# Implementation Roadmap

Implement exactly one milestone at a time. Do not start a later milestone until the current acceptance gate passes.

| Milestone | Scope | Status |
|---|---|---|
| M0 | Repository contract and executable skeleton | Not started |
| M1 | PMEGP discovery and deterministic 20-business sample | Not started |
| M2 | Downloader and immutable raw store | Not started |
| M3 | PDF classification and native text extraction | Not started |
| M4 | OCR fallback and basic table extraction | Not started |
| M5 | Canonical facts, evidence and deterministic validation | Not started |
| M6 | Local LLM structured extraction | Not started |
| M7 | Query assistant using QueryIntent + deterministic SQL | Not started |
| M8 | Scale and harden on 100 projects | Not started |
| M9 | Process the full dynamically discovered PMEGP corpus | Not started |

## M0 - Repository contract and executable skeleton
Deliver: repo structure, pyproject, configuration, logging, Typer CLI, PostgreSQL configuration, SQLAlchemy/Alembic skeleton, pytest, README, license inventory.

Acceptance commands:
```bash
uv run pytest
uv run python -m msmeintel --help
```

Out of scope: source crawling, downloading, PDF parsing, AI.

## M1 - PMEGP discovery and sample manifest
Deliver: `SourceAdapter`, `PMEGPAdapter`, project/document-link discovery, URL canonicalization, persistence, `--limit`, stable `sample_20.json`, fixtures/tests.

Acceptance: deterministic 20-project sample; project/document associations visible; rerun does not duplicate source records.

## M2 - Downloader and immutable raw store
Deliver: retries/backoff, MIME/signature validation, SHA-256, content-addressed paths, persisted status/errors, retry-failed.

Acceptance: reachable sample documents stored; duplicate bytes stored once; rerun is idempotent.

## M3 - PDF classification and native text extraction
Deliver: page enumeration, native text, page metadata, text/scanned/mixed classification, persistence.

Acceptance: every sample page has an extraction status; normal text PDFs yield usable text.

## M4 - OCR fallback and basic tables
Deliver: OCR decision rule, rendering, Tesseract, pdfplumber tables, quality score; Camelot only if sample evidence requires it.

Acceptance: scanned sample pages produce text; selected financial tables recover expected golden values.

## M5 - Canonical facts, evidence and validation
Deliver: currency/unit normalization, facts/evidence persistence, validation rules, Markdown project report.

Acceptance: golden core fields are correct; core facts have page evidence; warnings are non-destructive.

## M6 - Local LLM structured extraction
Deliver: provider interface, Ollama adapter, Pydantic output schema, versioned prompt, retry/failure handling, audit metadata, mocked tests plus selected real-model evaluation.

Acceptance: invalid JSON rejected; missing values remain null; evidence required for core numerics; model never writes directly to DB.

## M7 - Query assistant
Deliver: QueryIntent schema, intent parsing, deterministic safe query builder, read-only SQL, result formatter, grounded answer prompt, query CLI.

Acceptance: fixed evaluation questions pass; no arbitrary LLM SQL; current-trend query states the Version 1 limitation.

## M8 - Scale to 100
Deliver: 100-project run, failure report, schema/normalization changes only when supported by observed data, performance metrics.

Acceptance: no regression on the golden 20; failures categorized; pipeline resumable.

## M9 - Full dynamic corpus
Deliver: process all currently discovered PMEGP projects (not a hard-coded 1,024), full run report, searchable corpus, unresolved-exception list.

Acceptance: per-document failures do not abort the run; query assistant works across full corpus; evidence remains traceable.
