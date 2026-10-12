"""Native extraction with explicitly synthetic PDFs; the global network guard stays active."""

import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject
from typer.testing import CliRunner

from msmeintel import cli, discovery, downloads, extraction, raw_storage
from msmeintel.sources.base import DocumentCandidate, ProjectCandidate

TEXT = "Native project profile with machinery capacity and employment. " * 3
ROOT = Path(__file__).resolve().parents[1]


def pdf_bytes(pages=(TEXT,), *, encrypted=False, rotated=False):
    """A local PDF fixture, not government content. None=image-only, empty string=blank."""
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        resources = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        content = b""
        if text:
            # Short separate lines stay inside the media box, allowing reliable coordinate checks.
            lines = [text[i : i + 60] for i in range(0, len(text), 60)]
            content = (
                "BT /F1 12 Tf 40 730 Td 16 TL "
                + " T* ".join(f"({line}) Tj" for line in lines)
                + " ET"
            ).encode()
        if text is None or text == "IMAGE " + TEXT:
            image = DecodedStreamObject()
            image.set_data(b"\xff\xff\xff")
            image.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Image"),
                    NameObject("/Width"): NumberObject(1),
                    NameObject("/Height"): NumberObject(1),
                    NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                    NameObject("/BitsPerComponent"): NumberObject(8),
                }
            )
            resources[NameObject("/XObject")] = DictionaryObject(
                {NameObject("/Im0"): writer._add_object(image)}
            )
            content += b" q 500 0 0 400 40 40 cm /Im0 Do Q"
        stream.set_data(content)
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = writer._add_object(stream)
        if rotated:
            page.rotate(90)
    if encrypted:
        writer.encrypt("synthetic-test-password", algorithm="AES-256")
    output = io.BytesIO()
    writer.write(output)
    writer.close()
    return output.getvalue()


@pytest.fixture
def corpus(tmp_path):
    def build(bodies=None):
        bodies = bodies if bodies is not None else [pdf_bytes()]
        projects = [
            ProjectCandidate(
                title=f"Synthetic {number}",
                listing_url="https://example.test/list",
                external_project_id=str(number),
                documents=(DocumentCandidate(f"/{number}.pdf", "https://example.test/list"),),
            )
            for number in range(len(bodies))
        ]
        full, _ = discovery.build_manifest(
            projects, source_key="synthetic", source_url="https://example.test/list"
        )
        full_path, sample_path = tmp_path / "full.json", tmp_path / "sample.json"
        manifest_path, data = tmp_path / "downloads.json", tmp_path / "data"
        discovery.write_manifest(full_path, full)
        discovery.write_sample(
            sample_path, discovery.select_sample(full, len(bodies)), replace=True
        )
        value = downloads.prepare(sample_path, full_path, manifest_path, data)
        for receipt in value["documents"]:
            body = bodies[int(receipt["associations"][0]["external_project_id"])]
            if body is None:
                receipt.update(
                    status="DOWNLOAD_FAILED",
                    error={
                        "category": "INVALID_PDF",
                        "message": "Synthetic non-PDF source exception.",
                        "at": downloads.now(),
                        "retryable": False,
                    },
                )
                continue
            digest = hashlib.sha256(body).hexdigest()
            relative = raw_storage.storage_path(digest)
            target = data / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(body)
            receipt.update(
                status="DOWNLOADED",
                sha256=digest,
                storage_path=relative,
                byte_count=len(body),
                downloaded_at=downloads.now(),
                verified_at=downloads.now(),
            )
        value["last_run"].update(complete=True, ended_at=downloads.now())
        downloads.checkpoint(manifest_path, value)
        return manifest_path, data

    return build


def result_for(manifest, data, index=0):
    return json.loads(
        extraction.output_path(data, manifest["documents"][index]["sha256"]).read_text()
    )


