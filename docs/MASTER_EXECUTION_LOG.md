# Master execution log — M04–M09

User's master prompt authorizes sequential implementation with a strict gate at
each milestone. No milestone is accepted based on mocks alone. Source exceptions
PSRIDs 716, 680 and 700 remain explicit non-PDF downloads. Original artifacts and
accepted M00–M03 milestone records are preserved.

## Starting checkpoint — 2026-10-09

- Inspected contracts, existing code/tests and authentic local manifests.
- Baseline `uv run pytest` exited 0: 276 passed in 54.46 seconds.
- `uv run python -m msmeintel extract verify --manifest data/downloads/sample_20.json`
  exited 0: 17 source hashes and 17 native output checksums verified, no problems.
- Captured byte hashes/mtimes for existing raw/native/discovery/download/sample
  files for post-M04 comparisons. Native receipts account for 17 PDFs / 101 pages.
- No project-owned `.git` exists; do not checkpoint an unrelated parent repository.
- Tesseract is not on PATH or at its standard Windows location. Upstream documents
  Apache-2.0 and links the UB Mannheim Windows distribution. `winget show --id
  UB-Mannheim.TesseractOCR --exact --source winget --accept-source-agreements`
  exited 0 and identified version 5.4.0.20240606 and installer checksum
  `c885fff6998e0608ba4bb8ab51436e1c6775c2bafc2559a19b423e18678b60c9`.

## M04 — FAILED; real OCR also BLOCKED (2026-10-09)

Last accepted milestone remains M03. **M05–M09 were not started.** The batch's
`complete: true` means all inputs were visited, not that the milestone passed.

### Files and functionality

Created:

- `.agent/plans/M04-ocr-tables.md` and this execution log.
- `src/msmeintel/ocr.py`: bounded Tesseract subprocesses, runtime/language-data
  identity, selective rendering and TSV text/word coordinates.
- `src/msmeintel/page_processing.py`: verified M03 inputs, per-page native table
  candidates and selective OCR, evidence/quality/errors, atomic versioned outputs,
  checkpoints, integrity checks and verified reuse.
- `scripts/check_m04_ocr.py`: separate mandatory real-engine scanned/mixed check;
  explicitly synthetic PDF generator shared by offline tests.
- `tests/test_page_processing.py`, `tests/fixtures/tables/golden.json` and
  `tests/fixtures/tables/README.md`: offline tests and manually read genuine cells.

Modified `src/msmeintel/cli.py` (thin `pages run/verify` commands), `README.md`
(unaccepted feature/limitations) and `THIRD_PARTY_LICENSES.md` (runtime status).
No existing test or frozen milestone plan was modified. No new Python dependency,
lockfile change, database schema or framework. Optional `MSMEINTEL_TESSERACT`
selects an approved local engine executable. Existing renderer licenses apply;
the uninstalled Tesseract binary bundle/language-data notices remain REVIEW REQUIRED.

### Final command results

Commands run from the nested project root. Native exit codes were preserved.

| Command | Exit | Actual result |
| --- | ---: | --- |
| `uv sync --locked` | 0 | 40 packages resolved/checked; no dependency changes |
| `uv run ruff check .` | 0 | All checks passed |
| `uv run ruff format --check .` | 0 | 32 files already formatted |
| `uv run pytest tests/test_page_processing.py` | 1 | 37 passed, 1 failed; 16.72 s |
| `uv run pytest` | 1 | 313 passed, 1 failed; 61.47 s; no skips |
| `uv run python -m msmeintel --help` | 0 | Existing commands plus `pages` |
| `uv run python -m msmeintel health` | 0 | Configuration OK; database connectivity not checked |
| `uv run python scripts/check_m04_ocr.py` | 2 | `{"status":"BLOCKED","error":"OCR_RUNTIME_UNAVAILABLE"}` |
| `uv run python -m msmeintel pages run --manifest data/downloads/sample_20.json` | 0 | First successful batch: 17 attempted, 17 processed; 101 pages |
| `uv run python -m msmeintel pages verify --manifest data/downloads/sample_20.json` | 0 | 17 verified documents; no integrity problems |
| `uv run python -m msmeintel pages run --manifest data/downloads/sample_20.json` (again) | 0 | 0 attempted, 17 reused; output bytes/mtimes unchanged |
| `uv run python -m msmeintel extract verify --manifest data/downloads/sample_20.json` | 0 | 17 source hashes and 17 native checksums verified |
| `uv run python -m msmeintel download verify --manifest data/downloads/sample_20.json` | 0 | 17 verified hashes, 2,442,368 bytes, 20 associations, 3 explicit source failures |

