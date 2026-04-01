"""Shared constants for the Kedro AzureML Pipeline plugin.

See Also
--------
[KedroAzureMLConfig][kedro_azureml_pipeline.config.KedroAzureMLConfig] : Top-level plugin configuration.
[AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Reads constants during pipeline generation.
[MlflowAzureMLHook][kedro_azureml_pipeline.mlflow_hook.MlflowAzureMLHook] : Uses MLflow env var constants.
"""

DISTRIBUTED_CONFIG_FIELD = "__kedro_azureml_distributed_config__"
PARAMS_PREFIX = "params:"

# MLflow integration env vars (set by generator, read by MlflowAzureMLHook)
KEDRO_AZUREML_MLFLOW_ENABLED = "KEDRO_AZUREML_MLFLOW_ENABLED"
KEDRO_AZUREML_MLFLOW_RUN_NAME = "KEDRO_AZUREML_MLFLOW_RUN_NAME"
KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME = "KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME"
KEDRO_AZUREML_MLFLOW_NODE_NAME = "KEDRO_AZUREML_MLFLOW_NODE_NAME"
