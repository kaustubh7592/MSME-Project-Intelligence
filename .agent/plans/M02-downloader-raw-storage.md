# M02 — Downloader and immutable raw document storage

Planning checkpoint: 2026-10-08. Awaiting approval; no M02 application code or
document downloads have been performed. M00 and M01 remain accepted and frozen.

## Goal

Download every distinct document URL in the authentic M01 representative sample,
preserve every project/link observation, and keep verified original bytes in an
immutable SHA-256 store. Make interrupted runs resumable and individual failures
visible without discarding successes. Stop at raw acquisition; do not start M03.

## In scope

- Generic, sequential httpx downloads from validated M01 manifests.
- Conservative access-policy checks, bounded retries/timeouts and streamed PDF checks.
- Content-addressed storage, atomic publication/checkpoints, local integrity verification.
- Inspectable JSON download receipts, association retention, accurate counts and retry-failed.
- Small CLI additions, offline tests and separate real-sample acceptance operations.

## Out of scope

No rediscovery, reselection, edits to completed milestone plans or M01 artifacts,
`bootstrap_20.json`, additional sources, generalized crawler/storage framework,
parallel workers, queues, Docker, database domain tables or migrations. No PDF
library, page enumeration, text extraction, classification, rendering, OCR,
tables, business facts, LLM, embeddings, API or UI. No remote-change polling,
conditional revalidation, force-refresh feature, byte-range resume, public PDF
redistribution, raw-file deletion or automatic repair of corrupt immutable files.

## Existing code/context inspected

- `AGENTS.md`, `.agent/PLANS.md`, the complete `docs/TECHNICAL_SPEC.md`,
  `docs/IMPLEMENTATION_ROADMAP.md` and `docs/DECISIONS.md`.
- Existing M00/M01 acceptance and outcome sections; `README.md`,
  `THIRD_PARTY_LICENSES.md`, `pyproject.toml` and `.gitignore`.
- `src/msmeintel/{cli,config,discovery}.py` and `sources/{base,pmegp}.py`;
  `tests/conftest.py`, `tests/test_skeleton.py`, relevant discovery tests and
  `tests/fixtures/pmegp/README.md`.
- Actual `data/discovery/pmegp.json` and `config/sample_20.json`, including their
  identities, document observations and cross-artifact consistency.

The saved full discovery contains 1,024 project records/associations and **983
case-sensitive distinct canonical document URLs**. The sample contains 20
projects, 20 associations and 20 distinct URLs; every selected identity and
document observation matches the full manifest. These are inspected artifact
counts, never implementation constants. URL path/query case must not be folded.

M01 already stores absolute `url`, `canonical_url`, original relative
`original_href`, `found_on_url`, title/type and `original_variants` per document.
`external_project_id` is the string form of PMEGP's PSRID. Its document URLs use
the observed `/Home/DownloadDocument?fileName=...` route. M02 consumes those URLs
verbatim; it neither reconstructs DocPath links nor calls the discovery API.

M01 recorded robots 404 on 2026-10-08, but did not request PDF bodies or HEADs.
Document availability, response MIME, redirects, lengths and content hashes
remain unverified. No `data/raw/` directory exists at this planning checkpoint.

## Design

### Small code flow and input boundary

Use `discovery.read_manifest`, `read_sample`, `json_text` and the existing generic
`sources.base.canonicalize_url`; keep M01 behavior unchanged. Two new ordinary
modules suffice: `downloads.py` for acquisition/receipts and `raw_storage.py`
for byte validation/publication/verification. No repository classes or adapter
registry. The downloader must not import `sources.pmegp` or use PMEGP field names.

Before any HTTP or output replacement, require a complete discovery snapshot and
valid sample from the same source. Match each selected record key, external ID
and entire document-observation list against discovery. A stale/mismatched
selection fails explicitly; do not silently change its URLs or resample. Group
work by canonical URL, preserving each project's complete document observation,
including every original variant. Process URLs in deterministic sorted order.
Different URL strings remain different work items even if the server might treat
them as aliases; identical bytes are deduplicated only after hashing.

