# Execution Plans

Use an ExecPlan for each milestone or any change that spans multiple modules, requires a database migration, or changes the ingestion/query architecture.

Each ExecPlan must be self-contained and stored in `.agent/plans/`.

## Required sections

### Goal
State the user-visible or pipeline behaviour to deliver.

### In scope
List exactly what this plan will implement.

### Out of scope
List adjacent work that must not be started.

### Existing code/context inspected
List the repository files actually inspected before planning.

### Design
Describe the minimal design and data flow. Reuse existing abstractions where possible.

### File changes
List files to create/change and the purpose of each.

### Database changes
Describe migrations, indexes and compatibility impact, or state `none`.

### Implementation steps
Write ordered, independently checkable steps.

### Tests
List unit/integration/golden tests to add or update.

### Acceptance commands
List exact commands that must pass.

### Risks and open questions
Record uncertainty. Do not hide it.

### Progress
Update checkboxes as implementation proceeds.

### Outcome
After implementation, record what was completed, deviations from plan, test results and unresolved follow-up work.
