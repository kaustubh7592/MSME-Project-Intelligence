# M03 — Native PDF text and basic layout extraction

## Goal

Process the 17 authentic M02 PDFs into verified, page-addressable native text/word
JSON, retaining source identities and marking insufficient-text pages for M04.
Plan and implementation are authorized in the same task (2026-10-09).

## In scope

Read the validated M02 manifest; deduplicate by SHA-256; verify raw bytes before
each parse or reuse; enumerate every page; native text, word boxes and page
metadata; explicit errors/OCR flags; atomic JSON checkpoints; resume and
parser-version-aware reuse; offline fixtures/regressions and real-corpus review.

## Out of scope

OCR execution, table reconstruction, financial/business fields, AI, querying,
database domain tables, infrastructure, downloading or repairing source files.
M00–M02 plans/code remain unchanged except adding the M03 CLI group. PSRIDs 716,
680 and 700 remain documented M02 source-format exceptions, never parser inputs;
do not unpack their ZIP-like responses or fabricate replacements.

## Existing code/context inspected

`AGENTS.md`, `.agent/PLANS.md`, `docs/TECHNICAL_SPEC.md` (especially 13–15,
19, 33–40, 43, 56–58), roadmap, data dictionary, decisions; `cli.py`,
`raw_storage.py`, `downloads.py`, existing discovery/configuration conventions;
`pyproject.toml`, `README.md`, `THIRD_PARTY_LICENSES.md`, `.gitignore`,
`tests/conftest.py`, downloader tests/blank fixture; authentic discovery/sample
and `data/downloads/sample_20.json` (20 associations, 17 stored hashes).

## Design

- One source-independent `extraction.py` service, sequential and entirely local.
  Reuse M02 manifest validation and raw-file verification. Use pypdf for page
  enumeration/encryption preflight and pdfplumber for native text and words.
  Add only these specified parser dependencies and their required transitives;
  verify installed licenses, recording uncertainty as REVIEW REQUIRED.
- Read raw files only. Verify SHA/size/signature before parsing and before cache
  reuse; also verify after parsing before publishing successful derived output.
  Encrypted PDFs are explicit unsupported inputs (no password bypass). Parser
  errors are recorded per document/page and do not hide other successes.
- Pages retain 1-based PDF index (not guessed printed labels), text, ordered words
  with `x0/top/x1/bottom` boxes in PDF points, width/height, page bbox, rotation,
  image count, character/word counts, method, `ocr_used: false`, null confidence,
  status and error. Keep parser-generated whitespace, no financial normalization.
  Use pdfplumber geometric reading order with explicit x/y tolerance 3; no
  semantic column/table reconstruction. Under 80 non-whitespace characters means
  `OCR_REQUIRED`, retaining any native text; this is a heuristic, including blank
  pages, not proof of a scan. Documents classify TEXT_PDF / SCANNED_PDF / MIXED_PDF
  from these page results, with uncertainty documented. Page errors stay errors.
- `data/work/native/<sha256>.json`: schema/parser versions, extraction options,
  source SHA/path/size, timestamps, status (`TEXT_EXTRACTED`, `OCR_REQUIRED`,
  `PARTIAL`, `FAILED`), classification, page count and page results. Parser
  identity includes pypdf, pdfplumber, pdfminer.six versions and local algorithm
  revision/options. Insufficient text is not an extraction exception.
- `data/work/native/manifest.json`: input download-manifest identity, source key,
  original URL/project associations grouped by content hash, per-document output
  path/hash/status/counts/error, excluded M02 receipts and run counts. Failed M02
  associations remain visible but are not counted as attempted PDFs.
- Same-directory temporary file, flush/fsync, bounded Windows replacement retry,
  atomic replace for derived outputs/checkpoints. Never write into raw or input
  locations; reject linked output directories. One local writer supported.
  Reuse only complete verified outputs with matching parser identity and output
  checksum; changed versions, damaged/missing outputs and errors reprocess.
  Resume at document checkpoints; interrupted current document restarts. Orphan
  temporary files are never mistaken for completed results.
- CLI: `extract run --manifest <M02 receipt>` and `extract verify --manifest ...`.
  Fixed output beneath configured data directory avoids unsafe output options.
  Verify checks source/output hashes, coverage, associations and page totals.
  Exit 0 for completed native processing (OCR flags/excluded M02 failures are
  reported separately), 1 for extraction/integrity failures, 2 for bad input or
  storage/configuration error. No live source requests.

