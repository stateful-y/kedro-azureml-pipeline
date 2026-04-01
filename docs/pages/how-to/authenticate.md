# How to Authenticate

This guide shows you how to configure Azure credentials for the plugin. The authentication method depends on where you are running: local development, CI/CD pipelines, or Azure ML compute.

## Prerequisites

- `kedro-azureml-pipeline` installed ([Getting Started](../tutorials/getting-started.md))
- An Azure ML workspace with your user or service principal assigned the `Contributor` or `AzureML Data Scientist` role

## How the credential chain works

The plugin uses `DefaultAzureCredential` from the Azure Identity SDK. This tries multiple credential sources in order and uses the first one that succeeds:

1. Environment variables (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`)
2. Azure CLI session (`az login`)
3. Visual Studio Code credential
4. Azure PowerShell credential
5. Interactive browser login (fallback)

On Azure ML compute instances, the plugin disables the managed identity credential to avoid permission conflicts with the compute's own identity. If `DefaultAzureCredential` fails entirely, it falls back to `InteractiveBrowserCredential` for interactive environments.

## Local development

Log in with the Azure CLI:

```bash
az login
```

Verify you can reach your workspace:

```bash
az ml workspace show --name <your-workspace> --resource-group <your-rg>
```

This is all you need for `kedro run` (local execution) and `kedro azureml run` (submitting jobs to Azure ML).

## CI/CD and automated environments

For non-interactive environments like GitHub Actions or other CI/CD systems, use a service principal.

### Create a service principal

```bash
az ad sp create-for-rbac --name "kedro-azureml-ci" --role "AzureML Data Scientist" \
  --scopes /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.MachineLearningServices/workspaces/<workspace-name>
```

Save the output. You will need `appId` (client ID), `password` (client secret), and `tenant`.

### Set environment variables

The plugin picks up service principal credentials through three environment variables:

```bash
export AZURE_TENANT_ID="<tenant>"
export AZURE_CLIENT_ID="<appId>"
export AZURE_CLIENT_SECRET="<password>"
```

### GitHub Actions example

```yaml
- name: Submit pipeline
  env:
    AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
    AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
    AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  run: kedro azureml run -j main
```

## Required roles

The identity (user or service principal) needs one of these roles on the Azure ML workspace:

| Role | Allows |
|---|---|
| `AzureML Data Scientist` | Submit jobs, read/write data assets, manage experiments |
| `Contributor` | Full workspace access including compute management |

If you only need to submit jobs and track experiments, `AzureML Data Scientist` is sufficient and follows the principle of least privilege.

## Troubleshooting

**`CredentialUnavailableError` or `AuthenticationError`**
: Azure credentials are missing or expired. Run `az login` for local development, or verify that `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are set in your CI/CD environment.

**`AuthorizationPermissionMismatch` when accessing data assets**
: The identity does not have the `Storage Blob Data Contributor` role on the storage account backing the data assets. Assign this role in the Azure Portal under the storage account's Access Control (IAM).

**Interactive browser popup on a headless server**
: The plugin falls back to `InteractiveBrowserCredential` when `DefaultAzureCredential` fails. On servers without a browser, set the service principal environment variables instead.

## See also

- [How to deploy from CI/CD](deploy-from-cicd.md): full CI/CD pipeline setup including callbacks and batch submission
- [Troubleshoot](troubleshoot.md): broader troubleshooting guide
- [Configuration reference](../reference/configuration.md): workspace configuration fields