Reuse `MSMEINTEL_DATA_DIR` for the raw root. Download manifest paths are explicit
CLI arguments. Reject output aliases of the sample/discovery inputs, invalid
existing JSON, incompatible source/selection, unsafe paths and duplicate JSON
keys without replacing existing data. Ordinary reruns use the saved acquisition
snapshot; no live discovery is required. Keep configuration and dependencies unchanged.

### HTTP, access controls and validation

- One synchronous client, verified TLS, no authentication or browser automation.
  User-agent: `MSMEIntel/0.1 (local learning project; document acquisition)`.
  GET only; no preliminary HEAD. Request `Accept-Encoding: identity`; reject
  unexpected content encoding rather than transforming raw bytes.
- Accept only validated HTTP(S) candidates on the discovery source's origin;
  reject credentials, local/private literal hosts and non-HTTP schemes. No
  automatic redirects: at most three same-origin hops, checking each target and
  robots before requesting it. Reject loops, cross-origin destinations and TLS
  downgrade; retain the final URL separately. This is a local operator tool,
  not a public arbitrary-URL fetch service or a new DNS-security framework.
- Fetch that origin's `/robots.txt` once when network work is actually needed,
  with a 512 KiB cap. A 404/410 means no published policy, **not** unrestricted
  permission or a reuse license. On 200 require a recognizable text policy;
  use stdlib `RobotFileParser` with conservative rejection of unsupported or
  ambiguous restrictions (including wildcard/precedence/group cases it cannot
  safely enforce). Other unresolved responses fail closed for that origin.
  This small generic policy check stays in `downloads.py`, not the PMEGP adapter;
  do not move/refactor frozen M01 code merely to share it.
- Request starts at least one second apart, including robots, redirects and
  retries; honor stricter supported crawl-delay/request-rate. Connect timeout
  10 seconds, read/write/pool timeout 30 seconds, plus a 120-second elapsed cap
  per document attempt checked during streaming. Defaults are named constants,
  not a new configuration system.
- At most three attempts per URL for transient transport/timeouts, HTTP 408,
  429, 500, 502, 503 and 504; exponential delays 1 then 2 seconds, combined with
  pacing and valid Retry-After seconds/HTTP dates. Never shorten Retry-After.
  If it exceeds 60 seconds, defer further origin requests for this run and
  record retryable failures; persist the not-before time for subsequent runs.
  Exhausted 429 likewise stops further requests to that origin for this run.
  Do not retry 401/403/404/410, challenges, invalid MIME/PDF or size violations.
  Never bypass access restrictions; one document failure otherwise leaves the
  remaining documents eligible to run.
- Require HTTP 200, not 204/206 or a redirect body. Accept `application/pdf`;
  missing MIME or `application/octet-stream` may pass only with valid PDF byte
  checks and a recorded warning. Reject explicit HTML/JSON/other MIME unread.
  Enforce 50 MiB both against declared Content-Length and counted streamed bytes;
  reject malformed/conflicting lengths and any declared/actual length mismatch.
- Basic integrity means nonempty bytes, `%PDF-` version header at the start and
  `%%EOF` in the final 1 KiB, plus complete HTTP transfer and length checks.
  These detect common error/truncation responses; they do **not** prove full PDF
  structural validity or safety. No xref/page parser or embedded content execution.
  A rejected real source file is reported, never silently rewritten to pass.

### Immutable storage and interruption recovery

Stream chunks to an exclusively created, application-owned `.part` file under
`data/raw/.tmp/` (same filesystem as the final store), counting bytes and computing
SHA-256 incrementally. Ignore server filenames for filesystem paths. Keep only
bounded header/trailer buffers; do not load a complete PDF into memory.

After checks, flush/fsync/close the temporary file. Atomically checkpoint its
hash, byte count, timestamp and staging filename with status `STAGED` **before**
publishing it as `data/raw/<first-two-hash-chars>/<sha256>.pdf`. Use an atomic
no-clobber filesystem operation; never `os.replace` an existing raw artifact.
If the hash path exists, rehash/check it before reuse and remove only the owned
temporary duplicate. An unavailable safe publication operation is a storage
error, not permission to overwrite or expose a partially copied final file.