All 276 pre-existing tests pass. Offline tests make no live calls. The 38 added
tests cover raw table cells/order/coordinates, quality flags, selective mocked OCR,
timeouts/unavailable runtime, TSV parsing, malformed/encrypted inputs, provenance,
shared hashes, atomic failure/resume, corruption, version changes and reuse. The
separate real-engine check is mandatory and has NOT passed.

### Actual corpus and quality inspection

The successful batch took approximately 19.4 seconds: 17 authentic PDFs, 101
pages, 117 table candidates, 71 pages with review flags, zero page/document
processing errors and zero pages requiring/receiving OCR. Twenty original
project-document associations remain, including three excluded downloads.
These candidate counts are not counts of validated semantic tables.

Generated local outputs: `data/work/pages/manifest.json` and 17 JSON files at
`data/work/pages/<recipe-hash-prefix>/<recipe-hash>.json`. Recipe hashes bind raw
identity, native output checksum, parser/runtime versions and quality settings.
No government content was downloaded again. Manual inspection renders remain
under `data/work/m04-review/`; raw documents and native outputs were not edited.

Visually compared physical source pages and independently recorded expected cells:

- PSRID 79, page 2: fixed-cost/projected-sales rows matched.
- PSRID 156, page 8: machinery descriptions, quantities and total matched.
- PSRID 709, page 10 (Hand Made Paper from Waste): **FAILED**. Source has four
  columns (Particulars, QTY, RATE, AMOUNT). Expected row
  `["Rag Chopper", "1", "70,000.00", "70,000.00"]`; actual parser output adds a
  fifth `""` cell. The Hollander Beater row has the same defect. Source SHA-256:
  `21ecbdbcc4f6b83ef961f3b25c287fa4de9e3037706ca5dcd90992ea83c73711`.

The sole failing test is
`tests/test_page_processing.py::test_authentic_golden_tables_offline`.
This is an unresolved internal layout-quality defect, not a source exception.
Focused snap-tolerance, strict-line and rectangle-filter diagnostics did not
establish a safe fix; no guessed column trimming or relaxed reference was adopted.
An initial Windows long-path write failure was corrected by using one full recipe
hash per output path. Its regression test passes. Valid assertions remain intact.

### Integrity and existing exceptions

Compared all 75 pre-existing snapshot files by SHA-256 and modification time:
only the intentionally extended CLI changed. Raw PDFs (17), native files (18,
including manifest), discovery files (4), download manifest, sample/config,
existing tests and frozen plans remained unchanged. The second M04 run reused
all 17 document JSON files without changing their bytes or modification times;
only its current-run checkpoint/summary is refreshed.

PSRIDs **716, 680 and 700** remain `INVALID_PDF` / missing PDF version signature
in their original M02 records. They were not unpacked, replaced, parsed or counted
as successful PDFs. Integrity success does not resolve table accuracy or OCR.

### Runtime blocker and next corrective actions

`winget install --id UB-Mannheim.TesseractOCR --exact --source winget --silent
--accept-package-agreements --accept-source-agreements --disable-interactivity`
exited **1** after repeated download timeouts: `InternetOpenUrl() failed`,
`0x80072ee2`. No usable Tesseract engine was installed. No access restriction was
bypassed; no synthetic/mocked output was substituted for real OCR acceptance.

To resume M04:

1. Obtain an approved Tesseract installation with English traineddata through an
   available route; verify actual engine/bundle/data notices and configure PATH
   or `MSMEINTEL_TESSERACT`. Rerun the real OCR command above.
2. Correct the PSRID 709 column-geometry defect without altering the valid golden
   cells or damaging other tables. Rerun the targeted and full suites, all M04
   acceptance commands and genuine-source quality checks.
3. Advance only after the complete gate passes. Current unreviewed candidates
   must not be treated as validated business facts.

No Git checkpoint: no project-owned `.git` exists, and M04 was not accepted.
Execution stops here under the user's mandatory stop-on-failure rule.