def test_text_numbering_coordinates_and_raw_unchanged(corpus):
    path, data = corpus([pdf_bytes((TEXT, TEXT + " Second page."))])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in data.glob("raw/*/*.pdf")}
    source = path.read_bytes()
    value = extraction.execute(path, data)
    result = result_for(value, data)
    assert result["page_count"] == 2
    assert result["classification"] == "TEXT_PDF"
    assert result["status"] == "TEXT_EXTRACTED"
    for number, page in enumerate(result["pages"], 1):
        assert page["page_number"] == number
        assert "Native project profile" in page["text"]
        assert page["word_count"] == len(page["words"]) > 0
        assert page["page_width"] == 612 and page["page_height"] == 792
        assert page["bbox"] == [0, 0, 612, 792] and page["rotation"] == 0
        assert page["ocr_used"] is False and page["ocr_confidence"] is None
        assert page["words"][0]["text"] == "Native"
        for word in page["words"]:
            assert 0 <= word["x0"] < word["x1"] <= 612
            assert 0 <= word["top"] < word["bottom"] <= 792
    assert result["pages"][0]["words"][0]["x0"] == 40
    assert result["pages"][0]["words"][0]["top"] == pytest.approx(52.484)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    assert source == path.read_bytes()
    assert extraction.verify(path, data) == {
        "source_hashes_verified": 1,
        "outputs_verified": 1,
        "problems": [],
    }


@pytest.mark.parametrize(
    "pages,classification,ocr",
    [
        (("",), "SCANNED_PDF", 1),
        ((None,), "SCANNED_PDF", 1),
        (("short caption",), "SCANNED_PDF", 1),
        ((TEXT, None, "", "tiny", "IMAGE " + TEXT), "MIXED_PDF", 3),
        (("IMAGE " + TEXT,), "TEXT_PDF", 0),
        (("x" * 79,), "SCANNED_PDF", 1),
        (("x" * 80,), "TEXT_PDF", 0),
    ],
)
def test_page_level_ocr_and_mixed_content(corpus, pages, classification, ocr):
    path, data = corpus([pdf_bytes(pages)])
    result = result_for(extraction.execute(path, data), data)
    assert result["classification"] == classification
    assert result["counts"]["pages_ocr_required"] == ocr
    assert result["counts"]["pages_failed"] == 0
    for original, page in zip(pages, result["pages"], strict=True):
        assert page["image_count"] == (original is None or original == "IMAGE " + TEXT)
        assert page["text"] is not None
    assert not extraction.verify(path, data)["problems"]


def test_rotation(corpus):
    path, data = corpus([pdf_bytes(rotated=True)])
    page = result_for(extraction.execute(path, data), data)["pages"][0]
    assert page["rotation"] == 90
    assert (page["page_width"], page["page_height"]) == (792, 612)
    assert any(not word["upright"] for word in page["words"])


@pytest.mark.parametrize("field", ["page_width", "word_x1"])
def test_invalid_coordinates_are_a_serializable_page_failure(field):
    word = {"text": "Native", "x0": 0, "x1": float("inf"), "top": 0, "bottom": 12, "upright": True}
    page = SimpleNamespace(
        width=float("nan") if field == "page_width" else 612,
        height=792,
        bbox=(0, 0, 612, 792),
        rotation=0,
        images=[],
        extract_text=lambda **kwargs: TEXT,
        extract_words=lambda **kwargs: [word],
        close=lambda: None,
    )
    result = extraction.extract_page(page, 1)
    assert result["status"] == "FAILED"
    assert result["error"]["category"] == "TEXT_EXTRACTION_ERROR"
    assert result["words"] == []
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "bad,category",
    [
        (b"%PDF-1.4\nmalformed\n%%EOF\n", "PDF_OPEN_ERROR"),
        (pdf_bytes(encrypted=True), "ENCRYPTED_PDF"),
        (pdf_bytes(()), "PDF_OPEN_ERROR"),
    ],
)
def test_bad_documents_isolated(corpus, bad, category):
    path, data = corpus([bad, pdf_bytes()])
    value = extraction.execute(path, data)
    report = extraction.report(value)
    assert report["summary"]["pdfs_processed"] == 1
    assert report["summary"]["pdfs_failed"] == 1
    assert report["failures"][0]["error"]["category"] == category
    assert extraction.verify(path, data)["outputs_verified"] == 1


def test_page_failure_retains_other_pages_and_partial_text(corpus, monkeypatch):
    path, data = corpus([pdf_bytes((TEXT, TEXT, TEXT))])
    page_class = extraction.pdfplumber.page.Page
    original = page_class.extract_words

    def fail_one(page, *args, **kwargs):
        if page.page_number == 2:
            raise ValueError("Untrusted PDF error body")
        return original(page, *args, **kwargs)

    monkeypatch.setattr(page_class, "extract_words", fail_one)
    value = extraction.execute(path, data)
    result = result_for(value, data)
    assert result["status"] == "PARTIAL"
    assert [p["status"] for p in result["pages"]] == ["TEXT_EXTRACTED", "FAILED", "TEXT_EXTRACTED"]
    assert result["pages"][1]["text"]
    assert "Untrusted PDF" not in json.dumps(result)
    assert value["documents"][0]["page_errors"][0]["page_number"] == 2
    monkeypatch.setattr(page_class, "extract_words", original)
    assert extraction.execute(path, data)["run"]["pdfs_attempted"] == 1