Checkpoint `DOWNLOADED` only after final-file verification. Store JSON using
closed/flushed same-directory temporary files and atomic replacement, following
M01's pattern without changing its private helpers. Persist each URL outcome;
failure to persist a receipt is a run-level error and stops further acquisition
without destroying earlier receipts/files. Raw paths are derived from validated
hashes, relative to the data root; reject traversal/symlink escapes in existing
manifests and directories. Support one writer at a time, as M01 does; no workers
or locking subsystem is introduced.

On rerun, rehash and validate every previously stored artifact before skipping
it. Reuse verified files with **no HTTP at all**, including no robots request if
there is no remaining network work. This verifies local unchanged content, not
that the remote server still serves the same bytes. Acquisition timestamps stay
unchanged on skips; record a separate verification time.

Recover a `STAGED` receipt from its verified final file, or publish its verified
complete staging file, without downloading again. Restart incomplete transfers
from byte zero; no Range requests or concatenation. Clean only validated,
application-owned temporary files, never arbitrary files or final artifacts.
A missing previously stored file can be fetched again, but must match its saved
hash; changed bytes are an explicit integrity failure, not a replacement receipt.
A corrupt existing hash path is reported and left untouched for manual recovery;
do not bless it as a skip, overwrite it or delete the evidence. Test crash points
before/after staging and publication as well as interrupted network streams.

### JSON receipt model and counts

Default acceptance output: `data/downloads/sample_20.json`, UTF-8 pretty JSON,
schema version 1. It is generated data under the already-ignored `data/` tree.

- Envelope: `schema_version`, `source_key`, `source_url`, `inputs` (input paths,
  SHA-256 fingerprints and discovery timestamp), `created_at`, `updated_at`,
  `documents`, and `last_run` (UTC start/end, completion flag and summary).
  Input fingerprints are provenance, not a hard-coded expected dataset hash.
- Each `documents` item: `canonical_url`, `associations`, `status`, `sha256`,
  `storage_path`, `byte_count`, `downloaded_at`, `verified_at`, `final_url`,
  `content_type`, `http_status`, `attempts`, `warnings`, nullable `error`,
  nullable `staging_path` and nullable `retry_not_before`.
- Each association: `record_key`, `external_project_id` (PSRID for PMEGP),
  `raw_title`, and `document` containing the **unaltered M01 document observation**
  (`original_href`, absolute original `url`, canonical URL, found-on URL,
  title/type, original variants). One URL receipt may contain many associations.
- States: `DOWNLOAD_PENDING`, `STAGED`, `DOWNLOADED`, `DOWNLOAD_FAILED`.
  New records have absent/null artifact fields until known. Errors record a
  category, short sanitized message, timestamp and retryability; do not persist
  response bodies, cookies, proxy credentials or raw exception strings.
  Retain known receipt/hash information on integrity failure instead of erasing it.

Print/save separate counts: projects, project-document associations, unique URLs,
duplicate URL associations (`associations - unique URLs`), distinct URLs attempted
this run, HTTP document attempts (including retry/hop requests, excluding robots),
downloaded URLs this run, verified skips, recovered staged URLs, unresolved failed
URLs, successful stored URLs, unique stored hashes, newly published files, and
content-duplicate URLs (`successful stored URLs - unique hashes`). A successfully
downloaded duplicate is still a successful URL, but not a new physical file.
Also report this-run content deduplications. A retry that succeeds is not a failed
URL; multiple projects sharing a failed URL are listed but not counted as multiple
failed transfers. No stored summary may contradict the underlying receipts.

### CLI contract

Add one Typer `download` group; keep handlers thin:

- `download run --sample PATH --discovery PATH --manifest PATH`: explicitly LIVE
  when needed; create/resume selected pending work, verify/reuse successes and
  recover interrupted work. Leave terminal failures visible for `retry-failed`.
- `download retry-failed --manifest PATH`: explicitly LIVE; retry only failed URL
  receipts, respecting policy and persisted backoff; never redownload successes.
  Integrity conflicts remain blocked, not silently repaired.
