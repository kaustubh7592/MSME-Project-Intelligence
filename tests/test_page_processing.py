"""Offline M04 contracts; actual OCR has a separate mandatory runtime acceptance command."""

import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pdfplumber
import pytest
import test_extraction as native_tests
from test_extraction import pdf_bytes
from typer.testing import CliRunner

from msmeintel import cli, extraction, ocr
from msmeintel import page_processing as pages

ROOT = Path(__file__).resolve().parents[1]
synthetic_pdf = runpy.run_path(str(ROOT / "scripts/check_m04_ocr.py"))["synthetic_pdf"]
ENGINE = {"executable": "synthetic-tesseract", "version": "TEST ONLY", "language": "eng"}


@pytest.fixture
def corpus(tmp_path):
    return native_tests.corpus.__wrapped__(tmp_path)


@pytest.fixture(autouse=True)
def fake_runtime(monkeypatch):
    monkeypatch.setattr(ocr, "runtime", lambda language: ENGINE.copy())


def workflow(corpus, *bodies):
    path, data = corpus(list(bodies) if bodies else [synthetic_pdf()])
    extraction.execute(path, data)
    return path, data


def read_output(result, data, index=0):
    entry = result["documents"][index]
    return json.loads((data / entry["output_path"]).read_text(encoding="utf-8"))


def test_native_table_cells_coordinates_and_no_ocr(corpus, monkeypatch):
    path, data = workflow(corpus)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in data.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Native PDF must not invoke OCR")

    monkeypatch.setattr(ocr, "extract", forbidden)
    result = pages.execute(path, data, pages.Options())
    table = read_output(result, data)["pages"][0]["tables"][0]
    assert table["rows"] == [
        ["Particulars", "Amount"],
        ["Machine", "1,23,456.00"],
        ["Missing amount", ""],
    ]
    assert table["cell_bboxes"][0] == [[50, 142, 300, 192], [300, 142, 500, 192]]
    assert table["page_number"] == table["table_index"] == 1
    assert table["header_candidate_rows"] == [1]
    assert table["quality"]["empty_cells"] == 1
    assert table["quality"]["missing_or_merged_cells"] == 0
    assert pages.summary(result)["pages_ocr_processed"] == 0
    assert pages.verify(path, data)["problems"] == []
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in before.items())


def test_multi_page_table_keeps_page_reference(corpus):
    path, data = workflow(corpus, synthetic_pdf())
    native_path = next(data.glob("raw/*/*.pdf"))
    with pdfplumber.open(native_path) as pdf:
        table = pdf.pages[0].find_tables()[0]
        first = pages.table_record(table, 1, 1, pdf.pages[0].bbox)
        second = pages.table_record(table, 1, 2, pdf.pages[0].bbox)
    assert first["rows"] == second["rows"]
    assert (first["page_number"], second["page_number"]) == (1, 2)


def test_missing_merged_ragged_and_page_edge_quality():
    table = SimpleNamespace(
        bbox=(0, 0, 100, 100),
        rows=[
            SimpleNamespace(cells=[(0, 0, 50, 50), None]),
            SimpleNamespace(cells=[(0, 50, 100, 100)]),
        ],
        extract=lambda **kwargs: [["Header", None], ["1 5.75"]],
    )
    value = pages.table_record(table, 1, 4, (0, 0, 100, 100))
    assert value["rows"] == [["Header", None], ["1 5.75"]]
    assert value["quality"]["missing_or_merged_cells"] == 1
    assert {"RAGGED_OR_EMPTY_TABLE", "PAGE_EDGE_POSSIBLE_CONTINUATION"} <= set(
        value["quality"]["flags"]
    )


@pytest.mark.parametrize(
    "characters,words,ratio,required",
    [(79, 20, 1, True), (80, 10, 1, False), (200, 9, 1, True), (200, 20, 0.5, True)],
)
def test_configurable_ocr_quality(characters, words, ratio, required):
    text = "a" * int(characters * ratio) + "\ufffd" * (characters - int(characters * ratio))
    assert (
        pages.needs_ocr(
            {"text": text, "word_count": words, "status": "TEXT_EXTRACTED"}, pages.Options()
        )[0]
        is required
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"min_native_chars": -1},
        {"dpi": 700},
        {"min_printable_ratio": float("nan")},
        {"ocr_timeout": 0},
        {"language": "--help"},
    ],
)
def test_bad_configuration_rejected(settings):
    with pytest.raises(extraction.ExtractionError):
        pages.Options(**settings)


