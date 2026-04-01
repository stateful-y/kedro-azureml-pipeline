# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.1.0-alpha.1] - 2026-04-01

This **minor release** includes 22 commits.


### Features
- Update prepare-release workflow to use new actions versions  by @em-pe
- Update Kedro version and refactor dataset handling for AzureML compatibility by @em-pe
- Update Python version in Read the Docs configuration to 3.10 by @em-pe
- Upgrade Kedro to version 1.0.0 and update Python compatibility in poetry.lock by @em-pe
- Update numpy to version 1.26.4 and adjust Python markers in poetry.lock by @em-pe
- Disable python 3.12 unittests for now by @em-pe
- Update pydantic model methods to get rid of deprecation warnings by @em-pe
- Update Azure ML configuration and add E2E test reproduction script by @em-pe
- Replace azureml-fsspec with Azure ML v2 SDK for ARM64 compatibility  by @em-pe

### Bug Fixes
- Depandabot config by @Lasica
- Add github actions permissions by @em-pe

### Documentation
- Fix reference

### Miscellaneous Tasks
- Enabled dependabot prs & config by @Lasica
- Disabled code QL actions for dependabot by @Lasica
- Test exception for e2e tests with dependabot by @Lasica
- Disable forked_branch build for dependabot PR's by @em-pe
- Lock kedro version to 1.0.x by @em-pe

### Build
- Bump rojopolis/spellcheck-github-actions  by @dependabot[bot]
- Bump pytest-cov from 3.0.0 to 7.0.0  by @dependabot[bot]
- Bump pytest from 8.3.5 to 8.4.2  by @dependabot[bot]
- Bump actions/setup-python from 5 to 6  by @dependabot[bot]
- Bump actions/checkout from 4 to 5  by @dependabot[bot]

### Contributors

Thanks to all contributors for this release:
- @em-pe
- @Lasica
- @dependabot[bot]
# Changelog

## [Unreleased]

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
- Removed `init` arguments: `-a`/`--storage-account-name`, `-c`/`--storage-container`, `--use-pipeline-data-passing`, and positional `experiment_name`. by [@gtauzin](https://github.com/gtauzin)
- Removed deprecated `docker` config section; environment configuration now uses `execution.environment`. by [@gtauzin](https://github.com/gtauzin)
- Removed constants: `KEDRO_AZURE_BLOB_TEMP_DIR_NAME`, `KEDRO_AZURE_RUNNER_CONFIG`, `KEDRO_AZURE_RUNNER_DATASET_TIMEOUT`. by [@gtauzin](https://github.com/gtauzin)
- Removed dependencies: `adlfs` and `backoff`. by [@gtauzin](https://github.com/gtauzin)
- Removed deprecated SDK v1 dataset stubs (`AzureMLPandasDataset`, `AzureMLFileDataset`) and `v1_datasets` module. by [@gtauzin](https://github.com/gtauzin)
- Migrated project following the `stateful-y/python-package-copier` template. by [@gtauzin](https://github.com/gtauzin)
- `kedro azureml init` no longer accepts positional arguments or `--aml-env`. It generates `conf/base/azureml.yml` with placeholder values to be filled in manually. by [@gtauzin](https://github.com/gtauzin)

### Documentation

- Migrated documentation from Sphinx (RST) to MkDocs with Material theme. by [@gtauzin](https://github.com/gtauzin)
- Rewrote all documentation pages: getting started, user guide, API reference, and contributing guide. by [@gtauzin](https://github.com/gtauzin)
- Added NumPy-style docstrings to all public modules, classes, and functions (interrogate coverage at 100%). by [@gtauzin](https://github.com/gtauzin)
