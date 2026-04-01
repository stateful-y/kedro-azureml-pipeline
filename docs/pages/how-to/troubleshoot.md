# How to Troubleshoot

This guide covers common errors and systematic debugging steps for Kedro AzureML Pipeline.

## Authentication errors

**Symptom**: Errors mentioning `AuthenticationError`, `CredentialUnavailableError`, or `DefaultAzureCredential`.

**Cause**: Azure credentials are missing or expired.

**Fix**: Run `az login` for local development, or set service principal environment variables for CI/CD. See [How to authenticate](authenticate.md) for the full credential setup guide.

---

## Compute target not found

**Symptom**: Error mentioning the cluster name cannot be found.

**Cause**: The `cluster_name` in `azureml.yml` does not match an existing compute target.

**Fix**: List available compute targets:

```bash
az ml compute list --workspace-name <name> --resource-group <rg>
```

Correct the `cluster_name` in the relevant `compute` entry in `azureml.yml`.

---

## Environment not found

**Symptom**: Error mentioning the environment name cannot be resolved.

**Cause**: The `environment` value in `azureml.yml` does not match any environment in the workspace.

**Fix**: List available environments:

```bash
az ml environment list --workspace-name <name> --resource-group <rg>
```

Ensure the name includes a valid version tag, e.g. `my-env@latest` or `my-env:3`. See [Build a custom environment](build-custom-environment.md) for creating and registering environments.

---

## Files missing during remote execution

**Symptom**: `FileNotFoundError` for project files or data during an Azure ML run.

**Cause**: The file is excluded from the code upload, or `code_directory` is set to `null`.

**Fix**: Check `.amlignore` because any file listed there is excluded from upload. Remove it if the file is needed. Ensure `code_directory: "."` is set in `azureml.yml` to upload the full project.

---

## Dataset version errors

**Symptom**: Errors about a data asset version not existing or not being accessible.

**Cause**: The `azureml_version` on an [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] entry does not exist, or the asset itself does not exist in the workspace.

**Fix**: Verify the asset exists:

```bash
az ml data show --name <dataset_name> --workspace-name <name> --resource-group <rg>
```

Remove the `azureml_version` field to use the latest version, or correct the version number. See the [Datasets reference](../reference/datasets.md) for the full parameter tables.

---

## Schedule not triggering

**Symptom**: You created a schedule with `kedro azureml schedule`, but no runs appear in Azure ML Studio.

**Cause**: The schedule definition, compute target, or environment may be invalid, causing Azure ML to skip the trigger silently.

**Fix**:

1. Verify the schedule exists in Azure ML Studio under **Assets > Schedules** (or **Manage > Schedules** depending on Studio version).
2. Check that the compute cluster referenced by the job is running and has available nodes.
3. Confirm the Azure ML environment still exists and has not been deleted or renamed.
4. Use `kedro azureml schedule -j <job> --dry-run` to inspect the schedule definition locally.
5. If using cron expressions, verify the expression and time zone are correct. A cron trigger in the past with no future occurrence will never fire.

---

## MLflow logging not appearing

**Symptom**: Node functions call `mlflow.log_metric()` or `mlflow.log_param()`, but no metrics or parameters appear in Azure ML Studio after the run completes.

**Cause**: The `kedro-mlflow` package or its hook may not be active during remote execution.

**Fix**:

1. Verify that `kedro-mlflow` is installed in your Azure ML environment (the Docker image or conda spec used by the compute).
2. Check step logs in Azure ML Studio for import errors related to `mlflow` or `kedro_mlflow`.
3. Compile the job with `kedro azureml compile -j <job>` and confirm that `KEDRO_AZUREML_MLFLOW_ENABLED: "1"` appears in the generated YAML environment variables.
4. If you set `mlflow_tracking_uri` manually in `mlflow.yml`, remove it or set it to `null` so Azure ML's injected URI takes precedence.

See also the [Use MLflow](use-mlflow.md) how-to guide.

---

## Azure SDK warnings

**Symptom**: Import warnings from `azure.ai.ml` appear in your terminal output.

**Note**: The plugin suppresses these warnings by default on import. If you see them, it usually means code is importing `azure.ai.ml` before `kedro_azureml_pipeline`. This is harmless but noisy. To suppress manually:

```python
import warnings
warnings.filterwarnings("ignore", module="azure.ai.ml")
```

---

## Systematic debugging steps

When encountering an unfamiliar issue, follow this approach:

### 1. Check the terminal output

Look for error messages and stack traces in the terminal where you ran `kedro azureml run`. These often pinpoint the exact failure.

### 2. Check Azure ML Studio logs

Open Azure ML Studio, navigate to **Jobs**, find the failed run, click the failed step, and open the **Outputs + logs** tab. The step logs contain the full stdout and stderr from the Kedro execution on Azure ML compute.

### 3. Verify configuration

```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('conf/base/azureml.yml'))"

# Verify the Kedro project loads cleanly
kedro run --dry-run

# Compile to YAML to inspect the generated Azure ML pipeline definition
kedro azureml compile -j <job_name>
```

### 4. Isolate the Kedro layer

Run the pipeline locally to confirm it works without Azure ML:

```bash
kedro run
```

If local execution fails, the issue is in your Kedro code or catalog, not in the plugin or Azure ML.

### 5. Search and report

Search [GitHub Issues](https://github.com/stateful-y/kedro-azureml-pipeline/issues) for similar problems. If not found, [open a new issue](https://github.com/stateful-y/kedro-azureml-pipeline/issues/new) with:

- Versions: output of `kedro --version`, `pip show kedro-azureml-pipeline`, `az --version`
- A minimal reproducible example
- The full error message and stack trace
- Sanitized configuration files

## See also

- [Configuration reference](../reference/configuration.md) for all `azureml.yml` fields
- [CLI reference](../reference/cli.md) for all available commands
- [Compile and inspect](compile-and-inspect.md) for verifying pipeline YAML before submitting
- [Architecture overview](../explanation/architecture.md) for how the plugin works internally
