# Concepts

Kedro-AzureML-Pipeline is a Kedro plugin that lets you run Kedro pipelines on Azure ML managed compute without modifying your pipeline code. It translates Kedro's pipeline abstraction into Azure ML pipeline jobs, where each Kedro node becomes a separate containerized step running on cloud infrastructure.

!!! note "Fork history"
    This project is a fork of [kedro-azureml](https://github.com/getindata/kedro-azureml), originally developed by [GetInData](https://github.com/getindata). We have continued development to add new features, improve documentation, and maintain the project under the `kedro-azureml-pipeline` package name.

This page introduces the core ideas behind the plugin and explains how Kedro and Azure ML fit together.

## The pipeline-as-a-service alignment

Kedro already organizes data science work into modular, testable pipelines with a declarative data catalog. Azure ML provides managed compute, experiment tracking, and enterprise-grade scheduling. Kedro-AzureML-Pipeline bridges the two so that the same pipeline definition runs locally during development and remotely in production.

The plugin works by compiling your Kedro pipeline graph into an Azure ML pipeline specification. Each Kedro node becomes an Azure ML component (a container step), and the data catalog determines how data flows between steps. No Azure ML-specific code is needed in your nodes.

### For Kedro users

If you already have a Kedro project, the plugin gives you:

- **Managed compute**: run pipelines on GPU clusters, Spark pools, or auto-scaling CPU clusters without infrastructure management
- **Data asset versioning**: register and version datasets as Azure ML Data Assets, tracked across experiments
- **Distributed training**: scale nodes across multiple GPUs with the `@distributed_job` decorator
- **Scheduling**: trigger pipelines on cron or recurrence schedules through configuration alone
- **MLflow integration**: Kedro-MLflow hooks fire during remote execution and log to Azure ML's native MLflow backend
- **No code changes**: your existing pipeline nodes, catalog entries, and parameters work as-is

See the [Azure ML documentation](https://learn.microsoft.com/en-us/azure/machine-learning/) for capabilities of the underlying platform.

### For Azure ML users

If you already use Azure ML, the plugin gives you:

- **Structured projects**: Kedro's opinionated project template keeps code, configuration, and data organized
- **Modular pipelines**: compose and reuse pipeline fragments across different jobs
- **Declarative catalog**: define all data sources in YAML instead of scattering I/O logic through code
- **Testable nodes**: pure functions with explicit inputs and outputs are straightforward to unit test
- **Environment-specific configuration**: separate base, local, and production settings cleanly

See the [Kedro documentation](https://docs.kedro.org/) for the full project framework.

## Key features

### Configuration-driven workflows

All Azure ML-specific settings live in `azureml.yml` files under Kedro's `conf/` directory structure. This separates infrastructure concerns (compute targets, environments, workspace credentials) from pipeline logic (nodes, catalog, parameters). Different environments (local, staging, production) each get their own configuration without touching the pipeline code.

### Data asset management

The `AzureMLAssetDataset` wraps any Kedro dataset and registers it as a versioned Azure ML Data Asset. Data is downloaded to the local filesystem on first access and uploaded after saving, giving nodes a familiar file-based interface while Azure ML tracks lineage and versions. For intermediate step outputs, `AzureMLPipelineDataset` handles temporary data mounting between container steps automatically.

### Distributed training

The `@distributed_job` decorator marks a node for multi-GPU or multi-node training. The plugin configures the Azure ML distribution strategy (PyTorch, TensorFlow, or MPI) and scales the node across the specified number of instances. The decorated function receives standard distributed training environment variables and runs identically to a local distributed launch.

### Kedro hooks preservation

The full Kedro hook lifecycle fires during remote execution. Each pipeline step bootstraps its own `KedroSession`, which means hooks like `before_node_run`, `after_node_run`, and dataset hooks all work as expected. The `MlflowAzureMLHook` coordinates kedro-mlflow with Azure ML's native MLflow tracking backend so that metrics, parameters, and artifacts land in the right experiment.

### Scheduling

Pipelines can run on automated schedules defined in configuration. Cron expressions and recurrence patterns are supported. Schedules are created as Azure ML `JobSchedule` objects, so they run independently in the cloud without requiring a local process or external orchestrator.

## Limitations and considerations

- **Feature parity**: Azure ML's pipeline model and Kedro's pipeline model may not overlap perfectly. Open an issue if you encounter a Kedro pattern that doesn't translate well to Azure ML, or if an Azure ML feature is missing from the plugin's capabilities.
- **Version compatibility**: the plugin is tested against specific ranges of `kedro` and `azure-ai-ml` SDK versions. Pin your dependencies to avoid unexpected breakage when either library releases a new major version.
- **Cold start overhead**: each pipeline step runs in its own container, which adds startup time compared to local execution. This is inherent to Azure ML's execution model and is most noticeable on small, fast nodes.

## See also

- [Architecture](architecture.md): how the plugin compiles and executes pipelines
- [Data Flow Between Steps](data-flow.md): how datasets are routed between containers
- [Hook Lifecycle](hook-lifecycle.md): how Kedro hooks fire during remote execution
- [Getting Started](../tutorials/getting-started.md): step-by-step setup tutorial
