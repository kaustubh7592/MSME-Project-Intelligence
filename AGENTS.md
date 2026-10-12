# Repository Instructions

## Mission
Build the local Government MSME Project Intelligence Platform described in `docs/TECHNICAL_SPEC.md`. The system builds an evidence-backed structured corpus from government project documents and answers questions from retrieved data.

## Architecture boundaries
- Keep Version 1 as one Python application plus PostgreSQL and a local model runtime.
- Do not introduce cloud services, paid APIs, microservices, message brokers, Kubernetes, or a separate vector database unless the user explicitly approves it.
- PMEGP is the only source adapter required until the roadmap reaches additional sources.

## Data truth rules
- Raw downloaded artifacts are immutable.
- Never invent a missing value.
- Never silently rewrite contradictory source values.
- Important financial/operational facts require page-level evidence.
- Keep source-reported facts separate from validation findings and derived values.
- Never hard-code the total project count; discovery determines it dynamically.

## AI rules
- The LLM is an interpretation layer, not the source of truth.
- Validate model output with Pydantic before persistence.
- The model must not write directly to the database.
- The query assistant must not execute arbitrary LLM-generated SQL.
- Use a validated QueryIntent and deterministic parameterized query builder.
- Do not claim that a business is currently trending from historical DPR data alone.

## Development process
- Implement only the requested milestone or task.
- For complex milestones, create/update an ExecPlan in `.agent/plans/` using `.agent/PLANS.md` before implementation.
- Do not begin the next milestone automatically.
- Keep changes small and reviewable.
- Add or update tests with each behaviour change.
- Run the milestone acceptance commands before declaring completion.
- If a requirement is ambiguous and the choice would materially change architecture, stop and ask instead of guessing.

## Relevant documents
- Use `docs/TECHNICAL_SPEC.md` for architecture and pipeline behaviour.
- Use `docs/IMPLEMENTATION_ROADMAP.md` for milestone scope and acceptance gates.
- Use `docs/DATA_DICTIONARY.md` when changing extracted fields or normalization.
- Use `docs/DECISIONS.md` before changing a recorded architecture decision.
- Use `.agent/PLANS.md` for significant multi-step implementation work.

## Completion report
At the end of an implementation task, report:
1. files changed;
2. behaviour implemented;
3. tests/commands run and results;
4. acceptance criteria satisfied;
5. known limitations or blockers;
6. whether any dependency/schema/configuration changed.
