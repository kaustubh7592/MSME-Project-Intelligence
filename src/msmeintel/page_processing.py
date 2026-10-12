"""M04 derived OCR/table records; native extraction and raw documents stay immutable."""

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

import pdfplumber

from . import discovery, downloads, extraction, ocr, raw_storage

ALGORITHM_VERSION = 1


@dataclass(frozen=True)
class Options:
    min_native_chars: int = 80
    min_native_words: int = 10
    min_printable_ratio: float = 0.95
    language: str = "eng"
    dpi: int = 300
    ocr_timeout: float = 60

    def __post_init__(self):
        if (
            type(self.min_native_chars) is not int
            or self.min_native_chars < 0
            or type(self.min_native_words) is not int
            or self.min_native_words < 0
            or not math.isfinite(self.min_printable_ratio)
            or not 0 <= self.min_printable_ratio <= 1
            or type(self.dpi) is not int
            or not 72 <= self.dpi <= 600
            or not math.isfinite(self.ocr_timeout)
            or self.ocr_timeout <= 0
            or not re.fullmatch(r"[A-Za-z0-9_]+", self.language)
        ):
            raise extraction.ExtractionError("Invalid page-processing settings.")


def path_for(data_dir: Path, digest: str | None = None, key: str | None = None) -> Path:
    root = data_dir.absolute()
    if digest is None:
        path = root / "work/pages/manifest.json"
    else:
        raw_storage.storage_path(digest)
        raw_storage.storage_path(key)
        # The full recipe hash includes the source SHA; two full hashes exceed Windows MAX_PATH.
        path = root / "work/pages" / key[:2] / f"{key}.json"
    for candidate in (root, *[root / p for p in reversed(path.relative_to(root).parents)], path):
        if candidate.is_symlink() or candidate.is_junction():
            raise extraction.ExtractionError("Linked page-processing paths are forbidden.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise extraction.ExtractionError("Page output escapes data directory.")
    return path


def fingerprint(value: dict) -> str:
    return hashlib.sha256(discovery.json_text(value).encode("utf-8")).hexdigest()


def needs_ocr(native: dict, options: Options) -> tuple[bool, dict]:
    text = native.get("text") or ""
    characters = [c for c in text if not c.isspace()]
    printable = sum(c.isprintable() and c != "\ufffd" for c in characters)
    quality = {
        "native_characters": len(characters),
        "native_words": native["word_count"],
        "printable_ratio": printable / len(characters) if characters else 0,
    }
    return (
        native["status"] == "FAILED"
        or len(characters) < options.min_native_chars
        or native["word_count"] < options.min_native_words
        or quality["printable_ratio"] < options.min_printable_ratio
    ), quality


def table_record(table, index: int, page_number: int, page_bbox: tuple) -> dict:
    rows = table.extract(x_tolerance=3, y_tolerance=3)
    boxes = [[list(cell) if cell is not None else None for cell in row.cells] for row in table.rows]
    if len(rows) != len(boxes) or any(len(r) != len(b) for r, b in zip(rows, boxes, strict=True)):
        raise ValueError("Table cell geometry disagrees with rows")
    for box in [table.bbox, *(c for row in boxes for c in row if c is not None)]:
        if (
            len(box) != 4
            or not all(math.isfinite(v) for v in box)
            or box[0] > box[2]
            or box[1] > box[3]
        ):
            raise ValueError("Invalid table coordinates")
    widths = [len(row) for row in rows]
    cells = [cell for row in rows for cell in row]
    missing, empty = cells.count(None), cells.count("")
    flags = []
    if not rows or len(set(widths)) != 1:
        flags.append("RAGGED_OR_EMPTY_TABLE")
    if not widths or min(widths) < 2 or len(rows) < 2:
        flags.append("NOT_A_RELIABLE_GRID")
    if missing:
        flags.append("MERGED_OR_MISSING_CELLS")
    if cells and (missing + empty) / len(cells) > 0.4:
        flags.append("SPARSE_TABLE")
    if any(cell and cell.count("\n") >= 3 for cell in cells):
        flags.append("MULTILINE_CELL_REVIEW")
    if table.bbox[1] - page_bbox[1] < 20 or page_bbox[3] - table.bbox[3] < 20:
        flags.append("PAGE_EDGE_POSSIBLE_CONTINUATION")
    header_candidates = [
        i + 1
        for i, row in enumerate(rows[:5])
        if sum(
            bool(
                re.search(
                    r"\b(particulars|amount|quantity|price|description|total|year)\b",
                    cell or "",
                    re.I,
                )
            )
            for cell in row
        )
        >= 2
    ]
    return {
        "table_index": index,
        "page_number": page_number,
        "method": "pdfplumber_lines",
        "bbox": list(table.bbox),
        "rows": rows,
        "cell_bboxes": boxes,
        "row_count": len(rows),
        "column_count": max(widths, default=0),
        "header_candidate_rows": header_candidates,
        "header_detection": "label_heuristic",
        "quality": {
            "status": "REVIEW_REQUIRED" if flags else "OK",
            "flags": flags,
            "missing_or_merged_cells": missing,
            "empty_cells": empty,
            "nonempty_fraction": (len(cells) - missing - empty) / len(cells) if cells else 0,
        },
    }


def process_document(
    raw: Path, native: dict, identity: dict, options: Options, engine: dict
) -> dict:
    result = {
        "schema_version": 1,
        "sha256": native["sha256"],
        "identity": identity,
        "created_at": downloads.now(),
        "pages": [],
        "error": None,
    }
    try:
        with pdfplumber.open(raw) as pdf:
            if not pdf.doc.is_extractable:
                raise ValueError("PDF extraction restricted")
            if len(pdf.pages) != native["page_count"]:
                raise ValueError("Native page count mismatch")
            for original, page in zip(native["pages"], pdf.pages, strict=True):
                required, quality = needs_ocr(original, options)
                value = {
                    "page_number": original["page_number"],
                    "native_quality": quality,
                    "ocr_required": required,
                    "ocr": None,
                    "ocr_error": None,
                    "text_method": "native",
                    "tables": [],
                    "table_errors": [],
                    "table_status": "NO_TABLE_DETECTED",
                    "issues": [],
                    "bbox": list(page.bbox),
                    "page_width": page.width,
                    "page_height": page.height,
                }
                try:
                    for index, table in enumerate(page.find_tables(), 1):
                        try:
                            value["tables"].append(
                                table_record(table, index, page.page_number, page.bbox)
                            )
                        except Exception as error:
                            value["table_errors"].append(
                                {
                                    "table_index": index,
                                    "category": "TABLE_EXTRACTION_ERROR",
                                    "exception_type": type(error).__name__,
                                }
                            )
                except Exception as error:
                    value["table_errors"].append(
                        {
                            "category": "TABLE_EXTRACTION_ERROR",
                            "exception_type": type(error).__name__,
                        }
                    )
                if value["table_errors"]:
                    value["table_status"] = "FAILED"
                elif value["tables"]:
                    value["table_status"] = "EXTRACTED"
                if required:
                    value["text_method"] = "ocr_pending"
                    try:
                        if "error" in engine:
                            raise ocr.OCRError(engine["error"])
                        value["ocr"] = ocr.extract(
                            raw,
                            page.page_number,
                            list(page.bbox),
                            engine,
                            dpi=options.dpi,
                            timeout=options.ocr_timeout,
                        )
                        value["text_method"] = "ocr"
                        if value["ocr"]["status"] == "OCR_EMPTY":
                            value["issues"].append("NO_OCR_TEXT")
                        elif value["ocr"]["mean_word_confidence"] < 60:
                            value["issues"].append("LOW_OCR_CONFIDENCE")
                    except ocr.OCRError as error:
                        value["ocr_error"] = error.category
                        value["text_method"] = "ocr_failed"
                    # No grid is invented from OCR word positions in this basic table stage.
                    value["issues"].append("OCR_TABLE_LAYOUT_REVIEW_REQUIRED")
                if any(t["quality"]["flags"] for t in value["tables"]):
                    value["issues"].append("TABLE_QUALITY_REVIEW_REQUIRED")
                value["status"] = (
                    "FAILED"
                    if value["ocr_error"] or value["table_errors"]
                    else "REVIEW_REQUIRED"
                    if value["issues"]
                    else "COMPLETE"
                )
                result["pages"].append(value)
                page.close()
    except Exception as error:
        result["error"] = {
            "category": "PDF_PROCESSING_ERROR",
            "exception_type": type(error).__name__,
        }
    result["status"] = (
        "FAILED"
        if result["error"] or any(p["status"] == "FAILED" for p in result["pages"])
        else "COMPLETE"
    )
    result["counts"] = counts(result["pages"])
    return result


def counts(pages: list) -> dict:
    return {
        "pages_processed": len(pages),
        "tables_extracted": sum(len(p["tables"]) for p in pages),
        "pages_ocr_required": sum(p["ocr_required"] for p in pages),
        "pages_ocr_processed": sum(p["ocr"] is not None for p in pages),
        "pages_review_required": sum(bool(p["issues"]) for p in pages),
        "pages_failed": sum(p["status"] == "FAILED" for p in pages),
    }


def read_native(manifest: Path, data_dir: Path) -> dict:
    check = extraction.verify(manifest, data_dir)
    if check["problems"]:
        raise extraction.ExtractionError("M03 source/output integrity or completion gate failed.")
    return json.loads(extraction.output_path(data_dir).read_text(encoding="utf-8"))


def _cached(path: Path, identity: dict, output_hash: str | None = None) -> dict:
    body = path.read_bytes()
    if output_hash is not None and hashlib.sha256(body).hexdigest() != output_hash:
        raise ValueError("Output checksum mismatch")
    value = json.loads(body)
    if (
        value["schema_version"] != 1
        or value["identity"] != identity
        or value["sha256"] != identity["source_sha256"]
        or value["status"] != "COMPLETE"
        or len(value["pages"]) != identity["page_count"]
        or [p["page_number"] for p in value["pages"]] != list(range(1, identity["page_count"] + 1))
        or value["counts"] != counts(value["pages"])
    ):
        raise ValueError("Incomplete or stale page output")
    return value


def execute(manifest: Path, data_dir: Path, options: Options) -> dict:
    source = read_native(manifest, data_dir)
    try:
        engine = ocr.runtime(options.language)
    except ocr.OCRError as error:
        engine = {"error": error.category}
    parser = {
        "algorithm": ALGORITHM_VERSION,
        "options": asdict(options),
        "ocr": engine,
        "versions": {
            name: version(name) for name in ("pdfplumber", "pdfminer.six", "pypdfium2", "Pillow")
        },
    }
    destination = path_for(data_dir)
    previous = {}
    if destination.exists():
        try:
            old = json.loads(destination.read_text(encoding="utf-8"))
            previous = {d["sha256"]: d for d in old["documents"]}
        except (ValueError, KeyError, TypeError) as error:
            raise extraction.ExtractionError(
                "Invalid M04 manifest; retain it for review."
            ) from error
    result = {
        "schema_version": 1,
        "source_key": source["source_key"],
        "parser": parser,
        "native_manifest_sha256": hashlib.sha256(
            extraction.output_path(data_dir).read_bytes()
        ).hexdigest(),
        "documents": [],
        "excluded_downloads": copy.deepcopy(source["excluded_downloads"]),
        "run": {"started_at": downloads.now(), "complete": False, "attempted": 0, "reused": 0},
    }
    for document in source["documents"]:
        native = json.loads(
            extraction.output_path(data_dir, document["sha256"]).read_text(encoding="utf-8")
        )
        identity = {
            "source_sha256": document["sha256"],
            "native_sha256": document["output_sha256"],
            "page_count": native["page_count"],
            "parser": parser,
        }
        key = fingerprint(identity)
        target = path_for(data_dir, document["sha256"], key)
        entry = {
            "sha256": document["sha256"],
            "receipts": copy.deepcopy(document["receipts"]),
            "identity": identity,
            "key": key,
            "status": "PENDING",
            "output_sha256": None,
            "output_path": target.relative_to(data_dir.absolute()).as_posix(),
            "counts": counts([]),
            "error": None,
        }
        result["documents"].append(entry)
        old = previous.get(document["sha256"], {})
        try:
            if old.get("key") != key or not old.get("output_sha256"):
                raise ValueError("No checkpoint for this version")
            output = _cached(target, identity, old["output_sha256"])
            checksum = old["output_sha256"]
            result["run"]["reused"] += 1
        except (OSError, ValueError, KeyError, TypeError):
            result["run"]["attempted"] += 1
            raw = raw_storage.safe_path(data_dir, document["storage_path"])
            output = process_document(raw, native, identity, options, engine)
            raw_storage.verify_file(
                data_dir, document["storage_path"], document["sha256"], document["byte_count"]
            )
            if (
                hashlib.sha256(
                    extraction.output_path(data_dir, document["sha256"]).read_bytes()
                ).hexdigest()
                != document["output_sha256"]
            ):
                raise extraction.ExtractionError("Native input changed during M04 processing.")
            # Versioned paths keep prior successful derivations if a new parser fails.
            checksum = extraction.atomic_json(target, output)
        entry.update(
            status=output["status"],
            output_sha256=checksum,
            counts=output["counts"],
            error=output["error"],
        )
        extraction.atomic_json(destination, result)
    result["run"].update(complete=True, ended_at=downloads.now())
    extraction.atomic_json(destination, result)
    return result


def summary(result: dict) -> dict:
    documents = result["documents"]
    associations = [a for d in documents for r in d["receipts"] for a in r["associations"]] + [
        a for d in result["excluded_downloads"] for a in d["associations"]
    ]
    return {
        **result["run"],
        "documents": len(documents),
        "documents_processed": sum(d["status"] == "COMPLETE" for d in documents),
        "documents_failed": sum(d["status"] == "FAILED" for d in documents),
        "projects": len({a["record_key"] for a in associations}),
        "associations": len(associations),
        "excluded_downloads": len(result["excluded_downloads"]),
        **{k: sum(d["counts"][k] for d in documents) for k in counts([])},
    }


def verify(manifest: Path, data_dir: Path) -> dict:
    source = read_native(manifest, data_dir)
    problems, checked = [], 0
    try:
        result = json.loads(path_for(data_dir).read_text(encoding="utf-8"))
        expected = {d["sha256"]: d for d in source["documents"]}
        if (
            not result["run"]["complete"]
            or len(result["documents"]) != len(expected)
            or {d["sha256"] for d in result["documents"]} != expected.keys()
            or result["excluded_downloads"] != source["excluded_downloads"]
        ):
            raise ValueError("M04 coverage differs from M03")
        for entry in result["documents"]:
            try:
                document = expected[entry["sha256"]]
                if (
                    entry["receipts"] != document["receipts"]
                    or entry["identity"]["native_sha256"] != document["output_sha256"]
                    or entry["key"] != fingerprint(entry["identity"])
                ):
                    raise ValueError("M04 identity/associations differ from source")
                output = _cached(
                    path_for(data_dir, entry["sha256"], entry["key"]),
                    entry["identity"],
                    entry["output_sha256"],
                )
                if output["counts"] != entry["counts"] or output["status"] != entry["status"]:
                    raise ValueError("M04 receipt differs from output")
                checked += 1
            except (OSError, ValueError, KeyError, TypeError):
                problems.append({"sha256": entry["sha256"], "category": "INVALID_PAGE_OUTPUT"})
    except (OSError, ValueError, KeyError, TypeError):
        problems.append({"category": "INVALID_PAGE_MANIFEST"})
    return {"verified_documents": checked, "problems": problems}