## File changes

- Create this plan and `src/msmeintel/extraction.py`.
- Extend `src/msmeintel/cli.py` with the two thin extraction commands.
- Update `pyproject.toml`, `uv.lock`, `THIRD_PARTY_LICENSES.md` for parser packages.
- Create `tests/test_extraction.py`, `tests/fixtures/extraction/README.md` and
  `tests/fixtures/extraction/golden.json` (small verified authentic page snippets).
  Generate explicit synthetic PDFs in tests using pypdf, including encrypted,
  image-only and mixed pages; no new fixture-generation dependency.
- Update README with M03 usage, format, classification/reuse semantics and limits.
- Generate ignored `data/work/native/*.json`; local review PNGs may be generated
  under `data/work/m03-review/` solely for manual acceptance, not runtime OCR.

## Database changes

None. No migrations, environment variables or domain schema changes.

## Implementation steps

1. Record this plan and baseline raw/input hashes; install/verify parser licenses.
2. Implement page extraction, provenance, safe outputs, resume and CLI commands.
3. Add offline synthetic tests and fix lint/test defects.
4. Process the authentic stored corpus; inspect rendered pages from at least
   three different documents and record small factual golden expectations.
5. Verify every raw/output hash and association, rerun to demonstrate zero parses,
   run all regressions/acceptance commands, update Progress/Outcome and stop.

## Tests

Text/numbering/boxes/rotation; empty and image-only OCR flags; mixed pages;
malformed/encrypted PDFs; per-page/document isolation; shared hashes retain all
associations; source corruption blocks parsing; atomic replacement and interrupted
resume; missing/corrupt output recovery; version-triggered reprocessing; no raw
or M02 receipt changes; CLI exit behavior; real corpus golden checks when local
files are present. Ordinary tests retain the existing socket/DNS prohibition.
Authentic corpus tests skip explicitly if local artifacts are absent, never fetch.

## Acceptance commands

Run from the repository containing `pyproject.toml`:

```powershell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -c "import msmeintel; print(msmeintel.__file__)"
uv run python -m msmeintel --help
uv run python -m msmeintel health
uv run alembic heads
uv run python -m msmeintel source --help
uv run python -m msmeintel download --help
uv run python -m msmeintel download verify --manifest data/downloads/sample_20.json
uv run python -m msmeintel extract --help
uv run python -m msmeintel extract run --manifest data/downloads/sample_20.json
uv run python -m msmeintel extract verify --manifest data/downloads/sample_20.json
uv run python -m msmeintel extract run --manifest data/downloads/sample_20.json
uv run python -m msmeintel extract verify --manifest data/downloads/sample_20.json
uv run pytest tests/test_extraction.py
```

First uncached run must attempt all 17 stored PDFs, account for every enumerable
page, preserve all 20 associations including exclusions, and leave raw hashes and
mtimes unchanged. Second run must report 17 verified reuses and zero parser
attempts if no extraction errors occurred. Manual inspection is additional to
these commands and records exact SHA/page/snippet observations in Outcome.

## Risks and open questions

No architectural blocker identified. PDF text order/fonts can be unreliable;
native success is not semantic accuracy. Threshold flags can include sparse
covers/blank pages and cannot detect every bad font encoding or existing bad OCR
layer. Per-page errors are isolated when enumeration works; corrupt page trees
can prevent enumeration entirely. Sequential in-process parsers have no hard
CPU/memory sandbox; retain the 50 MiB raw cap, close per-page caches, and do not
execute scripts/attachments. Government source redistribution remains REVIEW
REQUIRED; authentic bytes and full extracted text stay ignored/local. Dependency
license uncertainty affecting required use would be a genuine blocker.

## Progress

- [x] Inspect repository/contracts and record plan before implementation.
- [x] Implement extraction, persistence, CLI and verified dependency inventory.
- [x] Pass offline/regression/lint tests.
- [x] Process and manually inspect authentic corpus; verify integrity/idempotency.
- [x] Record acceptance evidence and completion.

## Outcome

**M03 COMPLETE — 2026-10-09.** All acceptance commands above exited 0. M04
has not started. No architecture/scope deviations or unresolved implementation
blockers. A transient Windows environment-install sharing lock resolved on the
normal locked-sync retry; no workaround dependency or infrastructure was added.

### Corpus acceptance

