# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.1.0-alpha.4] - 2026-10-19

This **minor release** includes 25 commits.


### Features
- Replace the retry job setting with limits  ([#89](https://github.com/stateful-y/kedro-azureml-pipeline/pull/89)) by @gtauzin
- Name the signal when a step command dies of one  ([#105](https://github.com/stateful-y/kedro-azureml-pipeline/pull/105)) by @gtauzin
- Let compute entries select a Kubernetes instance type  ([#112](https://github.com/stateful-y/kedro-azureml-pipeline/pull/112)) by @gtauzin
- Stage the code snapshot once and submit concurrently  ([#133](https://github.com/stateful-y/kedro-azureml-pipeline/pull/133)) by @gtauzin
- Add per-job display name overrides to run  ([#135](https://github.com/stateful-y/kedro-azureml-pipeline/pull/135)) by @gtauzin
- Post run start, success, and failure once per job  ([#134](https://github.com/stateful-y/kedro-azureml-pipeline/pull/134)) by @gtauzin
- Post through the Slack API and thread a run's outcome under its start  ([#137](https://github.com/stateful-y/kedro-azureml-pipeline/pull/137)) by @gtauzin
- Expose mpi_rank() next to the master-node check  ([#138](https://github.com/stateful-y/kedro-azureml-pipeline/pull/138)) by @gtauzin
- Report degraded runs with warning and recovered events  ([#205](https://github.com/stateful-y/kedro-azureml-pipeline/pull/205)) by @gtauzin

### Bug Fixes
- Stop the execution path writing around the logging system  ([#88](https://github.com/stateful-y/kedro-azureml-pipeline/pull/88)) by @gtauzin
- Skip suffix-execution tests where there is no POSIX shell  ([#106](https://github.com/stateful-y/kedro-azureml-pipeline/pull/106)) by @gtauzin
- Resolve the public names lazily so leaf submodules stay framework-free  ([#139](https://github.com/stateful-y/kedro-azureml-pipeline/pull/139)) by @gtauzin
- Bump vulnerable transitive dependencies  ([#179](https://github.com/stateful-y/kedro-azureml-pipeline/pull/179)) by @gtauzin
- Pin the CI Python version and patch test_invoke_execute for kedro 1.7  ([#201](https://github.com/stateful-y/kedro-azureml-pipeline/pull/201)) by @gtauzin
- Link the issue chooser to private vulnerability reporting and readthedocs  ([#203](https://github.com/stateful-y/kedro-azureml-pipeline/pull/203)) by @gtauzin

### Documentation
- Link the security page from the section index  ([#86](https://github.com/stateful-y/kedro-azureml-pipeline/pull/86)) by @gtauzin
- Add a migration guide from kedro-azureml  ([#87](https://github.com/stateful-y/kedro-azureml-pipeline/pull/87)) by @gtauzin
- Tell users how to cite this project  ([#90](https://github.com/stateful-y/kedro-azureml-pipeline/pull/90)) by @gtauzin
- Put the description in the citation title  ([#98](https://github.com/stateful-y/kedro-azureml-pipeline/pull/98)) by @gtauzin

### Miscellaneous Tasks
- Verify tag signatures, allow publish retries, and automerge dep updates  ([#85](https://github.com/stateful-y/kedro-azureml-pipeline/pull/85)) by @gtauzin
- Drain the dependency queue one PR at a time  ([#99](https://github.com/stateful-y/kedro-azureml-pipeline/pull/99)) by @gtauzin

### Build
- Bump sqlparse from 0.5.5 to 0.6.0  ([#109](https://github.com/stateful-y/kedro-azureml-pipeline/pull/109)) by @dependabot[bot]
- Bump mkdocs-material from 9.7.6 to 9.7.7  ([#130](https://github.com/stateful-y/kedro-azureml-pipeline/pull/130)) by @dependabot[bot]
- Bump gitpython from 3.1.58 to 3.1.59  ([#143](https://github.com/stateful-y/kedro-azureml-pipeline/pull/143)) by @dependabot[bot]
- Bump anyio from 4.13.0 to 4.14.2  ([#158](https://github.com/stateful-y/kedro-azureml-pipeline/pull/158)) by @dependabot[bot]

### Contributors

Thanks to all contributors for this release:
- @gtauzin
- @dependabot[bot]

## [0.1.0-alpha.3] - 2026-08-12

This **minor release** includes 60 commits.


### Features
- Add retry configuration for pipeline steps  ([#15](https://github.com/stateful-y/kedro-azureml-pipeline/pull/15)) by @gtauzin
- Add `kedro azureml schedule --delete` CLI command  ([#16](https://github.com/stateful-y/kedro-azureml-pipeline/pull/16)) by @gtauzin
- Support Pydantic models in param resolution (Kedro 1.3 compat)  ([#20](https://github.com/stateful-y/kedro-azureml-pipeline/pull/20)) by @gtauzin
- Add job-level params field to JobConfig with CLI merge  ([#25](https://github.com/stateful-y/kedro-azureml-pipeline/pull/25)) by @gtauzin
- Resolve job factories from pipeline namespaces + multi-schedule jobs  ([#26](https://github.com/stateful-y/kedro-azureml-pipeline/pull/26)) by @gtauzin
- Make uv.lock the single source of truth for lint tooling  ([#33](https://github.com/stateful-y/kedro-azureml-pipeline/pull/33)) by @gtauzin

### Bug Fixes
- Relax kedro-mlflow pin to >=1.0.0 in mlflow extra  ([#17](https://github.com/stateful-y/kedro-azureml-pipeline/pull/17)) by @gtauzin
- Gracefully handle missing azureml workspace config and resolve dataset factories in data_path  ([#18](https://github.com/stateful-y/kedro-azureml-pipeline/pull/18)) by @gtauzin
- Wrap Docker image URIs in Environment object  ([#21](https://github.com/stateful-y/kedro-azureml-pipeline/pull/21)) by @gtauzin
- Don't call set_experiment before resuming AzureML run (avoids experiment ID mismatch) by @gtauzin
- Don't call set_experiment before resuming AzureML run (avoids experiment ID mismatch)  ([#22](https://github.com/stateful-y/kedro-azureml-pipeline/pull/22)) by @gtauzin
- Resolve experiment ID from run metadata before start_run  by @gtauzin
- Set experiment_name on scheduled pipeline jobs  ([#24](https://github.com/stateful-y/kedro-azureml-pipeline/pull/24)) by @gtauzin
- Pin exact uv version in setup-uv steps (template v0.29.6)  ([#46](https://github.com/stateful-y/kedro-azureml-pipeline/pull/46)) by @gtauzin
- Pin ossf/scorecard-action to the existing v2.4.4 tag by @gtauzin
- Grant tests-versions what it uses, not what it asked for  ([#63](https://github.com/stateful-y/kedro-azureml-pipeline/pull/63)) by @gtauzin
- Raise mlflow floor to >=3.13 to keep pyarrow cp314-capable  ([#68](https://github.com/stateful-y/kedro-azureml-pipeline/pull/68)) by @gtauzin
- Raise cryptography to 49.0.0  ([#78](https://github.com/stateful-y/kedro-azureml-pipeline/pull/78)) by @gtauzin
- Name the nightly coverage upload's file and discover every Codecov workflow  ([#80](https://github.com/stateful-y/kedro-azureml-pipeline/pull/80)) by @gtauzin
- Unblock PyPI publishing and split the nightly by interpreter  ([#83](https://github.com/stateful-y/kedro-azureml-pipeline/pull/83)) by @gtauzin

### Documentation
- Fix license link to point to repository LICENSE file  ([#14](https://github.com/stateful-y/kedro-azureml-pipeline/pull/14)) by @gtauzin
- Migrate documentation engine to Zensical (template v0.30.1)  ([#47](https://github.com/stateful-y/kedro-azureml-pipeline/pull/47)) by @gtauzin

### Refactoring
- Move throwaway build output under .artifacts/ and CODEOWNERS into .github/  ([#79](https://github.com/stateful-y/kedro-azureml-pipeline/pull/79)) by @gtauzin

### Miscellaneous Tasks
- Commit uv.lock + fix ty diagnostics at the source  ([#29](https://github.com/stateful-y/kedro-azureml-pipeline/pull/29)) by @gtauzin
- Fix See Also links and root export 404s in the API docs (template v0.26.1)  ([#35](https://github.com/stateful-y/kedro-azureml-pipeline/pull/35)) by @gtauzin
- Run pre-commit hooks with prek and filter changelog entries (template v0.27.0)  ([#36](https://github.com/stateful-y/kedro-azureml-pipeline/pull/36)) by @gtauzin
- Exempt the docs build scripts from ruff's lint rules (template v0.27.3)  ([#40](https://github.com/stateful-y/kedro-azureml-pipeline/pull/40)) by @gtauzin
- Render API page structure from mkdocstrings templates (template v0.28.1)  ([#41](https://github.com/stateful-y/kedro-azureml-pipeline/pull/41)) by @gtauzin
- Discover the API surface with Griffe (template v0.28.3)  ([#42](https://github.com/stateful-y/kedro-azureml-pipeline/pull/42)) by @gtauzin
- Replace stale git hooks by installing with prek install -f (template v0.28.4)  ([#43](https://github.com/stateful-y/kedro-azureml-pipeline/pull/43)) by @gtauzin
- Make the generated docs build engine-independent (template v0.29.3)  ([#44](https://github.com/stateful-y/kedro-azureml-pipeline/pull/44)) by @gtauzin
- Replace Dependabot with Renovate for dependency updates (template v0.31.1)  ([#48](https://github.com/stateful-y/kedro-azureml-pipeline/pull/48)) by @gtauzin
- Add pre-push gates and a single CI roll-up check (template v0.32.1)  ([#50](https://github.com/stateful-y/kedro-azureml-pipeline/pull/50)) by @gtauzin
- Add Versions passed roll-up to gate the version matrix  ([#51](https://github.com/stateful-y/kedro-azureml-pipeline/pull/51)) by @gtauzin
- Restrict workflow permissions and add secret scanning (template v0.35.0)  ([#52](https://github.com/stateful-y/kedro-azureml-pipeline/pull/52)) by @gtauzin
- Switch Codecov to OIDC and pin the Scorecard action (template v0.36.0)  ([#53](https://github.com/stateful-y/kedro-azureml-pipeline/pull/53)) by @gtauzin
- Document signing release tags with gitsign (template v0.37.0)  ([#54](https://github.com/stateful-y/kedro-azureml-pipeline/pull/54)) by @gtauzin
- Add a CLAUDE.md project-instructions file for AI assistants (template v0.38.0)  ([#55](https://github.com/stateful-y/kedro-azureml-pipeline/pull/55)) by @gtauzin
- Fix three release-pipeline defects (template v0.39.0)  ([#56](https://github.com/stateful-y/kedro-azureml-pipeline/pull/56)) by @gtauzin
- Let Renovate see the SBOM tool's version pin (template v0.39.1)  ([#57](https://github.com/stateful-y/kedro-azureml-pipeline/pull/57)) by @gtauzin
- Add a nightly job that exercises the release path (template v0.40.0)  ([#58](https://github.com/stateful-y/kedro-azureml-pipeline/pull/58)) by @gtauzin
- Fix a shell injection in the release publish job (template v0.40.1)  ([#64](https://github.com/stateful-y/kedro-azureml-pipeline/pull/64)) by @gtauzin

### Build
- Bump dawidd6/action-download-artifact from 19 to 20  ([#11](https://github.com/stateful-y/kedro-azureml-pipeline/pull/11)) by @dependabot[bot]
- Bump actions/github-script from 8 to 9  ([#10](https://github.com/stateful-y/kedro-azureml-pipeline/pull/10)) by @dependabot[bot]
- Bump dawidd6/action-download-artifact from 20 to 21  ([#19](https://github.com/stateful-y/kedro-azureml-pipeline/pull/19)) by @dependabot[bot]
- Bump codecov/codecov-action from 6 to 7  ([#27](https://github.com/stateful-y/kedro-azureml-pipeline/pull/27)) by @dependabot[bot]
- Bump actions/checkout from 6 to 7  ([#28](https://github.com/stateful-y/kedro-azureml-pipeline/pull/28)) by @dependabot[bot]
- Bump the lint-tools group across 1 directory with 3 updates  ([#39](https://github.com/stateful-y/kedro-azureml-pipeline/pull/39)) by @dependabot[bot]
- Bump gitpython from 3.1.46 to 3.1.58  ([#61](https://github.com/stateful-y/kedro-azureml-pipeline/pull/61)) by @dependabot[bot]
- Bump pyasn1 from 0.6.3 to 0.6.4  ([#67](https://github.com/stateful-y/kedro-azureml-pipeline/pull/67)) by @dependabot[bot]
- Bump pyjwt from 2.12.1 to 2.13.0  ([#66](https://github.com/stateful-y/kedro-azureml-pipeline/pull/66)) by @dependabot[bot]
- Bump pillow from 12.1.1 to 12.3.0  ([#65](https://github.com/stateful-y/kedro-azureml-pipeline/pull/65)) by @dependabot[bot]
- Bump starlette from 1.0.0 to 1.3.1  ([#69](https://github.com/stateful-y/kedro-azureml-pipeline/pull/69)) by @dependabot[bot]
- Bump idna from 3.11 to 3.15  ([#71](https://github.com/stateful-y/kedro-azureml-pipeline/pull/71)) by @dependabot[bot]
- Bump pytest from 9.0.2 to 9.0.3  ([#72](https://github.com/stateful-y/kedro-azureml-pipeline/pull/72)) by @dependabot[bot]
- Bump mako from 1.3.10 to 1.3.12  ([#73](https://github.com/stateful-y/kedro-azureml-pipeline/pull/73)) by @dependabot[bot]
- Bump urllib3 from 2.6.3 to 2.7.0  ([#74](https://github.com/stateful-y/kedro-azureml-pipeline/pull/74)) by @dependabot[bot]
- Bump kedro-datasets from 9.2.0 to 9.3.0  ([#75](https://github.com/stateful-y/kedro-azureml-pipeline/pull/75)) by @dependabot[bot]
- Bump requests from 2.32.5 to 2.33.0  ([#77](https://github.com/stateful-y/kedro-azureml-pipeline/pull/77)) by @dependabot[bot]
- Bump kedro from 1.2.0 to 1.3.0  ([#76](https://github.com/stateful-y/kedro-azureml-pipeline/pull/76)) by @dependabot[bot]

### Contributors

Thanks to all contributors for this release:
- @dependabot[bot]
- @gtauzin

## [0.1.0-alpha.2] - 2026-04-15

This **minor release** includes 1 commit.


### Bug Fixes
- Patch azureml artifact builder for MLflow 3.10+ compatibility  ([#12](https://github.com/stateful-y/kedro-azureml-pipeline/pull/12)) by @gtauzin

### Contributors

Thanks to all contributors for this release:
- @gtauzin

## [0.1.0-alpha.1] - 2026-04-01

This **minor release** includes 1 commit.


### Features

- `kedro azureml run -j <job>` command for running named jobs immediately on Azure ML. Supports `--dry-run` (preview), `--wait-for-completion` (CI blocking), and `--on-job-scheduled` (callback). by [@gtauzin](https://github.com/gtauzin)
- `kedro azureml schedule -j <job>` command for creating or updating persistent Azure ML schedules. Requires each job to have a schedule configured. Supports `--dry-run` (preview). by [@gtauzin](https://github.com/gtauzin)
- `kedro azureml compile -j <job>` for compiling named job pipelines to YAML. by [@gtauzin](https://github.com/gtauzin)
- `schedules` and `jobs` config sections with cron and recurrence triggers, pipeline filtering (`from_nodes`, `to_nodes`, `tags`, etc.), per-job display name, compute, and experiment name. by [@gtauzin](https://github.com/gtauzin)
- Named workspaces: `workspace` is now a dict of named workspace configs (with mandatory `__default__`). Jobs can reference a specific workspace via `workspace:` key. CLI `--workspace`/`-w` selects a workspace at run/schedule time. by [@gtauzin](https://github.com/gtauzin)
- Full kedro-mlflow compatibility: unified experiment naming via mlflow.yml, MLflow run tagging hook, and env var injection into Azure ML component jobs. by [@gtauzin](https://github.com/gtauzin)
- Support for Python 3.13. by [@gtauzin](https://github.com/gtauzin)
- Support factory-resolved datasets in the runner. by [@gtauzin](https://github.com/gtauzin)

### Refactoring

- Config restructure: the `azure:` top-level key is replaced by three flat sections -- `workspace`, `compute`, `execution`. `compute` and `workspace` are flat dicts keyed by name (with mandatory `__default__`). `experiment_name` moves into per-job config. The `temporary_storage` and `pipeline_data_passing` config sections are removed. by [@gtauzin](https://github.com/gtauzin)
- `kedro azureml run` is replaced by `kedro azureml run -j <job>` (immediate execution) and `kedro azureml schedule -j <job>` (persistent schedules). `kedro azureml compile` now requires `-j <job>`. `--subscription-id` replaced by `--workspace`. by [@gtauzin](https://github.com/gtauzin)
- Blob storage removal: `KedroAzureRunnerDataset`, `KedroAzureRunnerDistributedDataset`, `BlobStorageDataPassing`, `KedroAzureRunnerConfig`, and `runner_dataset.py` module deleted. Pipeline data passing via `AzureMLPipelineDataset` is now the only mode. by [@gtauzin](https://github.com/gtauzin)
- Removed `kedro azureml run` command and all its options (`--display-name`, `--compute-name`, `--experiment-name`, `-p`/`--pipeline`, `--wait-for-completion`, `--on-job-scheduled`). by [@gtauzin](https://github.com/gtauzin)
- Removed deprecated `docker` config section; environment configuration now uses `execution.environment`. by [@gtauzin](https://github.com/gtauzin)
- Removed deprecated SDK v1 dataset stubs (`AzureMLPandasDataset`, `AzureMLFileDataset`) and `v1_datasets` module. by [@gtauzin](https://github.com/gtauzin)
- Migrated project following the `stateful-y/python-package-copier` template. by [@gtauzin](https://github.com/gtauzin)
- `kedro azureml init` no longer accepts positional arguments or `--aml-env`. It generates `conf/base/azureml.yml` with placeholder values to be filled in manually. by [@gtauzin](https://github.com/gtauzin)

### Documentation

- Migrated documentation from Sphinx (RST) to MkDocs with Material theme. by [@gtauzin](https://github.com/gtauzin)
- Rewrote all documentation pages based on diataxis approach: getting started, user guide, API reference, and contributing guide. by [@gtauzin](https://github.com/gtauzin)
- Added NumPy-style docstrings to all public modules, classes, and functions (interrogate coverage at 100%). by [@gtauzin](https://github.com/gtauzin)

### Contributors

Thanks to all contributors for this release:
- @gtauzin

---

## [`kedro-azureml` v1.0.0]

This project is a fork of [`kedro-azureml`](https://github.com/getindata/kedro-azureml) originally created by [GetInData | Part of Xebia](https://github.com/getindata).