def test_same_content_associations_and_exclusions(corpus):
    body = pdf_bytes()
    path, data = corpus([body, body, None])
    source = downloads.read_manifest(path)
    # A second project sharing a URL is distinct from two URLs sharing the same bytes.
    extra = copy.deepcopy(source["documents"][0]["associations"][0])
    extra["record_key"] = "00000000-0000-0000-0000-000000000004"
    extra["external_project_id"] = "shared"
    source["documents"][0]["associations"].append(extra)
    downloads.checkpoint(path, source)
    value = extraction.execute(path, data)
    summary = extraction.summarize(value)
    assert summary["pdfs_attempted"] == summary["pdfs_available"] == 1
    assert summary["projects"] == summary["associations"] == 4
    assert summary["excluded_downloads"] == 1
    receipts = value["documents"][0]["receipts"]
    assert sum(len(r["associations"]) for r in receipts) == 3
    assert receipts[0]["associations"] == source["documents"][0]["associations"]
    assert not extraction.verify(path, data)["problems"]


def test_verified_idempotency_never_parses(corpus, monkeypatch):
    path, data = corpus()
    first = extraction.execute(path, data)
    target = extraction.output_path(data, first["documents"][0]["sha256"])
    before = target.read_bytes(), target.stat().st_mtime_ns

    def unexpected(*args):
        raise AssertionError("Verified file must not be parsed again")

    monkeypatch.setattr(extraction, "extract_document", unexpected)
    second = extraction.execute(path, data)
    assert second["run"]["pdfs_attempted"] == 0
    assert second["run"]["pdfs_reused"] == second["run"]["source_hashes_verified"] == 1
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before


@pytest.mark.parametrize("change", ["algorithm", "library", "threshold", "missing", "corrupt"])
def test_reprocessing_conditions(corpus, monkeypatch, change):
    path, data = corpus()
    first = extraction.execute(path, data)
    target = extraction.output_path(data, first["documents"][0]["sha256"])
    if change == "algorithm":
        monkeypatch.setattr(extraction, "ALGORITHM_VERSION", 2)
    elif change == "library":
        monkeypatch.setattr(extraction, "version", lambda name: "test-next-version")
    elif change == "threshold":
        monkeypatch.setattr(extraction, "MIN_NATIVE_CHARS", 2000)
    elif change == "missing":
        target.unlink()
    else:
        target.write_text('{"interrupted":')
    assert extraction.verify(path, data)["problems"]
    second = extraction.execute(path, data)
    assert second["run"]["pdfs_attempted"] == 1
    assert second["run"]["pdfs_reused"] == 0
    assert not extraction.verify(path, data)["problems"]


@pytest.mark.parametrize("cached", [False, True])
def test_raw_corruption_never_parsed_or_reused(corpus, monkeypatch, cached):
    path, data = corpus()
    if cached:
        extraction.execute(path, data)
    raw = next(data.glob("raw/*/*.pdf"))
    raw.write_bytes(raw.read_bytes().replace(b"Native", b"BROKEN"))

    def forbidden(*args):
        raise AssertionError("Corrupt raw document must never be parsed")

    monkeypatch.setattr(extraction, "extract_document", forbidden)
    value = extraction.execute(path, data)
    assert value["documents"][0]["error"]["category"] == "SOURCE_INTEGRITY_ERROR"
    assert value["run"]["pdfs_attempted"] == value["run"]["pdfs_reused"] == 0


