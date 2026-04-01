# Empty file to load `tests` module as Kedro project
from kedro.config import OmegaConfigLoader  # new import

CONFIG_LOADER_CLASS = OmegaConfigLoader

# Allowed third-party plugin hooks for tests
ALLOWED_HOOK_PLUGINS = ("kedro_azureml_pipeline", "kedro-mlflow")
