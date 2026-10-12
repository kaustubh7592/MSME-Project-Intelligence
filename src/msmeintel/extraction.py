"""Offline native PDF extraction. Raw artifacts and acquisition receipts are read-only."""

import copy
import hashlib
import json
import math
import os
import tempfile
from importlib.metadata import version
from pathlib import Path
from time import sleep

import pdfplumber
from pypdf import PdfReader

from . import discovery, downloads, raw_storage

ALGORITHM_VERSION = 1
MIN_NATIVE_CHARS = 80
WORD_OPTIONS = {"x_tolerance": 3, "y_tolerance": 3, "use_text_flow": False}
COMPLETE_STATUSES = {"TEXT_EXTRACTED", "OCR_REQUIRED"}


class ExtractionError(ValueError):
    """An actionable local extraction/input error without document-supplied messages."""


def parser_identity() -> dict:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "versions": {name: version(name) for name in ("pypdf", "pdfplumber", "pdfminer.six")},
        "min_native_chars": MIN_NATIVE_CHARS,
        "word_options": WORD_OPTIONS.copy(),
        "text_layout": False,
        "coordinates": "PDF points; x from left, top/bottom from page top; page bbox retained",
    }


def output_path(data_dir: Path, digest: str | None = None) -> Path:
    if digest is not None:
        raw_storage.storage_path(digest)
    root = data_dir.absolute()
    path = root / "work" / "native" / (f"{digest}.json" if digest else "manifest.json")
    for candidate in (root, root / "work", path.parent, path):
        if candidate.is_symlink() or candidate.is_junction():
            raise ExtractionError("Linked extraction output paths are forbidden.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ExtractionError("Extraction output escapes the data directory.")
    return path


def atomic_json(path: Path, value: dict) -> str:
    body = discovery.json_text(value).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                sleep(0.05 * 2**attempt)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(body).hexdigest()


def _error(category: str, error: Exception | None = None) -> dict:
    return {"category": category, "exception_type": type(error).__name__ if error else None}


def _empty_page(number: int) -> dict:
    return {
        "page_number": number,
        "status": "FAILED",
        "text": None,
        "words": [],
        "word_count": 0,
        "native_character_count": 0,
        "page_width": None,
        "page_height": None,
        "bbox": None,
        "rotation": None,
        "image_count": None,
        "extraction_method": "pdfplumber_native",
        "ocr_used": False,
        "ocr_confidence": None,
        "error": None,
    }


def extract_page(page, number: int) -> dict:
    result = _empty_page(number)
    try:
        if not all(math.isfinite(v) for v in (*page.bbox, page.width, page.height)):
            raise ValueError("Invalid page dimensions")
        result.update(
            page_width=page.width,
            page_height=page.height,
            bbox=list(page.bbox),
            rotation=page.rotation,
            image_count=len(page.images),
        )
        result["text"] = page.extract_text(layout=False, **WORD_OPTIONS) or ""
        result["native_character_count"] = sum(not c.isspace() for c in result["text"])
        words = [
            {key: word[key] for key in ("text", "x0", "top", "x1", "bottom", "upright")}
            for word in page.extract_words(**WORD_OPTIONS)
        ]
        if not all(
            math.isfinite(w[k]) and math.isfinite(w[end]) and w[k] <= w[end]
            for w in words
            for k, end in (("x0", "x1"), ("top", "bottom"))
        ):
            raise ValueError("Invalid page coordinates")
        result["words"] = words
        result["word_count"] = len(words)
        result["status"] = (
            "TEXT_EXTRACTED"
            if result["native_character_count"] >= MIN_NATIVE_CHARS
            else "OCR_REQUIRED"
        )
    except Exception as error:
        # Parser exceptions vary by malformed PDF; retain partial text and the failure type.
        result["error"] = _error("TEXT_EXTRACTION_ERROR", error)
        result["status"] = "FAILED"
    finally:
        page.close()
    return result


def page_counts(pages: list[dict]) -> dict:
    return {
        "pages_total": len(pages),
        "pages_processed": sum(p["status"] != "FAILED" for p in pages),
        "pages_with_text": sum(p["native_character_count"] > 0 for p in pages),
        "pages_sufficient_text": sum(p["status"] == "TEXT_EXTRACTED" for p in pages),
        "pages_ocr_required": sum(p["status"] == "OCR_REQUIRED" for p in pages),
        "pages_failed": sum(p["status"] == "FAILED" for p in pages),
    }


def _finish(result: dict) -> dict:
    result["counts"] = page_counts(result["pages"])
    counts = result["counts"]
    if result["error"] or counts["pages_failed"]:
        result["status"] = "PARTIAL" if counts["pages_processed"] else "FAILED"
        result["classification"] = None
    elif counts["pages_ocr_required"]:
        result["status"] = "OCR_REQUIRED"
        result["classification"] = "MIXED_PDF" if counts["pages_sufficient_text"] else "SCANNED_PDF"
    else:
        result["status"] = "TEXT_EXTRACTED"
        result["classification"] = "TEXT_PDF"
    return result


def extract_document(path: Path, document: dict, parser: dict) -> dict:
    result = {
        "schema_version": 1,
        "parser": parser,
        "sha256": document["sha256"],
        "storage_path": document["storage_path"],
        "byte_count": document["byte_count"],
        "extracted_at": downloads.now(),
        "page_count": None,
        "pages": [],
        "error": None,
    }
    try:
        with path.open("rb") as stream:
            reader = PdfReader(stream)
            if reader.is_encrypted:
                result["error"] = _error("ENCRYPTED_PDF")
                return _finish(result)
            result["page_count"] = len(reader.pages)
            if not result["page_count"]:
                raise ValueError("PDF has no pages")
            stream.seek(0)
            with pdfplumber.open(stream) as pdf:
                if not pdf.doc.is_extractable:
                    result["error"] = _error("EXTRACTION_RESTRICTED")
                elif len(pdf.pages) != result["page_count"]:
                    result["error"] = _error("PAGE_COUNT_MISMATCH")
                else:
                    for number, page in enumerate(pdf.pages, 1):
                        result["pages"].append(extract_page(page, number))
    except Exception as error:
        result["error"] = _error("PDF_OPEN_ERROR", error)
    if result["error"] and result["page_count"]:
        for number in range(len(result["pages"]) + 1, result["page_count"] + 1):
            page = _empty_page(number)
            page["error"] = result["error"]
            result["pages"].append(page)
    return _finish(result)


def _inputs(manifest_path: Path) -> tuple[dict, dict, list]:
    manifest = downloads.read_manifest(manifest_path)
    documents, excluded = {}, []
    for receipt in manifest["documents"]:
        if receipt["status"] != "DOWNLOADED":
            excluded.append(copy.deepcopy(receipt))
            continue
        digest = receipt["sha256"]
        item = documents.setdefault(
            digest,
            {
                "sha256": digest,
                "storage_path": receipt["storage_path"],
                "byte_count": receipt["byte_count"],
                "receipts": [],
            },
        )
        if item["byte_count"] != receipt["byte_count"]:
            raise ExtractionError("Conflicting sizes for one raw SHA-256.")
        item["receipts"].append(
            {
                k: copy.deepcopy(receipt[k])
                for k in ("canonical_url", "associations", "downloaded_at")
            }
        )
    return manifest, documents, excluded


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def _cached(data_dir: Path, document: dict, receipt: dict, parser: dict) -> dict:
    path = output_path(data_dir, document["sha256"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["output_sha256"]:
        raise ValueError("Derived output checksum mismatch")
    value = _read_json(path)
    if (
        value["schema_version"] != 1
        or value["parser"] != parser
        or any(value[k] != document[k] for k in ("sha256", "storage_path", "byte_count"))
        or value["status"] not in COMPLETE_STATUSES
        or not value["page_count"]
        or len(value["pages"]) != value["page_count"]
        or any(
            p["page_number"] != number or p["status"] not in COMPLETE_STATUSES
            for number, p in enumerate(value["pages"], 1)
        )
        or value["counts"] != page_counts(value["pages"])
    ):
        raise ValueError("Incomplete, stale or inconsistent extraction output")
    return value


def _receipt(result: dict, output_hash: str) -> dict:
    return {
        "status": result["status"],
        "classification": result["classification"],
        "output_path": f"work/native/{result['sha256']}.json",
        "output_sha256": output_hash,
        "counts": result["counts"],
        "error": result["error"],
        "page_errors": [
            {"page_number": p["page_number"], "error": p["error"]}
            for p in result["pages"]
            if p["error"]
        ],
    }


def summarize(manifest: dict) -> dict:
    documents = manifest["documents"]
    associations = [a for d in documents for r in d["receipts"] for a in r["associations"]] + [
        a for r in manifest["excluded_downloads"] for a in r["associations"]
    ]
    return {
        **manifest["run"],
        "projects": len({a["record_key"] for a in associations}),
        "associations": len(associations),
        "pdfs_available": len(documents),
        "pdfs_processed": sum(d["status"] in COMPLETE_STATUSES for d in documents),
        "pdfs_partial": sum(d["status"] == "PARTIAL" for d in documents),
        "pdfs_failed": sum(d["status"] == "FAILED" for d in documents),
        "pdfs_pending": sum(d["status"] == "PENDING" for d in documents),
        "excluded_downloads": len(manifest["excluded_downloads"]),
        **{key: sum(d["counts"][key] for d in documents) for key in page_counts([])},
    }


def execute(manifest_path: Path, data_dir: Path) -> dict:
    source, documents, excluded = _inputs(manifest_path)
    destination = output_path(data_dir)
    for path in [destination, *(output_path(data_dir, digest) for digest in documents)]:
        if path.resolve() == manifest_path.resolve():
            raise ExtractionError("Extraction cannot overwrite its input manifest.")
    previous = {}
    if destination.exists():
        try:
            saved = _read_json(destination)
            previous = {d["sha256"]: d for d in saved["documents"]}
        except (ValueError, KeyError, TypeError) as error:
            raise ExtractionError("Invalid extraction manifest; retain it for review.") from error
    parser = parser_identity()
    for digest, document in documents.items():
        old = previous.get(digest, {})
        document.update(
            status="PENDING",
            counts=page_counts([]),
            error=None,
            page_errors=[],
            output_path=None,
            output_sha256=old.get("output_sha256"),
            classification=None,
        )
    manifest = {
        "schema_version": 1,
        "source_key": source["source_key"],
        "source_url": source["source_url"],
        "download_manifest_path": str(manifest_path.resolve()),
        "download_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "parser": parser,
        "documents": [documents[digest] for digest in sorted(documents)],
        "excluded_downloads": excluded,
        "run": {
            "started_at": downloads.now(),
            "ended_at": None,
            "complete": False,
            "pdfs_attempted": 0,
            "pdfs_reused": 0,
            "source_hashes_verified": 0,
        },
    }
    atomic_json(destination, manifest)
    for document in manifest["documents"]:
        try:
            raw_storage.verify_file(
                data_dir, document["storage_path"], document["sha256"], document["byte_count"]
            )
            manifest["run"]["source_hashes_verified"] += 1
        except (raw_storage.ArtifactError, OSError) as error:
            document.update(
                status="FAILED", error=_error("SOURCE_INTEGRITY_ERROR", error), output_sha256=None
            )
            atomic_json(destination, manifest)
            continue
        try:
            result = _cached(data_dir, document, document, parser)
        except (OSError, ValueError, KeyError, TypeError):
            manifest["run"]["pdfs_attempted"] += 1
            result = extract_document(
                raw_storage.safe_path(data_dir, document["storage_path"]), document, parser
            )
            try:
                raw_storage.verify_file(
                    data_dir, document["storage_path"], document["sha256"], document["byte_count"]
                )
            except (raw_storage.ArtifactError, OSError) as error:
                manifest["run"]["source_hashes_verified"] -= 1
                document.update(
                    status="FAILED",
                    error=_error("SOURCE_INTEGRITY_ERROR", error),
                    output_sha256=None,
                )
                atomic_json(destination, manifest)
                continue
            digest = atomic_json(output_path(data_dir, document["sha256"]), result)
        else:
            manifest["run"]["pdfs_reused"] += 1
            digest = document["output_sha256"]
        document.update(_receipt(result, digest))
        atomic_json(destination, manifest)
    manifest["run"].update(complete=True, ended_at=downloads.now())
    atomic_json(destination, manifest)
    return manifest


def verify(manifest_path: Path, data_dir: Path) -> dict:
    source, expected, excluded = _inputs(manifest_path)
    problems, verified, outputs = [], 0, 0
    try:
        manifest = _read_json(output_path(data_dir))
        actual = {d["sha256"]: d for d in manifest["documents"]}
        if (
            manifest["schema_version"] != 1
            or manifest["source_key"] != source["source_key"]
            or manifest["download_manifest_sha256"]
            != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            or manifest["excluded_downloads"] != excluded
            or len(actual) != len(manifest["documents"])
            or actual.keys() != expected.keys()
            or not manifest["run"]["complete"]
            or manifest["parser"] != parser_identity()
        ):
            raise ValueError("Incomplete or stale manifest")
        for digest, document in expected.items():
            entry = actual[digest]
            try:
                raw_storage.verify_file(
                    data_dir, document["storage_path"], digest, document["byte_count"]
                )
                verified += 1
                if any(entry[k] != document[k] for k in document):
                    raise ValueError("Source association mismatch")
                value = _cached(data_dir, document, entry, parser_identity())
                if any(entry[k] != v for k, v in _receipt(value, entry["output_sha256"]).items()):
                    raise ValueError("Receipt/output mismatch")
                outputs += 1
            except (OSError, ValueError, KeyError, TypeError) as error:
                problems.append({"sha256": digest, "error": _error("VERIFICATION_ERROR", error)})
    except (OSError, ValueError, KeyError, TypeError) as error:
        problems.append({"error": _error("INVALID_EXTRACTION_MANIFEST", error)})
    return {"source_hashes_verified": verified, "outputs_verified": outputs, "problems": problems}


def report(manifest: dict) -> dict:
    return {
        "summary": summarize(manifest),
        "failures": [d for d in manifest["documents"] if d["status"] in {"FAILED", "PARTIAL"}],
        "excluded_downloads": [
            {
                "source_project_ids": [a["external_project_id"] for a in d["associations"]],
                "status": d["status"],
                "error": d["error"],
            }
            for d in manifest["excluded_downloads"]
        ],
    }
