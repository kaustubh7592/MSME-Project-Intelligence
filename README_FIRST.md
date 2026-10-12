# Read This First - How to Hand the Project to Codex

## 1. Put this handoff pack at the root of the new code repository
You should end up with at least:

```text
AGENTS.md
.agent/PLANS.md
CODEX_PROMPTS.md
docs/TECHNICAL_SPEC.md
docs/IMPLEMENTATION_ROADMAP.md
docs/DATA_DICTIONARY.md
docs/DECISIONS.md
```

## 2. Do not paste the entire technical specification into every Codex message
The repository files are durable context. `AGENTS.md` contains the short always-applicable rules; the technical specification is consulted when architecture/pipeline details are needed.

## 3. Initialize Codex repository instructions if needed
If you are using Codex in the ChatGPT desktop app, `/init` can generate an `AGENTS.md` scaffold. For this project, replace/merge that scaffold with the supplied `AGENTS.md` rather than creating conflicting instruction files.

## 4. Start with planning only
Open `CODEX_PROMPTS.md` and use the first Milestone 0 planning prompt. Review the plan before asking Codex to write code.

## 5. Implement one milestone only
After approving the plan, use the implementation prompt. Do not tell Codex to continue automatically to the next milestone.

## 6. Run a verification pass
After implementation, use the verification prompt. Require test/acceptance results before marking the milestone complete.

## 7. Create a Git checkpoint
Commit after every accepted milestone. This makes rollback easy if a later Codex change damages working behaviour.

## 8. Move to the next milestone in a fresh focused task
Create a new ExecPlan for the next milestone. The repo files preserve architecture context, so the conversation does not need to carry the entire project history.

## Golden rule
The long technical document is the contract. The milestone ExecPlan is the unit of implementation.
