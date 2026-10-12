# M01 - PMEGP discovery and representative 20-project corpus

Implementation status: **DONE**, 2026-10-08. The user corrected the primary source
to `https://pmegp.msme.gov.in/Home/ProjectDetailList`; see verified results in Outcome.
The original single-pass plan below is retained, with this source correction.

## Goal

Deliver a small PMEGP discovery layer that records currently published project entries and their document links, persists an inspectable local manifest, and selects a repeatable, representative 20-project input for later milestones. Discover the actual population from source responses; never assume 1,024 or any other population size.

This is the single planning pass, dated 2026-10-07. M00 is accepted and frozen. This turn creates only this plan. There is a source-access blocker: the current official listing and robots policy could not be retrieved during planning. The design below is concrete, but it must not be represented as a verified parser contract or a completed current-source sample until access is restored. Routine implementation details do not require replanning or another approval cycle.

## In scope

- The roadmap's small `SourceAdapter` contract and one `PMEGPAdapter`.
- Sequential official-site HTML discovery with robots checks, finite timeouts, conservative pacing, and separate fetch/parse functions.
- Source-supplied project metadata, original and canonical URLs, zero-to-many document-link associations, duplicate handling, timestamps, and discovery status.
- A local JSON manifest with safe replacement, repeat-run behavior, and explicit completeness.
- Deterministic category/pattern sampling, a real checked-in `config/sample_20.json`, and documented coverage limitations.
- Typer `source discover`, `source list`, `source sample`, and an explicitly live `source smoke` operation.
- Fixture-based and mocked-transport tests; normal pytest execution prevents internet access.
- Add only `httpx`, `beautifulsoup4`, and `lxml` plus their required transitive packages. Update their verified license inventory and M01 usage documentation.

## Out of scope

- PDF or other document-body downloads, PDF availability probes, file hashing/content-addressed storage, download retry machinery, PDF parsing/classification, OCR, tables, normalization, evidence extraction, or financial validation.
- PostgreSQL domain tables, migrations, repositories, database persistence, or model changes. The roadmap requires a persistent manifest but does not mandate a database for M1. Local JSON follows the user's explicit M01 instruction; PostgreSQL remains the later structured-facts destination.
- AI, embeddings, query assistant, API, UI, Docker, queues, workers, generalized crawling, plugin registries, additional source adapters, or future-stage placeholders.
- Inferring a sector/type, current profitability, document contents, or missing metadata from a project name.
- Refactoring accepted M00 behavior or changing the M00 plan, specification, roadmap, data dictionary, or accepted architecture decisions.

## Existing code/context inspected

Read `AGENTS.md`, `.agent/PLANS.md`, `docs/TECHNICAL_SPEC.md` in full, `docs/IMPLEMENTATION_ROADMAP.md`, `docs/DATA_DICTIONARY.md`, `docs/DECISIONS.md`, and the accepted `.agent/plans/M00-repository-skeleton.md`.

Inspected all six existing `src/msmeintel/*.py` files, `tests/test_skeleton.py`, `pyproject.toml`, the lockfile's header/dependency context, `.gitignore`, `.env.example`, `README.md`, `THIRD_PARTY_LICENSES.md`, `alembic.ini`, and the migration environment/template. The current implementation has a working Typer app, an environment settings loader, application logging, a lazy database engine, empty metadata, and nine M00 checks. There is no discovery code to reuse. Existing `data/` ignore rules already cover generated manifests.

The roadmap's M0 status text is stale; the user's acceptance and completed M00 plan govern. Do not reopen M00 or edit the roadmap during this task.

## Design

### Source evidence and access boundary

The official primary listing, corrected by the user on 2026-10-08, is:

`https://pmegp.msme.gov.in/Home/ProjectDetailList`

