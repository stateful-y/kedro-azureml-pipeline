# Frequently Asked Questions

This guide answers common questions and helps you diagnose and resolve issues when using Kedro AzureML Pipeline.

## Getting Started

### Do I need to modify my Kedro code?

**No!** Kedro AzureML Pipeline works with existing Kedro projects without code changes.

The only modifications needed are:

1. **Add Kedro AzureML Pipeline to dependencies**:

    ```bash
    pip install kedro-azureml-pipeline
    ```

2. **Initialize the plugin**:

    ```bash
    kedro azureml init
    ```

3. **Register the hooks** in `settings.py`:

    ```python
    from kedro_azureml_pipeline.hooks import azureml_local_run_hook

    HOOKS = (azureml_local_run_hook,)
    ```

Everything else (catalog, pipelines, parameters, hooks) works as-is.

---

### Can I use both Kedro and Azure ML CLI?

**Yes!** You can mix both:

```bash
# Kedro commands work normally
kedro run --env local
kedro run --pipeline=data_processing

# Azure ML commands via Kedro wrapper
kedro azureml run -j training
kedro azureml compile -j training

# Or use the Azure ML CLI directly
az ml job list --workspace-name <name> --resource-group <rg>
```

The Kedro AzureML Pipeline CLI wrapper (`kedro azureml <command>`) automatically handles configuration for you.

---

### Is Kedro AzureML Pipeline production-ready?

**Yes**, with caveats:

- **Production strengths**:

  - Actively maintained and used in real projects
  - Comprehensive test coverage
  - Supports stable Kedro versions (Kedro >= 0.19)

- **Production considerations**:

  - **Newer project**: Less mature than Kedro or Azure ML alone
  - **Experimental features**: Some features like distributed training support are evolving
  - **Pin versions**: Both Kedro and the Azure ML SDK release frequently

---

## Configuration

### How do I use environment-specific configurations?

Kedro AzureML Pipeline respects Kedro environments. Create different configurations per environment:

```text
conf/
  ├── base/
  │   ├── catalog.yml
  │   ├── azureml.yml    # Default settings
  │   └── parameters.yml
  ├── local/
  │   ├── catalog.yml
  │   └── parameters.yml
  └── prod/
      ├── catalog.yml
      ├── azureml.yml    # Production workspace, compute, schedule
      └── parameters.yml
```

Run with `kedro azureml run -j <job> --env <ENV>` to load that environment's config.

---

### How do I configure multiple jobs from one pipeline?

Use different pipeline filters in `azureml.yml`:

```yaml
jobs:
  preprocessing_only:
    pipeline:
      pipeline_name: data_processing
      to_nodes:
        - preprocess_companies_node
        - preprocess_shuttles_node

  full_data_processing:
    pipeline:
      pipeline_name: data_processing
```

Each job is a different slice of the same Kedro pipeline.

---

### How do I use different compute targets per job?

Define compute entries in `azureml.yml` and reference them in jobs:

```yaml
compute:
  __default__:
    cluster_name: "cpu-cluster"
  gpu:
    cluster_name: "gpu-cluster"

jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    compute: gpu

  preprocessing:
    pipeline:
      pipeline_name: data_processing
    # Uses __default__ compute
```

---

### How do I schedule jobs?

Define schedules in `azureml.yml` and assign them to jobs:

```yaml
jobs:
  nightly_etl:
    pipeline:
      pipeline_name: data_processing
    schedule:
      cron_expression: "0 0 * * *"
      timezone: "UTC"
```