- First uncached run: 17 distinct PDFs attempted and successfully processed;
  101 total/processed pages, 101 with sufficient native text, zero OCR-required
  pages, zero page/document failures or partial documents. Each page has text,
  native word positions, metadata and status. No OCR was executed.
- All 20 projects and 20 original document associations remain represented:
  17 processable documents and three excluded M02 source-format failures (PSRIDs
  716, 680, 700, `INVALID_PDF` / missing PDF version signature). These exclusions
  are not M03 parser failures and their ZIP-like responses were not unpacked.
- Outputs: 17 `data/work/native/<sha256>.json` files and
  `data/work/native/manifest.json`, all local/ignored. Parser identity records
  pypdf 6.19.0, pdfplumber 0.11.10, pdfminer.six 20260107 and algorithm revision 1.
- `download verify`: 17 verified hashes, 2,442,368 original bytes, no integrity
  problems. `extract verify` before and after rerun: 17 raw hashes and 17 output
  checksums/association sets verified; no problems.
- Second run: zero parser attempts, 17 verified reuses; all 17 per-document
  output byte hashes **and modification times** unchanged. All 17 original PDF
  byte hashes and modification times match the pre-implementation baseline.
- M01 discovery/sample hashes unchanged. M02 receipt remains
  `be8195e52ec8bcb4294b723bffe14dc80399564dfce6fa80376f3dbb53af9255`.
  Baseline comparisons found no changes to frozen milestone plans, existing
  tests, migrations or source implementations; only the CLI gained M03 commands.

### Manual quality inspection

Rendered the following actual source pages with the already-required pypdfium2
dependency and visually compared them to the corresponding extracted JSON. PNGs
remain local under `data/work/m03-review/`; this is acceptance inspection, not a
rendering/OCR application feature. Full raw SHA identities and tiny verified text
snippets are recorded in `tests/fixtures/extraction/golden.json`.

| PSRID / source | Physical PDF page | Observed agreement |
|---|---:|---|
| 79 — Bakery Products (`9c13c856…`) | 1 of 2 | Heading and displayed `TOTAL PROJECT COST : Rs. 1,302,000.00` agree with text and page reference. |
| 156 — Book Binding (`1c861c0a…`) | 2 of 15 | `PROJECT AT GLANCE`, cost `21.48 Rs. In Lakhs`, employment `7 Persons` agree. |
| 709 — Hand Made Paper from Waste (`21ecbdbc…`) | 2 of 23 | Title and introduction opening sentence agree; an embedded photograph does not prevent native body-text extraction. |

Reading order was usable on these pages, but wrapped table cells (for example
Book Binding's raw-material row) flatten into text rather than retaining semantic
column relationships. No table reconstruction, source correction or business-fact
normalization was performed. This small inspection is not a claim of whole-corpus
semantic accuracy. The 80-character heuristic did not flag any genuine sample
pages; blank/image-only/mixed/threshold behavior is exercised by synthetic tests.

### Validation and delivered files

- Full `uv run pytest`: **276 passed**, no skips (239 existing M00–M02 tests plus
  37 M03 tests), final run 66.33 seconds. Targeted extraction command: **37 passed**,
  including all 17 local authentic PDFs and the three golden source observations.
- Ruff check passes; Ruff format check reports 27 files already formatted.
  Locked sync, installed-package import, root/source/download/extract help,
  health and empty Alembic heads all pass. No PostgreSQL connection was needed.
- Tests cover encryption/malformed/empty/image/mixed/rotated PDFs, coordinates and
  non-finite coordinate rejection, individual page/document errors, duplicate
  associations/content, source corruption/change during parsing, version and
  output-corruption reprocessing, atomic-write failures/retry, interrupted resume,
  verified idempotency, CLI exits and the existing socket/DNS prohibition.
- Created: this plan, `src/msmeintel/extraction.py`, `tests/test_extraction.py`,
  `tests/fixtures/extraction/README.md`, `tests/fixtures/extraction/golden.json`.
  Modified: `src/msmeintel/cli.py`, `pyproject.toml`, `uv.lock`, `README.md`,
  `THIRD_PARTY_LICENSES.md`. Nine installed parser/direct-transitive packages
  added; existing locked package versions unchanged. No schema/config changes.

Known limits remain those recorded under Risks: approximate reading order/OCR
heuristics, no hard parser CPU/memory sandbox, one local writer, and source-content
redistribution REVIEW REQUIRED. None blocks this local 17-PDF M03 acceptance.
