# M04 — OCR fallback and basic tables

## Goal

Extend verified M03 outputs with native PDF tables and real, selective Tesseract
OCR. Execute the master prompt gate; advance only on verified acceptance.

## In scope

Offline M03 consumption, pdfplumber tables/cell boxes, configurable page-quality
thresholds, pypdfium2 rendering and bounded Tesseract subprocesses, atomic versioned
JSON, provenance, resume, synthetic real-OCR tests and 17-document acceptance.

## Out of scope

Business normalization, SQL schema, AI and later milestones until this gate passes;
no changes to accepted native/raw artifacts and no new table framework.

## Existing code/context inspected

Repository instructions, PLANS, technical spec 13–16/36–40/56–58, roadmap, data
dictionary, decisions, extraction/CLI/config/download/raw services, native tests,
network guard and the 17 verified native/raw outputs. No project-owned `.git`
directory exists. Tesseract is absent initially; verified upstream Apache-2.0
license and the upstream-linked Windows distribution before attempting installation.

## Design

One `page_processing.py` service and a small `ocr.py` subprocess helper; existing
pdfplumber/Pillow/pypdfium2 dependencies and stdlib only. CLI `pages run/verify`
consumes the M02 manifest plus verified M03 receipts. M03 failures remain explicit
excluded processing inputs; M02 exceptions 716/680/700 are never PDFs.

Persist under `data/work/pages/`: version/config-keyed document JSON and a checkpoint
manifest retaining M03 associations, native output hashes, per-page native/OCR
method, errors and table quality. Keep successful old version outputs on disk if
reprocessing fails. Reuse atomic writes and raw verification from existing code.
Every page has independent OCR and table outcomes; per-document failures isolate.

Tables retain raw `rows`, null vs empty cells, row/column indices, table/page
numbers and bounding boxes. Conservative header candidates are explicitly labeled
heuristics. Flag missing/merged cells, sparse/ragged tables and possible page-edge
continuations; do not merge pages or repair values. Image-only tables remain
REVIEW_REQUIRED (OCR words available, no guessed grid).

OCR triggers on insufficient native non-whitespace characters/words or printable
text ratio. Defaults 80 chars, 10 words, 0.95 printable ratio; CLI may configure
them. Render only required pages at 300 DPI with a 40-million-pixel cap. Invoke
Tesseract without a shell, finite timeout, English language by default, TSV output;
retain raw OCR text, confidence, pixel and PDF-point boxes separately from native
text. Capture runtime/language-data/parser versions and settings for reuse keys.
Missing runtime/language data is an explicit blocker for real OCR acceptance.

## File changes

Create this short plan, `docs/MASTER_EXECUTION_LOG.md`, `src/msmeintel/ocr.py`,
`src/msmeintel/page_processing.py`, `tests/test_page_processing.py`,
`tests/fixtures/tables/golden.json` and `README.md` in that fixture directory.
Extend CLI, root README and license inventory. Add a small `scripts/check_m04_ocr.py`
offline real-runtime acceptance check and shared synthetic fixture generator only
if needed by both tests/acceptance. Generated outputs remain ignored under data.

## Database changes

None.

## Implementation steps

1. Verify accepted input hashes and Tesseract availability/license.
2. Implement isolated OCR/table extraction and atomic versioned persistence.
3. Test offline errors, provenance, raw values, actual OCR and reruns.
4. Process 17 genuine PDFs; inspect three genuine tables visually and record golden
   cells independently of parser results. Run all gates and log actual outcomes.

## Tests

Native pages avoid OCR; real scanned/mixed fixtures; table order/coordinates/null
cells/raw numeric strings; malformed/multi-page tables; encryption/malformed PDFs;
OCR timeout/failure; version changes; atomic failure/resume; source/output tampering;
all M00–M03 regression tests. Runtime tests explicitly report missing Tesseract,
and the separate mandatory real-OCR command must pass regardless of unit coverage.

## Acceptance commands

```powershell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_page_processing.py
uv run pytest
uv run python -m msmeintel --help
uv run python -m msmeintel health
uv run python scripts/check_m04_ocr.py
uv run python -m msmeintel pages run --manifest data/downloads/sample_20.json
uv run python -m msmeintel pages verify --manifest data/downloads/sample_20.json
uv run python -m msmeintel pages run --manifest data/downloads/sample_20.json
uv run python -m msmeintel extract verify --manifest data/downloads/sample_20.json
uv run python -m msmeintel download verify --manifest data/downloads/sample_20.json
```

## Risks and open questions

Table detection is approximate; quality flags are not financial validation. Sparse
text is not proof of a scan. No hard native-parser sandbox; OCR has a subprocess
timeout/pixel cap. Tesseract installation may be restricted by machine policy.
No routine approval requested; unresolved acceptance blockers halt progression.

## Progress

- [x] Inspect inputs/contracts and verify baseline hashes.
- [x] Implement M04 services, CLI, fixtures and tests; execute the complete gate.
- [ ] Pass table-quality acceptance: PSRID 709 page 10 has an extra empty column.
- [ ] Pass real OCR acceptance: Tesseract installation timed out; runtime absent.
- [x] Record FAILED/BLOCKED results and stop; M05 must not start.

## Outcome

M04 is **FAILED**, with an additional real-runtime **BLOCKER**, on 2026-10-09.
The final regression suite reports 313 passed / 1 failed; targeted M04 tests
report 37 passed / 1 failed. The valid manually verified four-column machinery
table assertion remains unchanged: pdfplumber adds a fifth empty column for
PSRID 709, physical page 10. Two other genuine golden tables matched. Focused
geometry/strict-line diagnostics did not establish a safe correction.

Real Tesseract acceptance exits 2 (`OCR_RUNTIME_UNAVAILABLE`); installation failed
with download timeout `0x80072ee2`. Mocked OCR unit tests do not satisfy this gate.

Partial functional results: 17 documents / 101 pages / 117 table candidates;
71 pages marked for review, zero OCR pages in the genuine corpus, zero batch
extraction errors. All 20 associations and three M02 source exceptions remain.
Integrity checks pass. A second run reuses all 17 outputs with unchanged hashes
and modification times. Original raw/native/input artifacts remain unchanged.

Ruff, formatting, locked sync, CLI/configuration and prior integrity checks pass.
Windows long-path failure was fixed within M04 using a single full recipe hash
in each output path; no dependency/schema changes or accepted milestone redesign.
No project Git repository is configured. See `docs/MASTER_EXECUTION_LOG.md` for
exact commands, output locations and corrective actions. M05–M09 were not started.