See the [Scheduling section](user-guide.md#scheduling) of the user guide for details on recurrence schedules and reusable schedule definitions.

---

## Kedro Integration

### What happens to my Kedro hooks?

**All Kedro hooks are preserved and called at the appropriate times!**

Kedro AzureML Pipeline ensures hooks fire during Azure ML execution:

- **Context and catalog hooks** (`after_context_created`, `after_catalog_created`): Called before pipeline execution
- **Pipeline hooks** (`before_pipeline_run`, `after_pipeline_run`): Executed at the start and end of the pipeline job
- **Dataset hooks** (`before_dataset_loaded`, `after_dataset_loaded`, `before_dataset_saved`, `after_dataset_saved`): Called during data operations
- **Node hooks** (`before_node_run`, `after_node_run`, `on_node_error`): Wrapped in pipeline steps

This means integrations like `kedro-mlflow` work automatically without Azure ML-specific code.

---

### How does MLflow integration work?

If you have `kedro-mlflow` installed and configured:

1. **Kedro-MLflow hooks fire automatically** during Azure ML runs
2. **Azure ML's native MLflow tracking** records experiments, metrics, and artifacts
3. **No Azure ML-specific MLflow code needed**: it just works!
4. **Call MLflow functions in nodes as usual**

---

## Common Issues

### Why am I getting authentication errors?

Ensure your Azure credentials are configured. Run `az login` or set up a service principal. The plugin uses `DefaultAzureCredential` from the Azure Identity SDK.

**Solutions**:

- Run `az login` to refresh your credentials
- Verify your service principal has the correct role assignments
- Check that `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are set if using a service principal

---

### Why is my compute target not found?

Verify the cluster name in your `azureml.yml` matches an existing compute target in your Azure ML workspace:

```bash
az ml compute list --workspace-name <name> --resource-group <rg>
```

Common causes:

- Typo in `cluster_name`
- Compute target is in a different workspace
- Compute target was deleted or not yet provisioned

---

### Why is my environment not found?

Check that the environment name (including version tag like `@latest`) exists in your Azure ML workspace:

```bash
az ml environment list --workspace-name <name> --resource-group <rg>
```

---

### Why are files missing during remote execution?

Check your `.amlignore` file. It controls which files are excluded from the code snapshot upload.

**Solutions**:

- Ensure required files are not listed in `.amlignore`
- Set `code_directory: "."` in `azureml.yml` to upload the full project
- Set `code_directory: null` to disable code upload entirely (useful when using a pre-built environment)

---

### Why am I getting dataset version errors?

When using `AzureMLAssetDataset`, ensure the referenced Azure ML data asset exists and the version is accessible:

```bash
az ml data show --name <dataset_name> --workspace-name <name> --resource-group <rg>
```

Common causes:

- Data asset does not exist in the workspace
- Version specified does not exist
- Insufficient permissions to access the data asset

---

## Debugging Guide

When encountering an issue, follow this systematic approach:

### 1. Check Logs

- **Terminal output**: Look for error messages and stack traces where you ran `kedro azureml run`
- **Azure ML Studio logs**: Navigate to the failed job → Click the failed step → Check "Outputs + logs" tab

### 2. Verify Configuration

```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('conf/base/azureml.yml'))"

# Verify Kedro project loads
kedro run --dry-run

# Compile to YAML to inspect the generated pipeline
kedro azureml compile -j <job_name>
```

### 3. Test in Isolation

```bash
# Bypass Azure ML to isolate Kedro issues
kedro run

# Test single node
kedro run --node=<node_name>
```

### 4. Search GitHub Issues

Search [Kedro AzureML Pipeline Issues](https://github.com/stateful-y/kedro-azureml-pipeline/issues) for similar problems.

If not found, [open a new issue](https://github.com/stateful-y/kedro-azureml-pipeline/issues/new) with:

- Versions: `kedro --version`, `pip show kedro-azureml-pipeline`, `az --version`
- Minimal reproducible example
- Error message and stack trace
- Configuration files (sanitized)

---

## Still Need Help?

- **Documentation**: [Full Documentation](../index.md)
- **Community**: [Kedro Slack](https://slack.kedro.org/)
- **Bug Reports**: [GitHub Issues](https://github.com/stateful-y/kedro-azureml-pipeline/issues)

When asking for help, include:

- Kedro and Kedro AzureML Pipeline versions
- Minimal reproducible example
- Complete error messages
- What you've already tried
