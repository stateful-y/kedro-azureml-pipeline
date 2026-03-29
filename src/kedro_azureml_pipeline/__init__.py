"""Kedro AzureML Pipeline."""

from importlib.metadata import version

__version__ = version(__name__)
__all__ = ["__version__"]

import warnings

warnings.filterwarnings("ignore", module="azure.ai.ml")
