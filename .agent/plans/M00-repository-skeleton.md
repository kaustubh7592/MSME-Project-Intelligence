# M00 - Repository contract and executable skeleton

## Goal

Turn the current documentation-only handoff into the smallest locally executable Python repository skeleton. From the repository root, a developer must be able to install the locked dependencies and the project package with `uv sync`, run the test suite, and display `python -m msmeintel --help` without `PYTHONPATH` changes or `sys.path` modification. The skeleton will establish configuration, logging, CLI, PostgreSQL/SQLAlchemy wiring, and Alembic migration plumbing without implementing any source discovery or document-processing behavior.

Milestone 0 must not require a running PostgreSQL server for its two roadmap acceptance commands. Database connections remain lazy; a later command or migration that actually uses the database may require the configured server.

## In scope

- A Python 3.12+ `src`-layout package named `msmeintel`, managed by `uv` and installed into the project environment through an explicit build backend.
- A Typer application that is executable through `python -m msmeintel`, exposes useful `--help`, and has one small `health` command that validates application configuration without contacting PostgreSQL.
- A standard-library environment configuration loader for the local data directory, log level, and SQLAlchemy PostgreSQL URL.
- Standard-library logging setup used by the CLI.
- SQLAlchemy declarative metadata and a lazy engine factory configured for PostgreSQL through `DATABASE_URL`.
- An initialized Alembic environment wired to the same metadata and URL, with no schema revision yet.
- A compact pytest suite covering the executable skeleton and configuration boundaries, with Ruff as the only additional development-quality tool.
- Minimal local setup/usage documentation and an initial inventory of resolved dependency licenses.
- Ignore rules for local environments, caches, secrets, build output, and future generated data.

## Out of scope

- Every Milestone 1 deliverable: `SourceAdapter`, PMEGP HTML selectors, crawling, URL canonicalization, project/document discovery, persistent manifests, sampling, and live-site fixtures.
- All downloading, retry logic, hashing, raw artifact storage, PDF parsing/classification, OCR, table extraction, normalization, evidence, validation, reports, local LLM integration, query intent, SQL query building, and user-answer generation.
- Domain tables, SQLAlchemy domain models, indexes, seed data, or an initial Alembic revision. Those must be introduced only by the milestone that owns their behavior.
- A YAML configuration layer, `.env` parser, Pydantic settings model, dependency-injection framework, service/repository abstractions, or placeholder packages for later pipeline stages.
- Docker/Compose, PostgreSQL installation automation, cloud services, CI, deployment files, monitoring, microservices, queues, vector databases, or a UI.
- Empty `config/`, `data/`, source-adapter, processing, AI, query, or report directories created only to resemble the eventual repository tree.
- Git repository initialization and changes to the supplied contract documents.

## Existing code/context inspected

- `AGENTS.md`
- `.agent/PLANS.md`
- `.agent/plans/M00-TEMPLATE.md`
- `README_FIRST.md`
- `CODEX_PROMPTS.md`
- `docs/TECHNICAL_SPEC.md`
- `docs/MSME_Project_Intelligence_Technical_Specification_v2.md` (present as a duplicate specification file)
- `docs/IMPLEMENTATION_ROADMAP.md`
- `docs/DECISIONS.md`
- `docs/DATA_DICTIONARY.md`
- The complete current repository tree, which contains documentation only and no project-local `.git`, Python package, `pyproject.toml`, tests, or migration files.

## Design

Use one Python package and no running application services. `src/msmeintel/__main__.py` delegates directly to a Typer app in `cli.py`. The CLI configures standard-library logging, while `config.py` reads only three environment-backed settings into a small immutable dataclass:

- `DATABASE_URL`, defaulting to a documented local `postgresql+psycopg://...` development URL;
- `MSMEINTEL_LOG_LEVEL`, defaulting to `INFO`;
- `MSMEINTEL_DATA_DIR`, defaulting to `./data`.

`pyproject.toml` must define a real package rather than a virtual dependency-only project. Use the `uv_build` backend and explicitly map the package to the `src` tree:

```toml
[project]
name = "msmeintel"
requires-python = ">=3.12"

[build-system]
requires = ["uv_build>=0.12,<0.13"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "msmeintel"
module-root = "src"
```

The full `[project]` table will also contain version, description, README, and dependencies. The build-system declaration makes `uv sync` install the project in editable form, so `uv run python -m msmeintel` and a plain `import msmeintel` resolve the installed package without path hacks.

`database.py` owns the SQLAlchemy `DeclarativeBase` and a function that creates an engine from the loaded URL. Engine construction must not open a connection, so imports, CLI help, and tests do not depend on PostgreSQL availability. Alembic imports the same metadata and obtains its URL from the same loader; there is no duplicate database setting in `alembic.ini`.

The `health` command checks that settings load, the log level is valid, the database URL uses the PostgreSQL dialect/psycopg driver, and the data path is representable. It reports configuration readiness only, never prints credentials, does not create directories, and does not claim the database is reachable.

Keep all M0 database code in `database.py`. A `db/` package, model modules, and repository layer are premature while there are no tables. Split the module only when a later milestone has real database behavior that makes the split useful.

