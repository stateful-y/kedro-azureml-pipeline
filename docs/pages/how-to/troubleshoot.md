# How to Troubleshoot

This guide covers common errors and systematic debugging steps for Kedro AzureML Pipeline.

## Authentication errors

**Symptom**: Errors mentioning `AuthenticationError`, `CredentialUnavailableError`, or `DefaultAzureCredential`.

**Cause**: Azure credentials are missing or expired.

**Fix**:

```bash
az login
```

For CI/CD or automated environments, configure a service principal and set:

```bash
export AZURE_TENANT_ID="..."
export AZURE_CLIENT_ID="..."
export AZURE_CLIENT_SECRET="..."
```

Verify the service principal has the `Contributor` or `AzureML Data Scientist` role on the workspace.

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

Ensure the name includes a valid version tag, e.g. `my-env@latest` or `my-env:3`.

---

## Files missing during remote execution

**Symptom**: `FileNotFoundError` for project files or data during an Azure ML run.

**Cause**: The file is excluded from the code upload, or `code_directory` is set to `null`.

**Fix**: Check `.amlignore` - any file listed there is excluded from upload. Remove it if the file is needed. Ensure `code_directory: "."` is set in `azureml.yml` to upload the full project.

---

## Dataset version errors

**Symptom**: Errors about a data asset version not existing or not being accessible.

**Cause**: The `azureml_version` on an `AzureMLAssetDataset` entry does not exist, or the asset itself does not exist in the workspace.

**Fix**: Verify the asset exists:

```bash
az ml data show --name <dataset_name> --workspace-name <name> --resource-group <rg>
```

Remove the `azureml_version` field to use the latest version, or correct the version number.

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

- [Configuration reference](../reference/configuration.md) - all `azureml.yml` fields
- [Architecture overview](../explanation/architecture.md) - how the plugin works internally