- `download list --manifest PATH`: OFFLINE; JSON summary and failed URL/PSRID/error
  details, with the manifest itself providing the full association inventory.
- `download verify --manifest PATH`: OFFLINE; validate schema/associations,
  hash-derived paths and all referenced stored artifacts, byte counts and PDF
  checks. Report unavailable URLs separately; unfinished states are not complete.

Download operations exit 0 when all selected URLs are stored/verified, 1 for
persisted per-URL failures, and 2 for invalid input/configuration or run-level
storage failures. Offline verification exits nonzero on corrupt/missing artifacts,
invalid manifests or unfinished recovery; explicitly recorded unavailable URLs
alone do not invalidate good artifacts, and must remain visible in its output.

## File changes

| Exact path | Change |
|---|---|
| `.agent/plans/M02-downloader-raw-storage.md` | Create this plan now; update Progress/Outcome during approved implementation. |
| `src/msmeintel/downloads.py` | Create input mapping, sequential HTTP/policy/retries, JSON receipt persistence, summaries and service functions. |
| `src/msmeintel/raw_storage.py` | Create bounded byte checks, hash paths, safe staging/publication and local verification. |
| `src/msmeintel/cli.py` | Add the four download commands; leave health/source behavior unchanged. |
| `tests/test_downloads.py` | Create offline service/storage/CLI tests using MockTransport, temporary directories and controlled clocks. |
| `tests/fixtures/downloads/minimal.pdf` | Create a tiny valid, script/attachment-free **synthetic** PDF for offline byte tests, never a PMEGP substitute. |
| `tests/fixtures/downloads/README.md` | Document synthetic provenance, byte integrity and derived malformed test cases. |
| `README.md` | Add M02 commands, statuses/count definitions, recovery limits, live/offline distinction and local-only storage/reuse warning. |

Generated during approved acceptance only: `data/downloads/sample_20.json`,
`data/raw/<prefix>/<sha256>.pdf`, and transient owned `data/raw/.tmp/*.part` files
(plus short-lived JSON checkpoint files). No generated PDFs are committed.
No dependency, lockfile, settings, license-inventory, M01 adapter/fixture/artifact
or export changes are needed. Existing source-content reuse review remains in force.

## Database changes

None. M02's roadmap requires download persistence, not PostgreSQL domain tables.
JSON associations implement the required many-to-many provenance at this stage;
SQLAlchemy metadata and Alembic heads remain empty.

## Implementation steps

1. Add input/receipt validation and the offline synthetic PDF fixture/tests.
   Verify selection matching, shared URLs and complete original-link preservation.
2. Implement and test raw staging, bounded checks, SHA-256 publication, duplicate
   reuse, corruption detection and crash recovery before adding real HTTP.
3. Add generic HTTP policy/streaming/retries and per-URL checkpoint orchestration
   against MockTransport. Add accurate summaries and explicit retry-failed behavior.
4. Wire the CLI, add CLI regressions and README instructions. Run the offline gate;
   repair implementation failures without adding later-milestone features.
5. After approval, run real-sample acquisition, inspect every failed URL, verify
   stored hashes/associations, retry eligible failures once via the command, and
   rerun to demonstrate verified-success reuse. Record first/rerun summaries.
6. Rerun regressions, record results/deviations/blockers in this plan and stop.

## Tests

All new tests run under the existing autouse socket/DNS guard. Use httpx
MockTransport, controlled streams/clocks/sleep and temporary directories; do not
require the ignored full live manifest, site access or real government PDFs.

- Valid PDF round-trip preserves exact bytes/hash; absent/octet-stream MIME
  warning; wrong MIME/signature, HTML with PDF MIME, truncated/missing EOF,
  empty body, length mismatch, declared/streamed oversize and slow streams fail.
- HTTP errors/non-200 responses, transient success/exhaustion, timeouts midstream,
  bounded backoff/Retry-After (including cross-run not-before), origin pacing,
  robots absent/allow/deny/ambiguous/failure, challenges and redirect restrictions.
- Shared URL across projects makes one transfer with all original observations;
  multiple documents for one project remain separate. Two URLs with identical
  bytes produce two receipts but one file. Case-sensitive URLs remain distinct.