def test_mixed_only_image_page_selected(corpus, monkeypatch):
    path, data = workflow(corpus, synthetic_pdf(scanned=True, mixed=True))
    invoked = []

    def fake(raw, number, bbox, engine, **kwargs):
        invoked.append(number)
        return {
            "status": "OCR_COMPLETE",
            "text": "Synthetic mocked OCR",
            "words": [],
            "mean_word_confidence": 90,
        }

    monkeypatch.setattr(ocr, "extract", fake)
    result = pages.execute(path, data, pages.Options())
    output = read_output(result, data)
    assert invoked == [2]
    assert [p["text_method"] for p in output["pages"]] == ["native", "ocr"]
    assert output["pages"][1]["issues"] == ["OCR_TABLE_LAYOUT_REVIEW_REQUIRED"]


@pytest.mark.parametrize(
    "category", ["OCR_TIMEOUT", "OCR_RUNTIME_UNAVAILABLE", "OCR_PROCESS_FAILED"]
)
def test_ocr_failure_isolated_and_native_unchanged(corpus, monkeypatch, category):
    path, data = workflow(corpus, synthetic_pdf(scanned=True), synthetic_pdf())
    before = {p: p.read_bytes() for p in (data / "work/native").glob("*.json")}

    def fail(*args, **kwargs):
        raise ocr.OCRError(category)

    monkeypatch.setattr(ocr, "extract", fail)
    result = pages.execute(path, data, pages.Options())
    assert pages.summary(result)["documents_failed"] == 1
    assert pages.summary(result)["documents_processed"] == 1
    failed = next(
        read_output(result, data, i)
        for i, d in enumerate(result["documents"])
        if d["status"] == "FAILED"
    )
    assert failed["pages"][0]["ocr_error"] == category
    assert all(p.read_bytes() == body for p, body in before.items())


def test_table_failure_recorded(corpus, monkeypatch):
    path, data = workflow(corpus)

    def fail(page):
        raise ValueError("Malformed table payload")

    monkeypatch.setattr(pdfplumber.page.Page, "find_tables", fail)
    result = pages.execute(path, data, pages.Options())
    page = read_output(result, data)["pages"][0]
    assert page["table_status"] == "FAILED"
    assert page["table_errors"][0]["category"] == "TABLE_EXTRACTION_ERROR"
    assert "payload" not in json.dumps(page)


@pytest.mark.parametrize("body", [b"%PDF-1.4\nmalformed\n%%EOF\n", pdf_bytes(encrypted=True)])
def test_bad_pdf_native_gate_explicit(corpus, body):
    path, data = workflow(corpus, body)
    with pytest.raises(extraction.ExtractionError, match="M03"):
        pages.execute(path, data, pages.Options())


def test_idempotency_shared_hash_and_associations(corpus, monkeypatch):
    body = synthetic_pdf()
    path, data = workflow(corpus, body, body, None)
    first = pages.execute(path, data, pages.Options())
    target = data / first["documents"][0]["output_path"]
    before = target.read_bytes(), target.stat().st_mtime_ns

    def forbidden(*args):
        raise AssertionError("Cached result must not be reprocessed")

    monkeypatch.setattr(pages, "process_document", forbidden)
    second = pages.execute(path, data, pages.Options())
    assert pages.summary(second)["reused"] == 1
    assert pages.summary(second)["attempted"] == 0
    assert pages.summary(second)["associations"] == 3
    assert len(second["documents"][0]["receipts"]) == 2
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before


@pytest.mark.parametrize("change", ["parser", "ocr", "options", "corrupt"])
def test_reprocessing_and_prior_version_preserved(corpus, monkeypatch, change):
    path, data = workflow(corpus)
    first = pages.execute(path, data, pages.Options())
    target = data / first["documents"][0]["output_path"]
    before = target.read_bytes()
    options = pages.Options()
    if change == "parser":
        monkeypatch.setattr(pages, "ALGORITHM_VERSION", 2)
    elif change == "ocr":
        monkeypatch.setattr(
            ocr, "runtime", lambda language: {**ENGINE, "version": "NEXT TEST VERSION"}
        )
    elif change == "options":
        options = pages.Options(min_native_chars=81)
    else:
        target.write_text("broken")
    second = pages.execute(path, data, options)
    assert second["run"]["attempted"] == 1
    assert not pages.verify(path, data)["problems"]
    if change != "corrupt":
        assert target.read_bytes() == before
        assert second["documents"][0]["output_path"] != first["documents"][0]["output_path"]


def test_new_version_failure_keeps_previous_success(corpus, monkeypatch):
    path, data = workflow(corpus)
    first = pages.execute(path, data, pages.Options())
    target = data / first["documents"][0]["output_path"]
    before = target.read_bytes()
    monkeypatch.setattr(pages, "ALGORITHM_VERSION", 2)
    monkeypatch.setattr(
        pdfplumber.page.Page, "find_tables", lambda page: (_ for _ in ()).throw(ValueError())
    )
    result = pages.execute(path, data, pages.Options())
    assert result["documents"][0]["status"] == "FAILED"
    assert target.read_bytes() == before


