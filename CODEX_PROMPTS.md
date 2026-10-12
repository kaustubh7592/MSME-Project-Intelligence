# Codex Prompt Playbook

Use a two-turn pattern: planning first, implementation second. Do not ask Codex to build the entire project in one turn.

## First prompt - plan Milestone 0 only

```text
We are starting the Government MSME Project Intelligence Platform learning project.

Read the repository root AGENTS.md. For this task, also read:
- docs/TECHNICAL_SPEC.md
- docs/IMPLEMENTATION_ROADMAP.md
- .agent/PLANS.md

Work only on Milestone 0: Repository contract and executable skeleton.

This turn is PLANNING ONLY. Do not implement code yet.

Inspect the current repository first. Then create
`.agent/plans/M00-repository-skeleton.md` as a self-contained ExecPlan following
`.agent/PLANS.md`.

The plan must:
- stay strictly within Milestone 0;
- use the simplest architecture in the technical specification;
- identify exact files to create/change;
- include tests and exact acceptance commands;
- list anything intentionally deferred to later milestones;
- call out any ambiguity that requires my decision.

Do not start Milestone 1 and do not add future infrastructure.
When finished, summarize the proposed plan and stop for review.
```

## Implement an approved milestone

```text
Read AGENTS.md and the approved ExecPlan:
`.agent/plans/M00-repository-skeleton.md`.

Implement ONLY that approved plan.

Rules:
- do not expand the scope;
- do not begin the next milestone;
- keep changes minimal and reviewable;
- add/update tests as described in the plan;
- update the plan progress/outcome sections while working;
- if a material architecture decision is missing, stop and ask instead of guessing;
- do not declare completion until all acceptance commands have been run.

At the end, provide:
1. changed files;
2. what was implemented;
3. commands/tests run and their results;
4. acceptance criteria status;
5. blockers/known limitations;
6. any dependency, migration or configuration changes.

Then stop.
```

## Verification pass

```text
Review the current implementation against:
- AGENTS.md
- the active milestone ExecPlan
- the milestone acceptance criteria in docs/IMPLEMENTATION_ROADMAP.md

Do not add new features.

Inspect the diff and run the required tests/acceptance commands. Look specifically for:
- scope creep;
- missing tests;
- silent exception handling;
- missing evidence/provenance;
- non-idempotent behaviour;
- hard-coded source counts;
- unsafe SQL construction;
- LLM output that is not schema-validated;
- source values being overwritten by derived/validated values.

Fix only defects that are clearly inside the current milestone. If a fix would require
an architecture change, report it instead of implementing it without approval.

Finish with a pass/fail checklist for every acceptance criterion.
```

## Plan any later milestone

```text
Read AGENTS.md, .agent/PLANS.md, docs/TECHNICAL_SPEC.md and the sections of
`docs/IMPLEMENTATION_ROADMAP.md` relevant to Milestone <N>.
Also inspect the code produced by completed milestones that this work depends on.

Create `.agent/plans/M<N>-<short-name>.md`.
Planning only; do not code.
Keep scope strictly inside Milestone <N> and stop after presenting the plan.
```

## Implement any later milestone

```text
Implement only the approved `.agent/plans/M<N>-<short-name>.md`.
Update tests and the plan progress/outcome.
Run all acceptance commands.
Do not begin Milestone <N+1>.
Stop after the completion report.
```

## Focused bug-fix prompt

```text
We have a defect in the current implemented milestone.

Defect:
<observed behaviour>

Expected behaviour:
<expected behaviour>

Reproduction:
<commands/input>

Read AGENTS.md and only the documentation relevant to this subsystem.
First reproduce the defect and identify the smallest root cause.
Do not refactor unrelated modules.
Add a regression test that fails before the fix and passes after it.
Implement the smallest correct fix, run the relevant test suite, and report the result.
If the root cause conflicts with an architecture decision, stop and explain the conflict.
```