def test_change_during_parse_not_published(corpus, monkeypatch):
    path, data = corpus()
    original = extraction.extract_document

    def changed(raw, document, parser):
        result = original(raw, document, parser)
        raw.write_bytes(raw.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(extraction, "extract_document", changed)
    value = extraction.execute(path, data)
    assert value["documents"][0]["error"]["category"] == "SOURCE_INTEGRITY_ERROR"
    assert value["run"]["source_hashes_verified"] == 0
    assert not extraction.output_path(data, value["documents"][0]["sha256"]).exists()


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_atomic_failure_retains_previous_output(tmp_path, monkeypatch, failure):
    target = tmp_path / "result.json"
    extraction.atomic_json(target, {"old": True})
    before = target.read_bytes()

    def fail(*args):
        raise OSError("Synthetic disk error")

    monkeypatch.setattr(extraction.os, failure, fail)
    with pytest.raises(OSError):
        extraction.atomic_json(target, {"new": True})
    assert target.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_transient_replace_retry(tmp_path, monkeypatch):
    replace, calls = extraction.os.replace, []

    def locked(source, target):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("Windows sharing lock")
        replace(source, target)

    monkeypatch.setattr(extraction.os, "replace", locked)
    monkeypatch.setattr(extraction, "sleep", lambda delay: None)
    extraction.atomic_json(tmp_path / "ok.json", {"ok": True})
    assert len(calls) == 3


def test_interrupted_run_resumes_at_document_boundary(corpus, monkeypatch):
    path, data = corpus([pdf_bytes(), pdf_bytes((TEXT + "second",))])
    original, calls = extraction.extract_document, []

    def interrupted(*args):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return original(*args)

    monkeypatch.setattr(extraction, "extract_document", interrupted)
    with pytest.raises(KeyboardInterrupt):
        extraction.execute(path, data)
    assert not json.loads(extraction.output_path(data).read_text())["run"]["complete"]
    assert extraction.verify(path, data)["problems"]
    monkeypatch.setattr(extraction, "extract_document", original)
    result = extraction.execute(path, data)
    assert result["run"]["pdfs_reused"] == result["run"]["pdfs_attempted"] == 1


def test_manifest_association_tampering_fails_verification(corpus):
    path, data = corpus()
    value = extraction.execute(path, data)
    value["documents"][0]["receipts"][0]["associations"] = []
    extraction.atomic_json(extraction.output_path(data), value)
    assert extraction.verify(path, data)["problems"]
    assert not extraction.verify(path, data)["outputs_verified"]


def test_output_links_rejected(tmp_path, monkeypatch):
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p.name == "work" or original(p))
    with pytest.raises(extraction.ExtractionError, match="Linked"):
        extraction.output_path(tmp_path)


@pytest.mark.parametrize(
    "body,exit_code",
    [(pdf_bytes(), 0), (pdf_bytes((None,)), 0), (pdf_bytes(encrypted=True), 1), (None, 0)],
)
def test_cli_offline(corpus, monkeypatch, body, exit_code):
    path, data = corpus([body])
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(data))
    runner = CliRunner()
    result = runner.invoke(cli.app, ["extract", "run", "--manifest", str(path)])
    assert result.exit_code == exit_code, result.output
    result = runner.invoke(cli.app, ["extract", "verify", "--manifest", str(path)])
    assert result.exit_code == exit_code, result.output


def test_cli_invalid_manifest(tmp_path):
    result = CliRunner().invoke(cli.app, ["extract", "run", "--manifest", str(tmp_path / "absent")])
    assert result.exit_code == 2 and "Extraction error:" in result.output


def test_authentic_corpus_golden_and_integrity(tmp_path):
    source = ROOT / "data/downloads/sample_20.json"
    golden_path = ROOT / "tests/fixtures/extraction/golden.json"
    if not source.exists() or not golden_path.exists():
        pytest.skip("Authentic local M02 corpus/golden observations are not present; never fetch.")
    manifest = downloads.read_manifest(source)
    receipts = [d for d in manifest["documents"] if d["status"] == "DOWNLOADED"]
    if not all((ROOT / "data" / d["storage_path"]).exists() for d in receipts):
        pytest.skip("Authentic local raw PDFs absent; never fetch.")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert {o["sha256"] for o in golden} <= {d["sha256"] for d in receipts}
    for document in receipts:
        raw = ROOT / "data" / document["storage_path"]
        original = raw.read_bytes(), raw.stat().st_mtime_ns
        raw_storage.verify_file(
            ROOT / "data", document["storage_path"], document["sha256"], document["byte_count"]
        )
        result = extraction.extract_document(raw, document, extraction.parser_identity())
        assert result["status"] in extraction.COMPLETE_STATUSES
        assert result["page_count"] == len(result["pages"]) > 0
        for observation in golden:
            if observation["sha256"] == document["sha256"]:
                assert observation["source_project_id"] in {
                    a["external_project_id"] for a in document["associations"]
                }
                assert result["page_count"] == observation["page_count"]
                for page in observation["pages"]:
                    text = result["pages"][page["page_number"] - 1]["text"]
                    assert page["snippet"] in " ".join(text.split())
        assert (raw.read_bytes(), raw.stat().st_mtime_ns) == original