Runtime dependencies are limited to Typer, SQLAlchemy, Alembic, and Psycopg 3. Pytest and Ruff are the only direct development dependencies; Ruff provides both lint and formatting checks. `uv_build` is the build-system dependency, not an application runtime dependency. Configuration and logging use the Python standard library; YAML, dotenv, Pydantic, and settings-framework dependencies are intentionally not added in M0.

Dependencies may be used when they are open-source/free for the intended local learning use. Core functionality must not require a proprietary paid runtime, subscription-only service, or commercial-license-only component. License data must come from verifiable package metadata or the dependency's authoritative source; never infer or guess it. Any unresolved or conflicting license must be recorded as `REVIEW REQUIRED` rather than filled with a plausible value.

## File changes

Create these files during implementation:

- `.gitignore` — ignore `.venv`, Python/test/tool caches, `.env`, build artifacts, and generated `data/` contents.
- `.env.example` — document the three supported environment variables with safe local example values.
- `pyproject.toml` — define Python 3.12+, project metadata, the explicit `uv_build`/`src/msmeintel` package mapping, minimal runtime dependencies, a development group containing only pytest and Ruff, plus minimal pytest and Ruff settings.
- `uv.lock` — commit the dependency resolution produced by `uv lock`/`uv sync`; do not hand-edit it.
- `README.md` — document prerequisites, `uv` setup, environment variables, CLI/test commands, PostgreSQL as an external local prerequisite, Alembic usage, and explicit M0 limitations.
- `THIRD_PARTY_LICENSES.md` — at minimum record name, locked version, verified license or `REVIEW REQUIRED`, source URL, and purpose for every direct dependency and every runtime transitive dependency actually installed. Include readily verifiable build/development transitive licenses, but do not add bespoke inventory tooling or broaden M0 merely to chase non-runtime metadata; never fabricate an unknown license. Keep model licenses absent because M0 installs no model.
- `src/msmeintel/__init__.py` — package marker and package version exposure only if supplied by package metadata without duplicated constants.
- `src/msmeintel/__main__.py` — minimal `python -m msmeintel` entry point.
- `src/msmeintel/cli.py` — Typer app, root help text, logging initialization, and configuration-only `health` command.
- `src/msmeintel/config.py` — immutable settings dataclass, environment loading, log-level validation, and database URL validation without reading a committed `.env` file.
- `src/msmeintel/logging_config.py` — small idempotent wrapper around Python `logging` configuration.
- `src/msmeintel/database.py` — SQLAlchemy declarative base and lazy PostgreSQL engine factory; no models or queries.
- `alembic.ini` — minimal Alembic command configuration with no authoritative embedded database credentials.
- `migrations/README` — short note that the directory contains migration scripts.
- `migrations/env.py` — connect Alembic to `msmeintel.database.Base.metadata` and the environment-loaded URL for offline/online migration modes.
- `migrations/script.py.mako` — standard minimal Alembic revision template.
- `migrations/versions/.gitkeep` — retain the empty revisions directory until a later milestone owns the first schema.
- `tests/test_skeleton.py` — all M0 tests in one small module; no fixtures hierarchy or live database dependency.

Update during implementation:

- `.agent/plans/M00-repository-skeleton.md` — check progress as work completes and record the actual outcome, commands, versions, and any approved deviations.

Do not modify the existing specification, roadmap, decision log, data dictionary, prompt playbook, or template plan in this milestone.

## Database changes

None. M0 configures the PostgreSQL driver, SQLAlchemy metadata, and Alembic environment but creates no tables, indexes, seed rows, database, role, or migration revision. There is therefore no schema compatibility impact or rollback operation.

## Implementation steps

1. Add `.gitignore`, `pyproject.toml`, and the `src/msmeintel` package metadata. Configure `uv_build` exactly as described above; add only the four runtime and two development dependencies identified above, then generate and commit `uv.lock`. Run `uv sync` and verify the installed package resolves from the environment rather than the working tree through a path override.
2. Implement `config.py` and `.env.example`: define the three settings, deterministic defaults, validation errors with actionable messages, and no automatic filesystem or network side effects.
3. Implement standard-library logging and the Typer entry points. Make root help work before settings are loaded; add the configuration-only `health` command and ensure rendered URLs never disclose passwords.
4. Add `database.py` with one declarative base and one lazy engine factory. Do not add sessions, repositories, domain models, or connectivity/retry behavior.
5. Initialize the minimal Alembic files. Import `Base` from `msmeintel.database`, assign `target_metadata = Base.metadata` in `migrations/env.py`, inject the loaded URL there, and leave `migrations/versions/` empty. Do not mock Alembic's runtime context in tests.
6. Add `tests/test_skeleton.py` for CLI help/health, environment overrides and invalid configuration, credential redaction on both success and error paths, logging setup, lazy PostgreSQL engine configuration, and the application's empty M0 metadata. Tests must not open a socket, require PostgreSQL, or construct Alembic-context mocks.
7. Write `README.md` with copyable setup and verification commands. Populate the minimum required entries in `THIRD_PARTY_LICENSES.md` from the final `uv.lock` and authoritative license sources; mark uncertainty `REVIEW REQUIRED` and stop rather than inventing data or expanding M0 into a license-research subsystem.
8. Run the exact commands below from the repository root, fix only M0 defects, then update this plan's Progress and Outcome sections. Stop without beginning M1.

