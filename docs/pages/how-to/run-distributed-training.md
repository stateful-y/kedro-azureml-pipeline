# How to Run Distributed Training

This guide shows how to mark Kedro nodes for distributed execution on Azure ML using the `@distributed_job` decorator.

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

## How it works during remote execution

When the pipeline generator encounters a node decorated with `@distributed_job`, it wraps that pipeline step in an Azure ML distributed job configuration. The step runs on `num_nodes` compute nodes simultaneously. Each node receives the same inputs and is expected to coordinate via the framework's native communication primitives (e.g. NCCL for PyTorch).

During local runs, `@distributed_job` has no effect - the function runs normally as a single-process Kedro node.

## See also

- [Architecture overview](../explanation/architecture.md) - how the pipeline generator translates Kedro nodes to Azure ML steps
- [`distributed_job` API](../reference/api.md) - decorator parameter reference
- [`Framework` API](../reference/api.md) - supported framework values
