# How to Run Distributed Training

This guide shows how to mark Kedro nodes for distributed execution on Azure ML using the [`@distributed_job`][kedro_azureml_pipeline.distributed.distributed_job] decorator.

## Prerequisites

- A Kedro project with the plugin installed and configured (see [Getting Started](../tutorials/getting-started.md))
- An Azure ML compute cluster with multiple nodes available
- An Azure ML environment with your distributed training framework installed (PyTorch, TensorFlow, or MPI)

## Decorate a node function

Import the decorator and mark the function you want to run as a distributed step:

```python
from kedro_azureml_pipeline.distributed import distributed_job, Framework

@distributed_job(framework=Framework.PyTorch, num_nodes=4)
def train_model(X_train, y_train):
    import torch.distributed as dist
    dist.init_process_group("nccl")
    # ... distributed training logic
    return trained_model
```

Use the decorated function when registering your Kedro node:

```python
from kedro.pipeline import node

train_node = node(
    func=train_model,
    inputs=["X_train", "y_train"],
    outputs="trained_model",
    name="train_model_node",
)
```

## Supported frameworks

| Framework enum value | Distributed backend |
|---|---|
| `Framework.PyTorch` | PyTorch distributed (NCCL or Gloo) |
| `Framework.TensorFlow` | TensorFlow distributed strategy |
| `Framework.MPI` | MPI (Message Passing Interface) |

## Set the number of processes per node

Use `processes_per_node` to launch multiple worker processes on each node:

```python
@distributed_job(framework=Framework.PyTorch, num_nodes=4, processes_per_node=8)
def train_model(X_train, y_train):
    ...
```

## Use a Kedro parameter for node count

Pass a `params:` reference to make the node count configurable per environment:

```python
@distributed_job(framework=Framework.PyTorch, num_nodes="params:num_training_nodes")
def train_model(X_train, y_train):
    ...
```

Then set the value in `conf/base/parameters.yml`:

```yaml
num_training_nodes: 4
```

## How it works

During local runs, `@distributed_job` has no effect and the function runs normally. During Azure ML runs, the pipeline generator wraps the step in a distributed job configuration. See the [architecture overview](../explanation/architecture.md) for details on pipeline compilation.

!!! tip "Checking rank inside a node"

    Use [`is_distributed_master_node()`][kedro_azureml_pipeline.distributed.is_distributed_master_node] to check whether the current process is rank 0. This is useful for logging or saving artifacts only from the master node:

    ```python
    from kedro_azureml_pipeline.distributed import is_distributed_master_node

    if is_distributed_master_node():
        mlflow.log_artifact("model.pkl")
    ```

!!! note

    If your compute cluster has fewer nodes than `num_nodes`, Azure ML queues the job until enough nodes become available. The job will not fail immediately, but it may wait indefinitely if the cluster's maximum node count is lower than the requested count.

## See also

- [Architecture overview](../explanation/architecture.md) for how the pipeline generator translates Kedro nodes to Azure ML steps
- [`distributed_job`][kedro_azureml_pipeline.distributed.distributed_job] API for the decorator parameter reference
- [`Framework`][kedro_azureml_pipeline.distributed.Framework] API for supported framework values
