# Explanation

Explanation pages help you understand how the plugin works and the reasoning behind its design. Read these when you want to build a mental model of the system rather than accomplish a specific task.

- [**Concepts**](concepts.md): Core ideas behind the plugin, how Kedro and Azure ML fit together, and key features.
- [**Architecture Overview**](architecture.md): How the plugin translates Kedro pipelines into Azure ML pipeline jobs, the two execution contexts, and the compilation process.
- [**Data Flow Between Steps**](data-flow.md): How data moves between pipeline steps during remote execution, the three dataset paths, and how the runner rewires paths at runtime.
- [**Hook Lifecycle in Remote Execution**](hook-lifecycle.md): How the full Kedro hook lifecycle is preserved in remote steps, the bootstrap sequence, and kedro-mlflow coordination.