- Interrupted transfer, interruption before/after staging/publication/checkpoint,
  safe temporary cleanup, interrupted manifest replacement and persistence error:
  previous successes survive and rerun recovers without duplicate physical storage.
- Identical second run makes zero HTTP calls, preserves bytes/mtime/acquisition
  time and reports skips. Missing/corrupt existing files are not silently reused;
  no corrupt destination is overwritten and a changed refetch cannot replace a receipt.
- Invalid/ambiguous manifest, input/output alias, stale sample, changed selection,
  tampered hash/path and traversal/symlink escape fail safely. Retry-failed targets
  only failures. Verify/list never use HTTP; safe errors never expose credentials.
- CLI counts reconcile for mixed successes/failures/skips/recovery/duplicate URLs
  and content. Vary synthetic project/document counts; no count is hard-coded.
  Keep the existing M00/M01 suite and network guard intact.

## Acceptance commands

Run from the inner repository root containing `pyproject.toml`, using the default
`MSMEINTEL_DATA_DIR=./data`. These commands are for the approved implementation,
not this planning turn. An uncached `uv sync` may need dependency-network access;
pytest and all offline commands must not.

### Offline gate — every command exits 0

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
uv run python -m msmeintel source list --source pmegp --limit 20
```

Require all M00/M01/M02 tests passing, installed src package, no database contact
and empty Alembic heads. Do not rerun live discovery or overwrite the fixed sample
to demonstrate M02 regressions; the existing offline suite covers those behaviors.

### Explicit live acquisition, recovery and rerun

```powershell
uv run python -m msmeintel download run --sample config/sample_20.json --discovery data/discovery/pmegp.json --manifest data/downloads/sample_20.json
uv run python -m msmeintel download list --manifest data/downloads/sample_20.json
uv run python -m msmeintel download verify --manifest data/downloads/sample_20.json
uv run python -m msmeintel download retry-failed --manifest data/downloads/sample_20.json
uv run python -m msmeintel download run --sample config/sample_20.json --discovery data/discovery/pmegp.json --manifest data/downloads/sample_20.json
uv run python -m msmeintel download list --manifest data/downloads/sample_20.json
uv run python -m msmeintel download verify --manifest data/downloads/sample_20.json
```

Read each command's exit status. Exit 1 from acquisition is not a fully successful
download run: list each unavailable PSRID/URL/reason explicitly. Genuine unavailable
documents may remain documented exceptions, as requested; implementation errors,
corruption or source-wide access blocking are not acceptance passes. All reachable
sample documents must be stored. Record actual counts rather than assuming 20
hashes or zero content duplicates. After retries finish, the final ordinary rerun
must attempt zero URLs, download zero bodies, publish zero new files, preserve
every successful receipt and skip every verified success; unresolved failures
remain recorded, not erased. Record both first-run and rerun summaries in Outcome.

Run this independent offline association/hash check in PowerShell after the final
verification (the installed package validators are covered separately by pytest):

```powershell
@'
import hashlib
import json
from pathlib import Path
sample_path = Path("config/sample_20.json")
full_path = Path("data/discovery/pmegp.json")
sample = json.loads(sample_path.read_text(encoding="utf-8"))
result = json.loads(Path("data/downloads/sample_20.json").read_text(encoding="utf-8"))
encode = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False)
expected = {(p["record_key"], p["external_project_id"], p["raw_title"], encode(d))
            for p in sample["projects"] for d in p["documents"]}
actual = [(a["record_key"], a["external_project_id"], a["raw_title"], encode(a["document"]))
          for d in result["documents"] for a in d["associations"]]
assert len(sample["projects"]) == 20
assert len(actual) == len(expected) and set(actual) == expected
urls = [d["canonical_url"] for d in result["documents"]]
assert len(urls) == len(set(urls))
assert set(urls) == {d["canonical_url"] for p in sample["projects"] for d in p["documents"]}
assert all(a["document"]["canonical_url"] == d["canonical_url"]
           for d in result["documents"] for a in d["associations"])
