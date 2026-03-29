"""Shared utility functions and data classes."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass
class CliContext:
    """Runtime context passed to CLI command handlers.

    Parameters
    ----------
    env : str
        Kedro environment name.
    metadata : Any
        Kedro ``ProjectMetadata`` instance.

    See Also
    --------
    `kedro_azureml_pipeline.manager.KedroContextManager` : Uses env from this context.
    `kedro_azureml_pipeline.cli_functions.submit_scheduled_jobs` : Receives this as ``ctx``.
    """

    env: str
    metadata: Any


def update_dict(dictionary, *kv_pairs):
    """Return a deep copy of *dictionary* with nested keys updated.

    Parameters
    ----------
    dictionary : dict
        Source dictionary to copy.
    *kv_pairs : tuple of (str, Any)
        Key-value pairs where keys use dot notation for nesting
        (e.g. ``"a.b.c"``). Each pair is a 2-tuple.

    Returns
    -------
    dict
        Updated deep copy.
    """
    updated = deepcopy(dictionary)

    def traverse(d, key, value):
        """Recursively set a nested key."""
        s = key.split(".", 1)
        if len(s) > 1:
            if (s[0] not in d) or (not isinstance(d[s[0]], dict)):
                d[s[0]] = {}
            traverse(d[s[0]], s[1], value)
        else:
            d[s[0]] = value

    for k, v in kv_pairs:
        traverse(updated, k, v)
    return updated
