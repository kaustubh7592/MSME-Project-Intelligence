# Architecture Decision Log

## DEC-001 - PostgreSQL as local structured source of truth
**Status:** accepted

The dominant questions are structured filters such as budget, manpower and machinery cost. PostgreSQL is used for reliable local SQL queries and future growth. A vector database is not required initially.

## DEC-002 - PMEGP only for initial source adapter
**Status:** accepted

Additional government repositories are deferred until the PMEGP pipeline works end-to-end.

## DEC-003 - Scale 20 -> 100 -> full dynamically discovered corpus
**Status:** accepted

The current project count must never be hard-coded. The 20-business corpus is the correctness stage, 100 is the variation/hardening stage, and the final stage processes everything currently discovered.

## DEC-004 - Raw artifacts are immutable
**Status:** accepted

Downloaded bytes are preserved by SHA-256. Reprocessing creates/replaces derived data but not raw source artifacts.

## DEC-005 - Evidence required for core facts
**Status:** accepted

Important financial and operational values must point back to page-level source evidence.

## DEC-006 - OCR is a fallback
**Status:** accepted

Use native PDF extraction first. OCR only pages that lack sufficient native text.

## DEC-007 - No vector search in the first usable build
**Status:** accepted

Structured SQL and full-text search cover the initial user questions. Semantic search can be added later.

## DEC-008 - Local LLM behind a provider interface
**Status:** accepted

Start with an Ollama provider but keep business logic independent of a specific model/runtime.

## DEC-009 - QueryIntent + deterministic parameterized SQL
**Status:** accepted

The LLM interprets the user question into a constrained schema. Application code builds the SQL. Arbitrary model-generated SQL is not executed.

## DEC-010 - Current trend analysis is Phase 2
**Status:** accepted

Historical government DPRs alone do not establish what is trending in 2026. Current-market claims require current dated evidence.