for d in result["documents"]:
    assert d["status"] in {"DOWNLOADED", "DOWNLOAD_FAILED"}
    if d["status"] == "DOWNLOAD_FAILED":
        assert d["error"]
        continue
    digest = d["sha256"]
    assert d["storage_path"] == f"raw/{digest[:2]}/{digest}.pdf"
    content = (Path("data") / d["storage_path"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == digest
    assert len(content) == d["byte_count"]
    assert content.startswith(b"%PDF-") and b"%%EOF" in content[-1024:]
assert result["last_run"]["summary"]["urls_attempted"] == 0
assert result["last_run"]["summary"]["downloaded"] == 0
assert result["last_run"]["summary"]["new_files"] == 0
assert hashlib.sha256(sample_path.read_bytes()).hexdigest() == "200de670fddb0a19c7b4aab72967ad709db261b5ed03675991f0e3e6ce51b0cd"
assert hashlib.sha256(full_path.read_bytes()).hexdigest() == "41204f5d053742a198e9a72f4da242ae3ed95d03200b5ff7d0b6e12b860da4b5"
print("Associations retained; stored bytes verified; rerun reused receipts; M01 inputs unchanged.")
'@ | uv run python -
```

The two input hashes above protect the actual frozen files inspected for this
plan; they are acceptance evidence only, never application constants. Finally
rerun `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .`.

## Risks and open questions

- No present architecture/dependency/input-integrity blocker and no additional
  design decision is required before implementation approval. The saved sample
  and discovery are consistent. The roadmap's M0/M1 status table is stale;
  the user's explicit acceptance governs, and M02 does not rewrite it.
- PDF routes have not been fetched. Access restrictions, redirects, unusually
  large/malformed documents or different MIME behavior must be reported from
  actual responses; never invent a successful file or weaken access/TLS checks.
- Source robots 404 is neither a prohibition by itself nor blanket permission.
  Recheck policy before live work. Source-wide denial/unavailability preventing
  the real acceptance run is a genuine blocker, not grounds for a source switch.
- Reuse rights for government content remain **REVIEW REQUIRED** before public
  redistribution/republication. M02 keeps PDFs local/ignored; no open license is
  assumed. No new software dependency or commercial runtime is needed.
- Signature/EOF/hash checks are acquisition integrity checks, not a guarantee
  that a PDF opens, is malware-free or contains usable text. Full parsing is M03.
- One writer and a local filesystem with safe atomic publication are assumed.
  Network/OneDrive interference or disk failure must surface as storage errors;
  corrupt immutable destinations require explicit manual recovery, not overwrite.
  Reruns do not establish remote freshness; they verify the saved local snapshot.

## Progress

- [x] Inspect required contracts, existing M01 code and authentic input artifacts.
- [x] Produce this single M02 planning pass; stop for approval.
- [x] Implement generic downloader, immutable store and durable receipts.
- [x] Add offline tests/CLI/documentation; pass M00/M01/M02 regressions.
- [x] Run real sample, retry failures, verify all stored hashes/associations; retain three invalid-source exceptions.
- [x] Demonstrate rerun reuse, record outcomes/deviations/blockers and stop before M03.
- [x] Revalidate all acceptance commands on 2026-10-09 and mark M02 complete with the three documented source-format exceptions.

## Outcome

**Status: COMPLETE — revalidated 2026-10-09, with three documented external
document exceptions.** This is completion of M02's acquisition/storage and
failure-handling acceptance criteria, not a claim of 20 successful PDFs.

Implemented on 2026-10-08 after approval. The design/acceptance sections above
were not revised. M02 functionality and regression checks are complete; the live
sample has **17 successful PDFs and three explicitly invalid source responses**,
not 20 successful downloads. No replacement data was fabricated. M03 was not started.

### Files and behavior delivered

Created `src/msmeintel/downloads.py`, `src/msmeintel/raw_storage.py`,
`tests/test_downloads.py`, `tests/fixtures/downloads/minimal.pdf` and
`tests/fixtures/downloads/README.md`. Changed `src/msmeintel/cli.py`, `README.md`
and only this plan's Progress/Outcome sections. The two small implementation
modules cover generic acquisition/receipts and immutable byte storage without
additional frameworks, dependencies, settings or database changes.

Generated `data/downloads/sample_20.json` and 17 hash-addressed PDFs under
`data/raw/`. These are ignored local artifacts. The staging directory is empty
after acceptance. Both frozen M01 inputs retain the exact fingerprints recorded
above; M00/M01 plans, adapter, discovery implementation and tests were not changed.

Acquisition keeps all original/canonical links and project associations, checks
policy/HTTP/MIME/signature/EOF/length/size, retries bounded transient failures,
persists explicit failures and recovers interrupted transfers/publications.
Atomic hard-link publication succeeded on this filesystem. Verified reruns
do not request documents or robots; raw bytes and acquisition times are retained.

### Real corpus and source exceptions

| Measurement | Initial acquisition | Explicit retry-failed | Final ordinary rerun |
|---|---:|---:|---:|
| Projects / retained associations | 20 / 20 | 20 / 20 | 20 / 20 |
| Distinct selected URLs | 20 | 20 | 20 |
| URLs attempted this run | 20 | 3 | 0 |
| Document HTTP requests this run | 20 | 3 | 0 |
| Successful new downloads | 17 | 0 | 0 |
| Verified skips | 0 | 17 | 17 |
| Unresolved failed URLs | 3 | 3 | 3 |
| New physical files | 17 | 0 | 0 |
| Stored unique hashes | 17 | 17 | 17 |
| Stored bytes | 2,442,368 | 2,442,368 | 2,442,368 |

There are no shared URLs or duplicate successful contents in this real sample;
offline tests demonstrate that shared URLs retain all associations and different
URLs returning identical bytes create only one physical file. Total storage is
2,442,368 bytes (approximately 2.33 MiB), excluding JSON receipts.

The following observed URLs failed the PDF signature check on both acquisition
and explicit retry. Each returned HTTP 200 and `application/pdf`, but a separate
policy-checked diagnostic that read only the first 16 bytes confirmed a
`50 4b 03 04` (`PK`/ZIP-style) prefix rather than `%PDF-`. These are source-format
exceptions, not successful PDFs. No archive was opened, extracted, converted or
stored as a valid raw PDF. The diagnostic added one bounded prefix request per
failed URL, separately from the 23 acquisition requests counted in receipts.

| PSRID | Observed project name | Declared response length |
|---|---|---:|
| 716 | PROJECT PROFILE FORAUTOMATIC COIR FIBRE DYEIG/BLEACHING UNIT ( COIR BOARD BASED INDUSTRY ) | 34,178 bytes |
| 680 | PROJECT PROFILE FOR AUTOMATIC COIR YARN DYEING/BLEACHING UNIT ( COIR BOARD BASED INDUSTRY ) | 35,457 bytes |
| 700 | PROJECT PROFILE FOR COIR PITH GROW BAG MAKING UNIT ( COIR BOARD BASED INDUSTRY ) | 35,610 bytes |

Their full original URLs, IDs, names, statuses and failure reasons remain in
`data/downloads/sample_20.json`. These three source responses prevent a complete
20-PDF set; they do not prevent the other 17 artifacts from being used as raw
inputs later. No source access control, TLS check or PDF validation was bypassed.

### Commands and verification results

- `uv sync --locked`: PASS; existing 31-package environment checked, no dependency changes.
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS; 24 Python files already formatted.
- `uv run pytest`: final PASS, **239 passed, 0 failed**, including all 116 existing
  M00/M01 tests and 123 M02 cases; ordinary tests retain the socket/DNS guard.
- Installed-package import, root help, `health`, `alembic heads`, source help,
  download help and `source list --source pmegp --limit 20`: all PASS/exit 0.
  Alembic remains empty; health does not contact PostgreSQL.
- All seven exact live/local CLI commands in Acceptance commands were executed.
  Initial acquisition, retry-failed and the ordinary rerun correctly exited **1**
  because the three failed URLs remain unresolved. These are not represented as
  fully successful download runs. Both `list` and both `verify` calls exited 0;
  verification reported all 17 hashes valid, zero integrity problems and the
  three source failures separately.
- The exact independent PowerShell/Python acceptance block passed: all 20
  original associations match, canonical URL identities are unique, all 17
  successful filenames/paths equal their SHA-256 values, lengths and PDF markers
  agree, rerun download/new-file/attempt counts are zero, and M01 inputs are unchanged.
- Additional filesystem comparison confirmed the same 17 filenames, sizes and
  modification timestamps before/after rerun; no partial files remain.

Offline coverage includes valid/invalid/ZIP-like PDF responses, generic/wrong
MIME, HTTP errors, Retry-After and pacing, timeout/retry exhaustion, unsafe URLs,
robots/redirect restrictions, shared URLs/content, dynamic counts, partial/staged/
published interruption recovery, lost staging files, atomic receipt failure,
corruption and hash-change refusal, safe paths, CLI exit codes and secret redaction.

The first M02 test run exposed two Windows `PermissionError` failures during
receipt replacement (101 passed, two failed). A bounded five-attempt retry of
atomic receipt replacement now tolerates temporary sharing locks without changing
permissions or discarding the prior receipt; permanent errors still stop safely.
Dedicated transient/permanent-lock tests pass. Subsequent full runs passed 221,
234 and finally 239 tests as additional boundary cases were added.

### Deviations, blockers and limits

No architecture, scope, dependency, database or frozen-plan design deviation.
The bounded Windows receipt-replacement retry is a normal implementation detail
driven by observed filesystem behavior. The only remaining corpus blockers are
the three source responses identified above; implementation functionality is not
blocked. Raw corruption, if encountered later, still requires explicit manual
recovery rather than destructive automatic repair.

Signature/EOF/hash checks do not establish full PDF structural validity, safety
or text quality; those later stages were not implemented. Government-content
redistribution/republication remains REVIEW REQUIRED. M03, extraction, OCR,
tables, AI, business facts, embeddings and domain tables remain out of scope.

### Revalidation and completion — 2026-10-09

The repeated implementation request was handled by inspecting and revalidating
the existing implementation, not recreating files or redownloading verified raw
bytes. No application/test/dependency/configuration change was needed. This pass
modified only this plan's Progress/Outcome and the generated
`data/downloads/sample_20.json` receipts (verification times, retry attempts,
failure observations and last-run summary). The frozen design and acceptance
commands remain unchanged.

All exact acceptance commands were rerun: locked sync; Ruff lint/format;
complete pytest; installed-package import; root/source/download help; health;
empty Alembic heads; saved source list; both download-run/list/verify sequences;
retry-failed; and the independent association/hash/frozen-input assertion block.
The final post-live regression gate reports **239 passed, 0 failed** (116 M00/M01
and 123 M02 tests), Ruff PASS and 24 files already formatted. The earlier full
test run in this pass also passed all 239 tests. No ordinary test used live HTTP.

The resume and final rerun each verified/skipped all 17 existing PDFs, attempted
zero URLs, downloaded zero bodies and created zero files. The explicitly live
retry attempted only the three failed URLs; PSRIDs 716, 680 and 700 again returned
HTTP 200 / `application/pdf` but failed the PDF version-signature check. Each now
has three recorded acquisition attempts across the two implementation sessions.
No alternate link, conversion or synthetic replacement was introduced.

Final corpus: **20 projects, 20 original associations, 20 distinct URLs, 17
successful documents, 17 unique raw PDFs, 2,442,368 bytes and three explicit
failures**. Both integrity commands passed with 17 verified hashes and zero
stored-artifact problems. The independent assertion block confirmed all original
associations and both frozen M01 fingerprints. A before/after comparison of 28
application/test/config/input/raw files confirmed unchanged hashes, lengths and
modification timestamps; the raw staging directory contains no files.

Download-run/retry-failed commands correctly exit 1 while these three source
failures remain; list/verify and the offline acceptance gate exit 0. The approved
plan explicitly permits documented unavailable-source exceptions, so M02 is
complete with those exceptions retained. There is no implementation blocker or
architectural deviation. A complete 20-PDF corpus still requires valid PDFs for
the three source records. M03 was not started; content redistribution review
and the existing raw-corruption/manual-recovery limits remain unchanged.
