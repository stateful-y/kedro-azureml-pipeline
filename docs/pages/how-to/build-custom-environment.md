# How to Build a Custom Azure ML Environment

This guide shows how to create and register an Azure ML environment that contains your project's dependencies, so that remote pipeline steps have everything they need.

## Prerequisites

- The Kedro AzureML Pipeline plugin installed and configured (see [Getting Started](../tutorials/getting-started.md))
- The [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) with the `ml` extension (`az extension add -n ml`)

## Create a Dockerfile

Create a `Dockerfile` in your project root (or a `docker/` subdirectory):

```dockerfile
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

If you use `uv`, export your requirements first:

```bash
uv export --no-dev --no-hashes > requirements.txt
```

## Use a conda specification instead

If you prefer conda over pip, create an `environment.yml`:

```yaml
name: my-kedro-env
channels:
  - defaults
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
    - kedro>=1.0.0
    - kedro-azureml-pipeline
    - pandas
    # ... your other dependencies
```

## Register the environment in Azure ML

=== "With a Dockerfile"
    ```bash
    az ml environment create \
      --name my-kedro-env \
      --build-context-path . \
      --dockerfile-path Dockerfile \
      --workspace-name <workspace> \
      --resource-group <rg>
    ```

=== "With a conda spec"
    ```bash
    az ml environment create \
      --name my-kedro-env \
      --conda-file environment.yml \
      --image mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest \
      --workspace-name <workspace> \
      --resource-group <rg>
    ```

After registration, verify the environment:

```bash
az ml environment show --name my-kedro-env --version latest \
  --workspace-name <workspace> --resource-group <rg>
```

## Reference the environment in `azureml.yml`

```yaml
execution:
  environment: "my-kedro-env@latest"
  code_directory: "."
```

Use `@latest` to always pick the newest version, or pin a specific version with `:3` (e.g. `my-kedro-env:3`).

## Keep local and remote dependencies in sync

A common pain point is packages that work locally but are missing in the Azure ML environment. To avoid this:

1. Generate `requirements.txt` from your lock file before building:

    ```bash
    uv export --no-dev --no-hashes > requirements.txt
    ```

2. Rebuild and re-register the environment whenever dependencies change.

3. Test the environment by running a quick job:

    ```bash
    kedro azureml run -j <job> --wait-for-completion
    ```

    Check the step logs in Azure ML Studio for import errors.

## See also

- [Configuration reference](../reference/configuration.md#execution) for the `execution.environment` field
- [Azure ML environments documentation](https://learn.microsoft.com/en-us/azure/machine-learning/concept-environments) for full environment management options
