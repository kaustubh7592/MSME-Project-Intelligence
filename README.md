# Government MSME Project Intelligence Platform

M00 is the accepted executable skeleton. M01 discovers the official PMEGP
project list, preserves its metadata/document links in JSON, and selects a
deterministic representative 20. Authentic HTML/JSON fixtures and the real
`config/sample_20.json` are included; generated full manifests stay under `data/`.
M02 adds policy-checked downloads and immutable raw PDF storage. M03 adds native
page text/word extraction. OCR, business-fact extraction, AI and queries are not implemented.

## Prerequisites

- Python 3.12 or newer (uv can install a managed Python)
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL for later database operations; it is not required for M0 checks

## Setup

```bash
uv sync
uv run python -m msmeintel --help
uv run python -m msmeintel health
```

Configuration is read from environment variables. `.env.example` documents safe local
defaults, but M0 intentionally does not load `.env` files.

```text
DATABASE_URL=postgresql+psycopg://msmeintel:msmeintel@localhost:5432/msmeintel
MSMEINTEL_LOG_LEVEL=INFO
MSMEINTEL_DATA_DIR=./data
```

`health` validates configuration without contacting PostgreSQL and never prints database
credentials.

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -c "import msmeintel; print(msmeintel.__file__)"
uv run python -m msmeintel --help
uv run python -m msmeintel health
uv run alembic heads
```

The Alembic environment is initialized but has no revisions or domain tables in M0.
Commands that actually connect to PostgreSQL use `DATABASE_URL` and require an existing
local database.

## M01 discovery commands

Run from the repository containing `pyproject.toml`:

```bash
uv sync --locked
uv run python -m msmeintel source --help
uv run python -m msmeintel source smoke --source pmegp
uv run python -m msmeintel source discover --source pmegp
uv run python -m msmeintel source list --source pmegp --limit 20
uv run python -m msmeintel source sample --source pmegp --count 20 --output config/sample_20.json
```

`smoke` and `discover` are explicitly LIVE. All other commands are offline and
do not connect to PostgreSQL. `list` without a manifest reports "not discovered";
sampling without a valid full manifest fails. Discovery errors exit 2 without
replacing an existing good snapshot. An unexpected table shell, unsuccessful or
changed JSON envelope, malformed identifiable row, or incomplete response fails
explicitly instead of publishing a smaller/empty successful corpus.

### Verified PMEGP source (2026-10-08)

The primary source is [ProjectDetailList](https://pmegp.msme.gov.in/Home/ProjectDetailList),
not the older KVIC profile listing. Its initial HTML has the table headings and
an empty `#ux_tablebody`. The observed
[row-loading script](https://pmegp.msme.gov.in/TFL_Scripts/Home/ProjectDetailList.cshtml.js)
calls public [GetAllProjectDocuments](https://pmegp.msme.gov.in/Home/GetAllProjectDocuments)
using **GET with no query parameters or body**. The response is
`{"success":true,"data":[...]}` with the entire available array. No login,
browser session, browser runtime, API key, or pagination request is needed.

Browser paging is client-side: initially 10 rows, with 10/25/50/100 choices.
Search/sort also operate on the loaded array. There is no server page size,
page/offset parameter, or separate total field; discovery counts deduplicated
PSRIDs from the complete response. The observed run contained 1,024 projects
and 983 unique document URLs. These are observations, never application constants.

Preserved API fields: `PSRID`, exact `ProjectName`, `ProjectCost`, `DocPath`,
`IsActive`, `CreatedOn`, and nullable `ModifyOn`. `Sr No` is the JavaScript array
index plus one, not an official ID, so it is not used as identity or stored as a
stable source field. One publicly listed record has `IsActive: false`; discovery
retains it because the source page also displays every returned row.

There is no separate category field/filter. `category_hint` preserves the literal
trailing ` ( group label )` annotation published in each name; it does not infer
a sector from business words. Nine such labels were observed, including the
publisher-style label `Samadhan Projects`, which is not a canonical sector.
Missing/ambiguous annotations stay null.

The observed download handler constructs `/Home/DownloadDocument?fileName=` plus
JavaScript `encodeURIComponent(DocPath)`. Discovery reproduces that URL construction,
retains the original `DocPath`, and canonicalizes the result without requesting it.
There are no individual detail-page URLs in this response. See
[fixture provenance and reuse notes](tests/fixtures/pmegp/README.md).

HTTP uses one sequential httpx client, verified TLS, a descriptive user-agent,
10-second connect / 30-second other timeouts, a minimum one-second request-start
delay, and any stricter supported robots pacing. `--timeout` and
`--request-delay` accept finite positive seconds; the delay cannot lower the
policy floor. Robots are checked first. Unknown/challenged policies, unsupported
or ambiguous restriction precedence, denials, redirects, and unexpected MIME
types fail closed. Only the exact robots/listing/JSON routes are requestable.
Both HTML and JSON responses are capped at 5 MiB. The verified robots endpoint
returned 404 (no published policy); future policy responses are checked on each run.
Known document URLs are never requested (not even HEAD); unexpected PDF bodies
are closed unread. No authentication, CAPTCHA, anti-bot, or robots bypass exists.

### Manifest and sample

Default manifest: `$MSMEINTEL_DATA_DIR/discovery/pmegp.json` (normally
`data/discovery/pmegp.json`, already ignored). UTF-8, pretty-printed JSON contains
schema version, source key/URL, UTC discovery time, scope/completeness, dynamic
deduplicated population, project observations, and issues. Project observations
retain raw/cleaned names, nullable source ID/category/detail URL, original and
canonical listing/detail URLs, raw labeled metadata, document associations,
first/last-seen times, and link-discovery status. No absent field is inferred.
`raw_metadata` preserves JSON scalars, including false and null. Decimal JSON
numbers use exact decimal text (e.g. `ProjectCost: "180500.0000"`) without binary
floating-point rounding. The listing header explicitly states rupees;
`normalized_metadata.project_cost_inr` holds a separate exact decimal string
(`"180500"` in that example) when conversion is unambiguous and bounded. Zero
remains zero, and unknown/null costs are not normalized. These are discovery
observations, not validated M5 financial facts. Source timestamps remain verbatim.

Each canonical document appears once per project; `original_variants` preserves
additional original href/URL/title/found-on/type observations. One document may
belong to multiple projects. UUID5 record keys identify source observations,
not canonical businesses or file content. Identity prefers official ID, then
verified detail URL, then exact stable visible metadata and canonical document
URLs. Without stable IDs, changed metadata/links may be reported as a new record;
no semantic merging is attempted. Contradictory strong identities fail the run.

Successful reruns retain first-seen time and report added/changed/no-longer-seen
keys. "No longer seen" is not proof of permanent source deletion. Invalid old
JSON is never silently discarded. Writes use a closed, flushed same-directory
temporary file and atomic replacement. One writer at a time is supported; there
are no locks, workers, or database tables.

Filtering occurs only **after full enumeration** and cannot overwrite a full
manifest. It retains the full dynamic total but labels `complete: false`:

```bash
uv run python -m msmeintel source discover --source pmegp --limit 3 --output data/discovery/pmegp-limit-3.json
uv run python -m msmeintel source discover --source pmegp --sample config/sample_20.json --output data/discovery/pmegp-selected-20.json
```

`--limit` and `--sample` are mutually exclusive; every sample key must still be
present. Neither option is a reduced-network crawl or a population estimate.

Sampling uses complete manifests only, selecting projects with document links.
It rotates explicit categories and direct/detail, single/multiple-link patterns,
then chooses evenly spaced canonical identities within each allocated bucket.
Missing categories form their own bucket; absent categories use deterministic
pattern/even-spread coverage, not an inferred semantic classification. More
categories than slots are evenly spread and uncovered categories are reported.
Insufficient eligible projects fail; no padding or first-20 shortcut is used.
Document reachability, layout and OCR diversity remain unknown.

Samples omit volatile timestamps, reproduce unchanged bytes, and are not
regenerated by discovery. Existing equal samples are unchanged; changed samples
require another output path or explicit `--replace`. `config/sample_20.json`
comes from successful complete official discovery. Its 20 distinct PSRIDs and
20 distinct document URLs cover all nine published group labels. All currently
observed links have the same single-listing-download pattern; PDF layout/OCR
diversity is not known. Rerun selection was byte-identical.

### Offline testing

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

All ordinary tests block real socket/DNS calls. HTTP tests use `MockTransport`;
the parser tests use authentic pruned table/JSON captures. Algorithm edge cases
and malformed responses are explicit synthetic mutations, not claimed real data.
No unit test depends on a live count. The manual `source smoke` operation checks
robots, the HTML shell, and one complete JSON response without writing artifacts.
See the M01 plan for the full acceptance sequence and recorded results.

## M02 raw document acquisition

Use the authentic M01 artifacts without rediscovering or reselecting projects:

```powershell
uv run python -m msmeintel download run --sample config/sample_20.json --discovery data/discovery/pmegp.json --manifest data/downloads/sample_20.json
uv run python -m msmeintel download list --manifest data/downloads/sample_20.json
uv run python -m msmeintel download verify --manifest data/downloads/sample_20.json
uv run python -m msmeintel download retry-failed --manifest data/downloads/sample_20.json
```

`run` and `retry-failed` are explicitly LIVE when network work is needed. `list`
and `verify` are offline. The downloader validates the selected observations
against full discovery and preserves their original links, variants, record keys
and source IDs (PSRID for PMEGP). It knows no PMEGP HTML/API fields. Each distinct
canonical URL has one receipt with all its project associations; different URLs
with identical bytes share one physical file.

Original response bytes are streamed unchanged, hashed and stored at
`$MSMEINTEL_DATA_DIR/raw/<first-two-hash-chars>/<sha256>.pdf`. Server filenames
never determine local paths. SHA-256 publication is atomic and no-clobber. The
pretty JSON manifest checkpoints `DOWNLOAD_PENDING`, `STAGED`, `DOWNLOADED` or
`DOWNLOAD_FAILED` per URL, with acquisition/verification times and categorized
errors. Failed downloads are never successful receipts; earlier successes survive.

The client uses verified TLS, a descriptive user-agent, sequential requests,
minimum one-second pacing, stricter supported robots pacing, 10-second connect /
30-second other HTTP timeouts, a 120-second per-attempt streaming limit, and up
to three transient-error attempts with backoff. Retry-After is honored; long
waits defer the origin and persist its not-before time. Robots 404/410 means no
published policy, not unrestricted permission or a content-reuse license.
Ambiguous restrictions, challenges, cross-origin redirects and authentication
requirements are not bypassed. Same-origin redirects are limited to three hops.

Only HTTP 200 is accepted. Validation checks MIME, a PDF version signature,
an EOF marker in the last 1 KiB, complete transfer, declared/actual length and
a 50 MiB size cap. Missing/generic binary MIME is recorded as a warning and still
requires PDF byte checks. These checks do not establish that a PDF opens, is safe
to execute or contains usable text. No document content is executed or parsed.

### Reruns and recovery

Repeat the identical `download run` command. Every existing success is rehashed
before reuse; a fully cached run makes no HTTP requests, even to robots. Its
acquisition time and original bytes remain unchanged. This verifies the local
snapshot, not remote freshness. Ordinary runs leave terminal failures visible;
`retry-failed` retries failed URLs without redownloading successful ones.

An interrupted partial transfer restarts from byte zero. A durable `STAGED`
receipt resumes publication or adopts its verified final file without HTTP.
Only application-owned temporary files referenced by receipts are cleaned up.
A missing saved artifact can be refetched only if its hash matches; corrupt
immutable files are reported and left untouched for explicit manual recovery.
Do not delete raw files or rewrite receipts to hide an integrity error.

One local writer at a time is supported. Atomic hard-link publication must be
available on the raw filesystem; failures surface without unsafe copy/overwrite
fallbacks. Receipt replacement briefly retries transient Windows sharing locks;
persistent storage errors stop the run and retain durable recovery information.

Download commands exit 0 for fully stored/verified selections, 1 for per-URL
failures or unfinished work, and 2 for invalid input/configuration or storage
failure. Verification exits nonzero for missing/corrupt artifacts or unfinished
receipts; explicitly unavailable URLs remain reported separately from good files.

### Counts and local-only artifacts

Summaries distinguish projects, associations, unique URLs, duplicate URL
associations, URLs attempted, HTTP attempts, downloaded URLs, verified skips,
staged recoveries, failed URLs, successful URLs, unique hashes, new files,
content deduplications and storage bytes. HTTP attempts include retries and
redirects but exclude robots. A shared URL is one transfer; duplicate content
can be multiple successful transfers but only one physical file. Storage bytes
count each successfully referenced hash once, not once per project.

Generated PDFs/receipts stay under the ignored `data/` directory. Government
content redistribution/republication remains **REVIEW REQUIRED**; no source
license is inferred from public access. Tests use an explicitly synthetic blank
PDF and MockTransport under the existing socket/DNS guard, never live PDFs or
fabricated replacements. No dependency, database table or M03 processing is added.

## M03 native PDF text and layout

These commands are entirely offline and consume the existing M02 receipt:

```powershell
uv sync --locked
uv run python -m msmeintel extract run --manifest data/downloads/sample_20.json
uv run python -m msmeintel extract verify --manifest data/downloads/sample_20.json
uv run python -m msmeintel extract run --manifest data/downloads/sample_20.json
uv run pytest tests/test_extraction.py
```

Only `DOWNLOADED` files are inputs. The 17 authentic raw hashes are verified
before parsing/reuse and after parsing. M02's failures for PSRIDs **716, 680 and
700** remain excluded source-format exceptions, with their original associations
and errors retained; no archive is unpacked and no replacement is fabricated.
Different URLs/projects sharing a hash share one extraction. The downloader,
discovery manifests, sample, and original PDF bytes are never modified.

Outputs beneath `$MSMEINTEL_DATA_DIR` (default `data`):

- `work/native/<sha256>.json`: schema, original SHA/path/size, parser versions and
  options, timestamp, classification/status, page count and page results.
- `work/native/manifest.json`: original source URLs and project associations
  grouped by raw hash, excluded download receipts, output checksums, per-document
  status/errors/page counts, and last-run summary.

Every enumerated page has a **1-based physical PDF page index**, native `text`,
ordered `words` (`text`, `x0`, `top`, `x1`, `bottom`, `upright`), word/non-whitespace
character counts, dimensions, bbox, rotation, image count, method, status and
error. Coordinates are PDF points (1/72 inch); x is measured from the left and
top/bottom from the top in pdfplumber's page coordinate space. The original page
bbox is retained, including nonzero origins. No word boxes are inferred from
plain text. No Unicode/financial normalization is performed. OCR-used is false
and OCR confidence is null.

Native text uses pdfplumber's geometric reading order, `layout=False`,
`use_text_flow=False` and x/y tolerances of 3. It is a reading-order approximation,
not semantic layout or reconstructed tables. Multi-column text, wrapped table
cells, fonts/ligatures, hidden text and pre-existing OCR layers can be misleading.
Page numbers do not claim to match printed page labels. At fewer than 80
non-whitespace characters, a page is `OCR_REQUIRED`, preserving any native text.
Blank/sparse pages also meet that heuristic; the flag does not prove a scan.
Enough text does not establish correctness or recover text inside embedded images.

Document classification is `TEXT_PDF` (all pages sufficient), `SCANNED_PDF` (all
insufficient, scan-candidate heuristic only), or `MIXED_PDF` (both). Unknown/error
documents have null classification. Statuses distinguish `TEXT_EXTRACTED`,
`OCR_REQUIRED`, `PARTIAL` (some pages failed) and `FAILED`. Exceptions record stage
and exception type, not arbitrary PDF-supplied error bodies. Encrypted/restricted
PDFs are reported without password bypass; failed page enumeration can leave the
page count unknown. A page failure does not silently discard successful pages.

Derived files are flushed/fsynced and atomically replaced with bounded retries
for transient Windows sharing locks. One local writer is supported. Reruns rehash
raw and derived bytes and reuse only completed outputs with matching pypdf,
pdfplumber, pdfminer.six and local algorithm versions/options. Missing/corrupted
outputs, changed versions and partial/failed extraction are reprocessed; raw
corruption is reported and never repaired. Resume is per document: an interrupted
current document restarts, while checkpointed successes are reused. Temporary
files left by a hard process kill are not receipts and are never reused.

`verify` checks both hashes, parser identity, coverage/page totals and original
associations. Exit 0 means native processing/verification completed; OCR flags and
excluded M02 failures remain explicit. Exit 1 means a processing/integrity failure;
exit 2 means invalid input/configuration or local storage error. Summaries separate
attempted/reused/processed/partial/failed PDFs and total/processed/text/sufficient/
OCR/error pages. Pages with some text may also require OCR, so those counts overlap.

M03 acceptance observed **17 PDFs, 101 pages with sufficient native text, zero
OCR flags and zero extraction errors**. Three genuine pages were rendered only
for manual acceptance: Bakery Products page 1, Book Binding page 2 and Hand Made
Paper from Waste page 2. Text and physical page references matched; table cell
wrapping still loses semantic column structure. Tiny verified snippets are in
`tests/fixtures/extraction/golden.json`. The authentic-corpus test stays offline
and explicitly skips when local corpus files are absent. All ordinary tests keep
the existing network prohibition.

There are no schema/migration/new environment-variable changes. Only the specified
pypdf/pdfplumber dependencies and required transitives were added; see the license
inventory. The sequential parsers do not execute scripts or attachments but are
not a hard CPU/memory sandbox. The existing 50 MiB input limit and per-page cache
release apply. Government full text/PDF redistribution remains REVIEW REQUIRED.
M04 OCR and table work has not started.

## M04 work in progress — NOT ACCEPTED

See `docs/MASTER_EXECUTION_LOG.md` for the mandatory gate and actual failures.
M05–M09 must not start until M04 is accepted. The new commands are available for
inspection/debugging; their successful exit does not establish whole-corpus table
accuracy or prove real OCR works on this machine.

```powershell
uv run python -m msmeintel pages run --manifest data/downloads/sample_20.json
uv run python -m msmeintel pages verify --manifest data/downloads/sample_20.json
uv run python scripts/check_m04_ocr.py
```

The service consumes verified M03 artifacts, preserving native text and original
PDFs unchanged. It stores native tables as raw row arrays with cell bounding boxes,
page/table indices, null/empty cells, heuristic header candidates and explicit
quality flags. Single-column decorations, sparse/merged cells, multiline cells
and possible page-edge continuation remain review items, not normalized facts.
Tables are not merged across pages. No numeric cell text is repaired.

Outputs use `data/work/pages/<recipe-hash-prefix>/<recipe-hash>.json` plus
`data/work/pages/manifest.json`. The full recipe hash binds the original SHA-256,
native-output hash, parser versions, OCR engine/language-data hashes and settings.
This shorter layout works with Windows path-length limits. Previous-version
outputs stay on disk. Atomic checkpoints support document-level resume and
verified reuse. One writer is supported. Raw/native corruption fails the input
gate rather than being silently repaired.

OCR is selected per page using `--min-native-chars` (80), `--min-native-words`
(10) and `--min-printable-ratio` (0.95). English is the default `--language`.
OCR-derived words/text and confidence remain separate from native output; no
image-only table grid is invented. Rendering is 300 DPI with a 40-million-pixel
cap; Tesseract runs without a shell and with a 60-second timeout. Native parsers
still have no hard CPU/memory sandbox. `MSMEINTEL_TESSERACT` can name an approved
local executable; otherwise PATH and the standard Windows location are checked.
The selected trained language data must also be installed.

Current partial acceptance: 17 PDFs / 101 pages produced 117 table candidates;
71 pages have review flags. The three M02 source exceptions remain represented.
No real corpus page was selected for OCR. Tesseract installation failed with a
download timeout (`0x80072ee2`), and real OCR acceptance reports
`OCR_RUNTIME_UNAVAILABLE`. The manually verified PSRID 709 page-10 four-column
machinery table also fails its golden check because pdfplumber produces an extra
empty column. That assertion remains unchanged and failing; this is an unresolved
layout-quality defect, not an accepted source exception. Do not use these candidate
tables as validated business facts. The master gate stops at M04.