The original candidate was `https://www.kviconline.gov.in/pmegp/pmegpweb/docs/jsp/newprojectReports.jsp`, linked by the [Khordha District Industries Centre directory](https://khordha.odisha.gov.in/en/basic-page/list-project-profiles). It is no longer the primary source or a fallback. That directory's displayed count is not a discovered current total. The historical planning failures below refer to that older candidate, not the corrected source.

Current verification found an empty HTML table shell populated by public GET
`/Home/GetAllProjectDocuments`, with no parameters and client-side paging only.
Implementation uses the observed JSON feed while retaining the existing HTTP,
generic discovery, local-manifest, and sampling architecture. Detailed source
evidence, fixture provenance, field mapping, and acceptance results are in Outcome.

Planning observations on 2026-10-07:

- Web requests to the listing on both the www and non-www host returned timeouts. The official PMEGP portal home also timed out.
- Local read-only requests to both hosts' `robots.txt` failed with DNS timeout/resolution errors, including outside the filesystem sandbox. The initial sandbox attempt also encountered a local proxy failure. No successful robots response or current listing HTML was obtained.
- A historical [SVNIT PMEGP resource](https://www.svnit.ac.in/Unnat_Bharat/PI/pdf/Livelihood%20%26%20Entreprenurship/Schemes%20by%20Government%20of%20India/PMEGP%20Pradhan%20Mantri%20Employment%20Generation%20Programme/PMEGP%20Pradhan%20Mantri%20Employment%20Generation%20Programme.pdf), surfaced in search results only, describes industry filtering, project names, listing cost text, and profile links. This is a historical clue, not evidence of today's DOM, filter values, or complete population. No project PDF was opened or downloaded.
- Current CSS selectors, pagination/filter mechanics, external IDs, direct PDF versus detail links, categories, access restrictions, and source total are therefore unverified. Neither an outage nor a CAPTCHA prohibition can be concluded from these transport errors.

The first implementation activity is a bounded access check and actual HTML capture, not writing guessed selectors. Fetch the robots policy before automated listing traversal. If access is allowed, capture the unfiltered listing and only the continuation/detail HTML actually needed, with source URLs and capture times in fixture provenance. Inspect whether a default cost/category filter hides entries; use only the site's exposed unrestricted listing/filter controls. Do not guess ID ranges, invent a high cost ceiling, or call a filtered first page the whole corpus.

Use an observed heading/table/list structure in the adapter. Follow only observed listing continuations and project-detail HTML routes necessary to enumerate those entries; detect loops and incomplete traversal. Where the listing already contains document links, make no per-project request. A literal link embedded in markup may be parsed without executing JavaScript; do not add a browser runtime or call undocumented endpoints to work around access controls.

If the site remains inaccessible, record the failed checks and keep current-source parser verification, actual fixture capture, and the real sample blocked. Do not replace the source with a mirror, historical count, synthetic corpus, or third-party paid service.

### Minimal code flow

`CLI -> PMEGPAdapter (fetch HTML / pure parse) -> generic discovery merge -> JSON manifest -> offline list/sample`

Use small standard-library dataclasses for generic project/document candidates. Keep the roadmap-required adapter interface in `sources/base.py`, with discovery, document-link discovery, and URL canonicalization responsibilities. The PMEGP implementation supplies those operations; its parsing functions accept HTML and a page URL and never fetch data. Document discovery means extracting associated links, not retrieving their bodies.

Keep PMEGP URLs, selectors, category interpretation, and continuation rules in `sources/pmegp.py`. A single `discovery.py` module handles generic manifest, identity, merge, and sampling functions. Inject an adapter/client where required for tests; no registry, factory, ORM layer, or crawler framework.

Extend the current Typer app with a source command group. Reuse settings for `MSMEINTEL_DATA_DIR` and log level without changing the existing configuration contract or M00 health behavior. Database settings are never used to connect during discovery.

### HTTP behavior

- Use one synchronous `httpx.Client`, a descriptive `MSMEIntel/0.1` user-agent, verified TLS, and sequential requests. Default connect timeout is 10 seconds; other HTTP operation timeouts are 30 seconds.
- Wait at least one second between request starts, or longer if robots crawl-delay/request-rate requires it. Expose finite positive `--timeout` and `--request-delay` options for live commands; the delay cannot reduce the one-second/policy floor.
- Fetch robots once per contacted official origin. Use the standard-library robots parser for supported rules; an unsupported restrictive rule must not silently become permission. A genuine 404/410 means no published robots file; authentication errors, denial, 429, 5xx, transport failures, or an ambiguous/challenge response stop discovery.
- Validate permitted origin, route, scheme, and robots permission before each request/redirect. Do not automatically equate www/non-www, downgrade HTTPS, disable certificate validation, spoof identities, or evade a challenge.
- Never request a known document URL, even with HEAD. For allowed HTML routes, stream responses, check status and HTML content type before consuming content, and impose a modest HTML-size cap (5 MiB). An unexpected PDF/non-HTML response is closed unread and reported.
- Do not silently retry access denials or add a downloader/retry subsystem. Timeouts, HTTP errors, policy failures, and parser drift yield categorized CLI errors, a nonzero exit, and preservation of the previous good manifest.
- A complete traversal must be demonstrable from actual continuation/filter behavior. Partial results must not be published as a complete current corpus.

### Discovery data model

Store source observations, not canonical business facts. Generic candidate/manifest fields are:

| Field | Meaning |
|---|---|
| `source_key` | `pmegp`; explicit at manifest and sample level |
| `record_key` | Locally derived deterministic identity, explicitly not an official ID |
| `external_project_id` | Official stable ID only if exposed and verified; otherwise null; row serial number is not assumed stable |
| `title` | Source project/business name with surrounding/repeated whitespace cleaned; retain original visible text in raw metadata |
| `category_hint` | Explicit source category label only; otherwise null; no inferred canonical sector/type |
| `listing_url`, `canonical_listing_url` | Original source page carrying the observation and its canonical form |
| `page_url`, `canonical_page_url` | Actual individual detail page if present; otherwise null, rather than a fabricated detail URL |
| `raw_metadata` | Only other visible source labels/text that aid provenance or distinguish entries; e.g. an explicitly displayed cost stays raw text, never an M5 financial fact |
| `documents` | List of associated link observations, possibly empty |
| `first_seen_at`, `last_seen_at` | UTC ISO-8601 observation times; first seen survives matching reruns |
| `discovery_status` | `DISCOVERED` or `MISSING_DOCUMENT_LINK`; describes link discovery, not download success |

Each document link contains `original_href`, the resolved original `url`, `canonical_url`, nullable `title`, `found_on_url`, and nullable `declared_type` (a source/link hint, not verified MIME). Keep distinct original href variants when deduplicating one canonical URL. Associate documents within their project; a shared document never causes two businesses to merge.

Missing names or unsafe/malformed links produce issue entries with source page, row/location context, reason, and relevant raw text. Missing document links retain an otherwise identifiable project with an empty list and warning. Do not substitute invented values. If a recognizable project row cannot be represented/identified reliably, report incomplete discovery and preserve the previous full manifest rather than silently omitting it from the total. A structurally unrecognized page or silently truncated traversal is a run failure, not an empty successful manifest.

### Canonical URLs and duplicate identity

Use `urllib.parse` operations and the already required HTTP client, not a new URL library. Resolve relative links against the observed page, normalize scheme/host case and default ports, remove fragments, and encode literal path spaces without double-encoding existing escapes. Reject empty/fragment-only navigational hrefs, credentials in URLs, and non-HTTP(S) schemes. Preserve path case, meaningful trailing slashes, encoded reserved characters, and query values/order unless the real site establishes a safe source-specific equivalence. Canonicalization must be idempotent.

Prefer an official stable source ID for project identity, then a verified individual canonical detail URL. When neither exists, use a deterministic serialized tuple of logical listing identity, the source title/category, stable visible distinguishing metadata, and sorted canonical document URLs. Exclude timestamps, pagination position, and display serial numbers. Do not use title alone: similarly named variants must remain separate. This conservative fallback can treat changed metadata/link sets as a new observation; document that limitation instead of inventing semantic merging.

Collapse exact duplicate observations and duplicate links deterministically. If a supposedly unique ID/detail URL has conflicting records within one run, report a conflict and preserve the previous manifest rather than choose a record silently. Changes across successful runs are dated latest observations; report added/changed/no-longer-seen keys.

### JSON manifest and safe reruns

Use pretty-printed UTF-8 JSON at `data/discovery/pmegp.json` by default (under `MSMEINTEL_DATA_DIR`), with keys/records/documents in deterministic order. JSON is sufficient for this in-memory metadata collection and easier to inspect atomically than an append-only event log.

Envelope: `schema_version: 1`, `source_key`, starting `source_url`, `discovered_at`, `scope` (`full`, `limit`, or `sample`), `complete`, `discovered_total`, `projects`, and `issues`. The total comes from deduplicated entries across a verified full traversal, never from a hard-coded or directory-advertised number. CLI summaries distinguish discovered population, saved project count, project-document associations, and unique document URLs.

On a successful full run, merge matching `first_seen_at` values from the previous valid manifest, update `last_seen_at`, and replace the current snapshot. Report removed keys as not seen in this successful snapshot, not proof of permanent source deletion. No history database is required. Reject unreadable/invalid existing JSON before replacement.

Write to a temporary file in the destination directory, close it, then use `os.replace`. A failed fetch, parse, merge, validation, or write must leave the old manifest intact. M01 is single-process; simultaneous discovery writers are unsupported and documented, without adding locks/workers.

`--limit N` and `--sample PATH` are mutually exclusive output filters after full HTML enumeration, so they do not masquerade as representative selection or reduce the reported dynamic source total. They require an explicit `--output` different from the full-manifest path, set `complete: false`, and cannot overwrite the full snapshot. A sample selector file must resolve every selected key or fail visibly. The sampler requires a complete, unfiltered manifest.

### Deterministic representative 20

Select from all deduplicated projects with at least one valid document URL. Do not claim to know whether those PDFs are text/scanned, reachable, or suitable golden evidence in M01. Those checks belong to M2-M5.

1. Group by the exact explicit source category, with a separate missing-category bucket. Do not infer categories from names.
2. Within each category, group by observable link pattern: direct listing document links versus links found on a detail page, and single versus multiple distinct document URLs.
3. Sort category and pattern keys deterministically. Sort candidates within a pattern by canonical identity. Cycle categories evenly, cycling their nonempty pattern buckets on successive visits, until 20 distinct projects are selected. Choose candidates distributed across each bucket's sorted range for its allocated quota rather than repeatedly taking its alphabetical prefix.
4. If categories are entirely absent, apply the same method to link-pattern buckets. If there is only one indistinguishable bucket, choose evenly spaced positions across canonical-key order and report that only deterministic coverage, not semantic representativeness, was achievable.
5. For a bucket of size N and quota K, choose `floor(i * (N - 1) / (K - 1))` for `i = 0..K-1`; for K=1 use the middle position. Quotas never exceed available candidates. If there are more categories than sample slots, choose evenly spaced sorted categories and report uncovered categories.
6. Reject a nonpositive count or fewer eligible records than requested; never pad with duplicates or silently return fewer. Input row order, repeated links, and timestamps must not affect membership.

Write `config/sample_20.json` only from a successfully captured full official manifest. Store schema/source, `selection_method: category-pattern-round-robin-v1`, requested count, stable record keys, titles, observed categories, document associations, and source URLs. Omit volatile generation timestamps so unchanged input observations reproduce the same bytes. Print category/pattern coverage and missing-metadata limitations.

Commit the chosen sample as the fixed input for later milestones. Discovery never regenerates it automatically. Repeating `source sample` against identical observations is a no-op; different content requires an explicit `--replace` or a different output path. Do not fabricate this file while source access is blocked.

### CLI contract

- `source discover --source pmegp [--output PATH] [--limit N | --sample PATH]`: explicitly live discovery; writes the manifest and prints totals/status. No default count ceiling.
- `source list [--source pmegp] [--manifest PATH] [--limit N]`: local inspection. With no manifest yet, report the supported source and "not discovered"; otherwise show recorded discovery time/scope/totals and project-to-document URLs. It performs no HTTP.
- `source sample --source pmegp --count 20 [--manifest PATH] [--output config/sample_20.json] [--replace]`: local selection and coverage summary; no HTTP.
- `source smoke --source pmegp`: explicitly marked LIVE; check robots and one listing response with the same client/parser. Report source URL, status, parsed entries/links/category availability, and whether further pages exist. A positive result means the inspected response matches assumptions, not a complete-corpus count. Write no manifest/sample and fetch no PDFs.

No separate live pytest module is needed: the smoke command is the deliberate manual network operation. Help, list, and sample must work without the government site or PostgreSQL.

## File changes

Create during implementation:

| Path | Purpose |
|---|---|
| `src/msmeintel/sources/__init__.py` | Package marker |
| `src/msmeintel/sources/base.py` | Required small adapter contract and generic candidate dataclasses |
| `src/msmeintel/sources/pmegp.py` | PMEGP URLs/selectors, pure parsing, constrained HTML fetching/robots handling, canonicalization |
| `src/msmeintel/discovery.py` | Generic identity/deduplication, manifest validation/read/write, selection and coverage |
| `tests/conftest.py` | Small autouse guard blocking real outbound socket/DNS calls in ordinary tests |
| `tests/test_discovery.py` | Parsing, canonicalization, transport, persistence, sampling, and CLI checks |
| `tests/fixtures/pmegp/listing.html` | Actual official listing capture retaining categories, row/link structures, and navigation; capture only once access allows it |
| `tests/fixtures/pmegp/edge_cases.html` | Clearly labeled synthetic malformed/duplicate/missing-link variants of the observed structure |
| `tests/fixtures/pmegp/README.md` | Capture URL/time, policy check, pruning/redaction notes, real versus synthetic provenance, traversal assumptions, and fixture license/reuse information |
| `config/sample_20.json` | Actual representative sample generated from complete official discovery; no placeholder |

If the accessible source actually requires a different continuation or detail response, add only its concrete fixture at `tests/fixtures/pmegp/continuation.html` or `tests/fixtures/pmegp/detail.html`, respectively. These conditional filenames are specified here; do not create empty examples or add corresponding runtime subsystems before the source demonstrates the need.

Change during implementation:

- `src/msmeintel/cli.py`: register and implement the four thin source commands; preserve health/root help behavior.
- `pyproject.toml`: add the three required runtime libraries, retaining existing build/dev settings.
- `uv.lock`: regenerate resolution without unrelated upgrades.
- `README.md`: document M01 commands, schema, sample policy, offline/live boundaries, errors, and single-writer limitation.
- `THIRD_PARTY_LICENSES.md`: record new direct and actually installed runtime transitive versions/licenses from authoritative metadata/license files. Unclear information is `REVIEW REQUIRED`; do not guess or add audit tooling.
- `.agent/plans/M01-pmegp-discovery.md`: implementation Progress/Outcome and source-verification evidence only, unless a genuine blocker changes scope/architecture/security/data integrity/licensing.

Generated local artifacts are `data/discovery/pmegp.json` and explicitly requested filtered snapshots. They are already ignored. No planned changes to M00 tests, configuration module, database module, migrations, .env example, .gitignore, or existing contracts.

## Database changes

None. No migrations, domain models, tables, indexes, seed data, or database access.

## Implementation steps

1. Resolve the documented source-access check without bypasses. Verify robots and current unrestricted listing behavior; capture actual HTML and provenance. Bind selectors, categories, identities, and continuation behavior only to that evidence. Ordinary selector/fixture details do not require another planning pass. Persistent denial/inaccessibility remains a reported source blocker.
2. Add and lock httpx/BeautifulSoup/lxml; verify licenses for the resolved packages and update the bounded inventory. Keep unrelated locked dependencies unchanged where compatible.
3. Add the small adapter contract and pure PMEGP parsing/canonicalization functions, with committed fixture checks first.
4. Add conservative HTML fetching with injected httpx transport and tested policy/timeouts/errors. Verify every requested URL is an allowed policy/listing/detail route and no document bytes are consumed.
5. Add generic identity, JSON serialization/validation, safe rerun replacement, explicit full/filtered scope, and deterministic sampler. Exercise these with a fixed clock and offline fixture data.
6. Wire the CLI, including local inspection and the separate smoke command. Run the complete offline gate, preserving M00 behavior.
7. With permitted source access, run the live smoke and full discovery; inspect associations, generate the actual 20-project sample and its coverage, and repeat discovery to verify stable identities/no duplicates. If the source is unavailable, report live acceptance blocked instead of claiming completion from synthetic data.
8. Record acceptance results, discovered count, source assumptions, sample coverage, file/dependency changes, and any real deviations in Outcome. Stop at M01.

## Tests

Use existing pytest and `httpx.MockTransport`; no new test framework or live HTTP in pytest.

- **Actual parsing:** representative rows from captured listing HTML produce correct source names/categories and all associated links. Preserve missing optional metadata. Do not assert a fixed live count.
- **Malformed/missing:** missing href/title/category, relative links, duplicate anchors/rows, unsafe schemes, no-document records, unexpected HTML/challenge pages, and malformed structure. Missing links are visible; structural drift fails explicitly.
- **URLs:** relative resolution, default ports, mixed-case host versus case-sensitive path, fragments, literal spaces/existing escapes, query preservation, and canonicalization idempotence. Preserve originals.
- **Identity:** repeated observations deduplicate; same name with distinct source identifiers/documents stays separate; a document shared by two projects stays associated with both; conflicting strong identities fail visibly.
- **Dynamic population:** mock responses with different row counts and added/removed entries change computed totals accordingly; no constant population count. Test any observed pagination/filter traversal, duplicate continuations, loops, and failed later pages.
- **Persistence:** two successful runs preserve first-seen timestamps, update last-seen times, and do not duplicate rows/links. Invalid old JSON, interrupted writes, parser failure, and HTTP failures preserve prior bytes. Full/limited/sample outputs cannot silently replace one another.
- **Sampling:** fixed fixture input yields exactly 20 unique eligible projects, reproducible bytes/membership after input reorder or timestamp changes, category/pattern quota coverage, singleton/exhausted buckets, missing categories, uniform-metadata fallback, too few candidates, and explicit changed-sample replacement. Use labeled synthetic expansions for algorithm edge cases, never as the real 20-project artifact.
- **Transport/security:** mock robots allowance/denial/404/failure, request pacing, timeout, 401/403/429/5xx, unexpected MIME, oversized HTML, blocked redirects/origins, and an offered PDF response whose body must remain unread. Recorded request URLs must contain no document request.
- **CLI/offline:** in-process runner covers discover -> manifest -> list -> sample and repeat-run idempotency with mocked responses. Assert real socket/DNS access is blocked by the autouse guard; list/sample/help issue zero HTTP requests. Run existing M00 checks unchanged under the same guard.
- **Live:** only `source smoke` and explicit discovery acceptance below. No auto-run live tests or skipped tests presented as a live pass.

## Acceptance commands

All commands run from the inner repository root containing `pyproject.toml`.

Install the locked environment, then run the mandatory offline gate (pytest itself uses no internet; an uncached initial dependency sync may):

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
```

Every command must exit 0; all M00 and M01 tests pass, Alembic stays empty, and help advertises the four source operations. Pytest exercises the complete mock discovery/persistence/sample flow under the network guard.

After source access and robots permission are confirmed, run the explicitly live acceptance and local inspection:

```powershell
uv run python -m msmeintel source smoke --source pmegp
uv run python -m msmeintel source discover --source pmegp
uv run python -m msmeintel source list --source pmegp --limit 20
uv run python -m msmeintel source sample --source pmegp --count 20 --output config/sample_20.json
uv run python -m msmeintel source discover --source pmegp
uv run python -m msmeintel source sample --source pmegp --count 20 --output data/discovery/sample_20-rerun.json
uv run python -m msmeintel source discover --source pmegp --limit 3 --output data/discovery/pmegp-limit-3.json
uv run python -m msmeintel source discover --source pmegp --sample config/sample_20.json --output data/discovery/pmegp-selected-20.json
uv run python -c "import json; from pathlib import Path; a=json.loads(Path('config/sample_20.json').read_text(encoding='utf-8')); b=json.loads(Path('data/discovery/sample_20-rerun.json').read_text(encoding='utf-8')); assert len(a['projects']) == 20; assert len({p['record_key'] for p in a['projects']}) == 20; assert a == b"
```

Only smoke/discover contact the site. Require a complete full manifest with an observed dynamic total, correct visible project/document associations, a 20-project checked-in sample with coverage reported, and no duplicates on rerun. The limit output contains three records; the selected output contains the twenty requested keys; both are labeled filtered. If source content genuinely changes between live runs, retain/report the difference and verify determinism using the same saved snapshot; do not label source drift an algorithm failure or erase it. Repeating `sample` on the same manifest must be byte-identical.

A failed/blocked live operation is not a pass. M01 is not done until permitted official-source discovery and the actual representative sample have been demonstrated. No application acceptance commands were run in this planning turn; only the read-only source-access checks documented above were attempted.

## Risks and open questions

These are the original planning risks. The old-target access blocker was resolved
by the user's corrected source; current dispositions and limitations are in Outcome.

- **Genuine source-access blocker:** current PMEGP HTML and robots could not be obtained. This prevents asserting current selectors, category coverage, pagination, identifiers, document route patterns, or source count. Successful permitted access, or an authentic HTML capture with URL/time for offline parser work, resolves different parts of this gap; a saved capture alone does not prove current live access.
- **No current metadata claim:** category stratification is the preferred algorithm only if explicitly present in actual HTML; the deterministic link-pattern/even-spread fallback is already specified. Sampling does not claim document-layout or OCR diversity before document processing exists.
- **Identity ceiling:** without stable source IDs/detail URLs, exact observed-record identity may change with links or distinguishing metadata. Preserve/report the difference, not speculative merging.
- **Access or licensing conflict:** an observed robots denial, authentication/CAPTCHA, a requirement for a proprietary/paid core dependency, or source terms prohibiting the intended fixture reuse would require reporting a real blocker. Do not bypass or silently assume a license. Keep captures limited to necessary public listing markup and record attribution/reuse evidence.
- No user architecture decision is outstanding: JSON persistence, the dependency stack, offline/live separation, and the sampling fallback follow the explicit task. Restoration of source access is evidence needed for implementation, not a request for a new design approval cycle.

## Progress

- [x] Required contracts and existing M00 implementation inspected.
- [x] Official listing address corroborated and bounded access checks attempted.
- [x] Single M01 ExecPlan written; no implementation performed.
- [x] Corrected official HTML/robots/script/API verified; authentic HTML/JSON fixtures captured.
- [x] 2026-10-08: retried official robots/listing access before implementation; no authentic repository capture found.
- [x] Source-independent M01 contract, URL handling, HTTP safety, manifests, deterministic sampling, CLI, tests, documentation, and bounded dependency inventory implemented.
- [x] PMEGP HTML-shell/API parsing and complete dynamic discovery implemented; real sample generated.
- [x] Offline acceptance gate passing: 116 tests, including all nine unchanged M00 tests.
- [x] Live acceptance and representative-20 coverage verified; all approved commands pass.

## Outcome

**M01 DONE — 2026-10-08, after the user corrected the primary source.**
Resumed the existing implementation; no new planning pass or architecture redesign.
All offline and live acceptance commands passed against the corrected source.
M00 regressions pass unchanged. M02 was not started.

### Verified source and request contract

- Primary listing: `GET https://pmegp.msme.gov.in/Home/ProjectDetailList`.
  The initial HTML contains `table#datatable-basic`, five headings (including
  hidden PSRID and Total Project Cost in rupees), and empty `tbody#ux_tablebody`.
- Its observed script, `/TFL_Scripts/Home/ProjectDetailList.cshtml.js`, calls
  **`GET https://pmegp.msme.gov.in/Home/GetAllProjectDocuments`**, with no query
  parameters or request body. The public endpoint works without authentication,
  cookies, or a browser runtime. Response: `application/json; charset=utf-8`,
  `{"success":true,"data":[project objects]}`.
- There are no server pagination parameters/page size or separate total field.
  The complete array is rendered by the script, then DataTables pages/searches/
  sorts it locally. The observed default display size is 10, with 10/25/50/100
  choices. Browser page 2 displays rows 11-20. Sr No is index + 1, not an API field
  or stable identity. No row serial is promoted to a project ID.
- The browser's rendered table, actual linked script, and direct API response
  were inspected. The browser-control API did not expose a raw network/HAR trace;
  method/parameters were established from that script and the successful direct
  request, not invented or claimed from an unavailable trace.
- `GET https://pmegp.msme.gov.in/robots.txt` returned 404 with no body.
  All live discovery checks policy before fetching the shell/API. Only those
  exact three metadata routes are permitted. No download URL is requested.
- Download buttons use `/Home/DownloadDocument?fileName=` plus JavaScript
  `encodeURIComponent(DocPath)`. The adapter reproduces this observed URL
  construction and retains the original DocPath, resolved URL, and canonical URL.
  There are no individual detail-page URLs in this feed.
- The old KVIC target is neither primary nor fallback; a regression test rejects it.

### Data, manifest, and representative 20

The successful full manifest at `data/discovery/pmegp.json` contains **1,024
distinct PSRIDs**, **1,024 project-document associations**, and **983 unique
canonical document URLs**, computed from the actual response. Shared documents
remain associated with separate projects; no count is hard-coded. It is a full,
complete snapshot with zero issues.

Captured API fields: PSRID, exact ProjectName, ProjectCost, DocPath, IsActive,
CreatedOn, and nullable ModifyOn. ProjectName is retained in raw_title and raw
metadata; cleaned title remains separate. ProjectCost retains exact decimal
text, e.g. `180500.0000`, with separate deterministic
`normalized_metadata.project_cost_inr = "180500"`. Conversion uses Decimal,
not binary floating-point arithmetic; unknown/null/unsafe-to-expand values are
not normalized. Two zero costs and one IsActive=false record were retained.
The source page renders the latter, so silently filtering it would lose data.
Source date strings remain verbatim. This is discovery metadata, not M5
financial normalization or validation.

There is no category column/filter/JSON field. The nine literal trailing
` ( group label )` annotations in the published names are preserved as
category_hint, without inferring a canonical business sector. The approved
category/pattern sampler is unchanged. Current links have one observable
pattern (single document from the listing); PDF contents/layouts are unknown.

| Published group label | Discovered projects | Selected |
|---|---:|---:|
| AGRO BASED FOOD PROCESSING INDUSTRY | 63 | 3 |
| COIR BOARD BASED INDUSTRY | 36 | 3 |
| FOREST BASED INDUSTRY | 21 | 2 |
| HAND MADE PAPER AND FIBRE INDUSTRY | 6 | 2 |
| MINERAL BASED INDUSTRY | 31 | 2 |
| POLYMER AND CHEMICAL BASED INDUSTRY | 74 | 2 |
| RURAL ENGG. AND BIO-TECH INDUSTRY | 81 | 2 |
| SERVICE AND TEXTILE INDUSTRY | 38 | 2 |
| Samadhan Projects | 674 | 2 |

Created the real `config/sample_20.json`: **20 distinct PSRIDs, 20 distinct
document URLs, 9/9 labels and 1/1 observed link patterns covered**. Stable
selected PSRIDs, in sample record-key order:
156, 3, 326, 103, 879, 706, 79, 716, 659, 700, 547, 709, 680, 439, 418, 178, 782,
320, 502, 59. The selection is category-balanced, not a population-proportional
estimate or a claim of OCR/layout diversity.

Rediscovery reported added=0, changed=0, no_longer_seen=0. All first_seen_at values
remained `2026-10-08T05:40:58.934578+00:00`; last_seen_at advanced to
`2026-10-08T05:42:09.914337+00:00`. The rerun sample was byte-identical.
Filtered artifacts contain exactly 3 and 20 projects respectively, retain the
dynamic full total, and are explicitly incomplete limit/sample snapshots.

### Files and implementation details

Created `tests/fixtures/pmegp/listing.html`,
`tests/fixtures/pmegp/project_documents.json`, and `config/sample_20.json`.
The HTML capture is a minimal authentic table/script-reference excerpt; the
JSON capture preserves 12 unmodified API row objects, original numeric tokens,
and JSON escapes. Capture time is `2026-10-08T05:32:17.594477+00:00`.
Pruning, source URLs, row selection, attribution, and reuse caveats are documented
in the fixture README. Malformed cases are clearly synthetic test mutations.

Modified:

- `src/msmeintel/sources/pmegp.py`: corrected source, observed shell/API parsing,
  direct GET feed, decimal-text handling, exact button URL construction,
  conservative policy checks, and JSON MIME validation.
- `src/msmeintel/sources/base.py` and `src/msmeintel/discovery.py`: generic raw
  JSON scalar metadata (including false/null) and separate normalized text
  metadata. No generic code depends on PMEGP field names.
- `src/msmeintel/cli.py`: accurate HTML/JSON smoke/help output and endpoint reporting.
- `tests/test_discovery.py`: authentic fixture parsing and mocked full CLI flow,
  varying response lengths, official-ID conflicts, zero/null/inactive cases,
  decimal precision, source drift, API denial/timeout/MIME failure, and old-source rejection.
- `README.md`, `tests/fixtures/pmegp/README.md`, `THIRD_PARTY_LICENSES.md`, and
  this plan's source correction/Progress/Outcome.

The previously implemented JSON storage and deterministic sampling were reused.
No new dependencies, lockfile changes, environment variables, database tables,
migrations, browser runtime, or future infrastructure were required. M00 source
contracts and tests remain unchanged apart from the already planned CLI extension.

### Acceptance results

| Exact offline command | Result |
|---|---|
| `uv sync --locked` | PASS; 31 locked packages checked |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS; 20 files formatted |
| `uv run pytest` | PASS; final run 116 passed in 5.15 seconds, including all nine M00 tests; zero live calls/skips |
| `uv run python -c "import msmeintel; print(msmeintel.__file__)"` | PASS; installed src package |
| `uv run python -m msmeintel --help` | PASS |
| `uv run python -m msmeintel health` | PASS; no database connection |
| `uv run alembic heads` | PASS; empty, no revisions |
| `uv run python -m msmeintel source --help` | PASS; four operations advertised |

Every command in the existing live/local Acceptance commands block also ran
unchanged and exited 0: smoke; full discovery; list --limit 20; creation of the
real 20 sample; repeated full discovery; rerun sample; --limit 3 output; selected
20 output; and the exact final count/unique-key/equality Python assertion.
Additional read-only checks verified sample byte equality, all PSRID/name
mappings, exact cost equivalence, and every constructed fileName-to-DocPath mapping.

One regression exposed that the prior robots precedence check depended on private
stdlib parser state. It was fixed conservatively using explicit directives/public
parser operations, without allowing ambiguous rules or changing the architecture.
An initial inspection snippet passed bytearray rather than bytes to BeautifulSoup;
that diagnostic-only error was corrected before capturing fixtures.

### Resolved blockers, limitations, and deviations

The prior checkpoint used the older KVIC URL and obtained no authentic source.
The user's corrected official target resolved that source-access blocker. Windows
curl still reported a certificate-revocation-check error, and the web reader
could not fetch the page, but the browser and approved httpx client succeeded
with their normal TLS verification. No certificate checks or access controls
were disabled, and no paid/proprietary component was introduced.

No implementation/runtime blocker remains. The source's terms assert rights and
do not grant an open-content license. Fixtures retain only minimal factual
metadata/schema; no site script, graphics, or PDF body is vendored. Public
redistribution/republication remains **REVIEW REQUIRED**; public access/robots 404
is not a license grant. Existing unused lxml resource notices remain recorded,
not silently assumed to have the core library license.

The source-specific adjustment is HTML-shell validation plus the observed public
JSON endpoint, as explicitly requested by the user. JSON fixtures replace the
previously conditional guessed-HTML edge fixtures; no guessed selector/endpoint
or fabricated authentic response was used. Generic metadata was minimally extended
for the requested raw/normalized cost distinction. These are evidence-driven
implementation details, not an architecture redesign or new planning pass.

M02 was not started. No PDF body/HEAD requests, SHA-256 file storage, parsing/OCR,
domain tables, AI, API/UI, Docker, queues, workers, or future-milestone code was added.