def test_raw_corruption_blocks_processing(corpus):
    path, data = workflow(corpus)
    raw = next(data.glob("raw/*/*.pdf"))
    raw.write_bytes(raw.read_bytes() + b"corrupt")
    with pytest.raises(extraction.ExtractionError, match="integrity"):
        pages.execute(path, data, pages.Options())


def test_atomic_replace_failure_retains_output(tmp_path, monkeypatch):
    target = tmp_path / "output.json"
    extraction.atomic_json(target, {"old": True})
    before = target.read_bytes()

    def fail(*args):
        raise OSError("Disk failure")

    monkeypatch.setattr(extraction.os, "replace", fail)
    with pytest.raises(OSError):
        extraction.atomic_json(target, {"new": True})
    assert target.read_bytes() == before


def test_windows_output_path_uses_one_full_recipe_hash():
    target = pages.path_for(Path("data"), "a" * 64, "b" * 64)
    assert target.relative_to(Path("data").absolute()).as_posix() == (
        "work/pages/bb/" + "b" * 64 + ".json"
    )


def test_interrupted_documents_resume(corpus, monkeypatch):
    path, data = workflow(corpus, synthetic_pdf(), pdf_bytes())
    original, calls = pages.process_document, []

    def interrupted(*args):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return original(*args)

    monkeypatch.setattr(pages, "process_document", interrupted)
    with pytest.raises(KeyboardInterrupt):
        pages.execute(path, data, pages.Options())
    assert pages.verify(path, data)["problems"]
    monkeypatch.setattr(pages, "process_document", original)
    result = pages.execute(path, data, pages.Options())
    assert result["run"]["attempted"] == result["run"]["reused"] == 1


TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext\n"
    "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90.5\t12345\n"
)


def test_tsv_preserves_text_and_maps_coordinates():
    result = ocr.parse_tsv(TSV, width=200, height=100, bbox=[0, 0, 400, 200])
    assert result["text"] == "12345"
    assert result["words"][0]["pixel_bbox"] == [10, 20, 40, 30]
    assert result["words"][0]["bbox"] == [20, 40, 80, 60]
    assert result["mean_word_confidence"] == 90.5


@pytest.mark.parametrize(
    "text",
    [
        "bad",
        TSV.replace("90.5", "nan"),
        TSV.replace("90.5", "101"),
        TSV.replace("\t30\t", "\t900\t"),
    ],
)
def test_bad_tsv(text):
    with pytest.raises(ocr.OCRError, match="INVALID_OCR_OUTPUT"):
        ocr.parse_tsv(text, width=200, height=100, bbox=[0, 0, 400, 200])


@pytest.mark.parametrize(
    "failure,category",
    [
        (subprocess.TimeoutExpired("test", 1), "OCR_TIMEOUT"),
        (FileNotFoundError(), "OCR_RUNTIME_UNAVAILABLE"),
    ],
)
def test_subprocess_timeout_and_missing_binary(monkeypatch, failure, category):
    def fail(*args, **kwargs):
        assert kwargs["shell"] is False and kwargs["timeout"] == 1
        raise failure

    monkeypatch.setattr(ocr.subprocess, "run", fail)
    with pytest.raises(ocr.OCRError, match=category):
        ocr._run(["synthetic"], 1)


def test_cli_native_run_and_verify(corpus, monkeypatch):
    path, data = workflow(corpus)
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(data))
    for command in ("run", "verify"):
        result = CliRunner().invoke(cli.app, ["pages", command, "--manifest", str(path)])
        assert result.exit_code == 0, result.output


def test_authentic_golden_tables_offline():
    golden = ROOT / "tests/fixtures/tables/golden.json"
    if not golden.exists():
        pytest.skip("Manual table reference values not recorded yet; not an accepted M04 gate.")
    for item in json.loads(golden.read_text(encoding="utf-8")):
        raw = ROOT / "data/raw" / item["sha256"][:2] / f"{item['sha256']}.pdf"
        if not raw.exists():
            pytest.skip("Authentic local raw PDFs absent; never download in tests.")
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == item["sha256"]
        with pdfplumber.open(raw) as pdf:
            page = pdf.pages[item["page_number"] - 1]
            tables = [
                pages.table_record(t, i, page.page_number, page.bbox)
                for i, t in enumerate(page.find_tables(), 1)
            ]
            for expected in item["rows"]:
                assert any(expected in t["rows"] for t in tables)