## Tests

Add `tests/test_skeleton.py` with focused checks that:

- Typer's in-process runner returns exit code 0 for `--help` and exposes `health` without loading or connecting to the database.
- `health` succeeds with valid defaults/overrides, labels itself as a configuration check, and does not expose the database username/password in either standard output or standard error;
- a configuration-error health invocation returns a clear sanitized error and does not expose the database username/password in either standard output or standard error;
- the loader honors explicit environment overrides and rejects an invalid log level or non-PostgreSQL database URL without echoing credentials;
- logging applies the configured level without accumulating duplicate handlers across repeated setup calls;
- the engine factory produces a PostgreSQL/Psycopg SQLAlchemy engine lazily and can be disposed without a server;
- `Base.metadata.tables` is empty in M0. Do not import or emulate Alembic's execution context merely to test `migrations/env.py`; verify the file assigns `target_metadata = Base.metadata` during review, use `uv run alembic heads` as the M0 executable check, and leave full behavior to the first real migration.

No integration, golden-corpus, network, live PostgreSQL, source-site, or document fixtures belong in M0.

## Acceptance commands

Run from the repository root in this order:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -c "import msmeintel; print(msmeintel.__file__)"
uv run python -m msmeintel --help
uv run python -m msmeintel health
uv run alembic heads
```

Acceptance requires every command to exit 0. `uv run pytest` and `uv run python -m msmeintel --help` are the exact M0 gate from `docs/IMPLEMENTATION_ROADMAP.md`. The import command must print the installed `src/msmeintel/__init__.py` path without `PYTHONPATH` or `sys.path` manipulation. `health` must explicitly report configuration readiness rather than database reachability. `alembic heads` is expected to succeed with no listed revisions and without contacting PostgreSQL.

## Risks and open questions

- **Project license decision required:** the repository specifies a third-party license inventory but does not choose a license for this project's own source code. This plan does not invent one or add `LICENSE`. The owner should select one before external distribution; that choice does not block M0 execution.
- **PostgreSQL provisioning default:** the specification does not require Docker. This plan treats PostgreSQL installation/database creation as an external local prerequisite and adds no Compose file. Approval of this plan confirms that default; request a separate explicit scope change if container provisioning is wanted.
- The outer workspace is part of an unrelated parent Git worktree, while this repository directory has no local `.git`. Implementation must not stage, commit, or modify files outside this repository; repository initialization remains an owner action.
- Dependency versions and transitive packages will be determined by `uv.lock` at implementation time. Record the required inventory scope above using verified sources; label unclear licenses `REVIEW REQUIRED`. An unresolved license blocks adopting that dependency for required core functionality, but does not justify speculative tooling or a repository-wide license audit in M0.
- A default local database URL is developer convenience, not a secret. Real credentials stay in `DATABASE_URL`, `.env` remains ignored, and neither health output nor logs may expose the password.

## Progress

- [x] Plan drafted from the current repository and M0 contracts.
- [x] Owner approved the plan in principle and requested targeted revisions.
- [x] Requested plan revisions incorporated.
- [x] Revised plan reviewed and approved by the owner.
- [x] Repository skeleton implemented.
- [x] Tests passing.
- [x] Acceptance commands passing.

## Outcome

Completed on 2026-10-03.

- Added the installable `src/msmeintel` package, environment-backed configuration,
  credential-safe configuration health command, standard-library logging, lazy SQLAlchemy
  engine factory, shared empty declarative metadata, and Alembic environment with no
  revisions.
- Added the `uv_build` package configuration, `uv.lock`, pytest/Ruff configuration, nine
  focused tests, setup documentation, ignore rules, environment example, and verified
  third-party license inventory.
- `uv sync` installed the project with CPython 3.14.8, which satisfies the Python 3.12+
  contract. Locked direct versions are Alembic 1.20.0, Psycopg/Psycopg Binary 3.3.6,
  SQLAlchemy 2.1.3, Typer 0.27.2, pytest 9.1.1, Ruff 0.16.10, and uv_build 0.12.22.
- Acceptance results: `uv run ruff check .` passed; `uv run ruff format --check .` reported
  13 files formatted; `uv run pytest` reported 9 passed; the package import printed the
  installed `src/msmeintel/__init__.py`; CLI help and configuration health exited 0; and
  `uv run alembic heads` exited 0 with no revisions.
- Database changes: none. No database connection was attempted and no table, model, index,
  seed row, role, database, or migration revision was created.
- Deviations: none. Installing missing `uv` 0.12.22 and its managed compatible Python was an
  environment prerequisite, not a repository or scope change.
- Blockers: none. The project's own source license remains an owner decision before external
  distribution, and PostgreSQL provisioning remains an external prerequisite for later
  database-using milestones.
