"""Implementation helpers for CLI commands."""

import importlib
import json
import logging
import re
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import click

from kedro_azureml_pipeline.generator import AzureMLPipelineGenerator
from kedro_azureml_pipeline.manager import KedroContextManager
from kedro_azureml_pipeline.utils import CliContext

logger = logging.getLogger()


def _read_mlflow_experiment_name(mgr: KedroContextManager) -> str | None:
    """Read experiment name from ``mlflow.yml`` via the Kedro config loader.

    Parameters
    ----------
    mgr : KedroContextManager
        Active context manager.

    Returns
    -------
    str or None
        Experiment name, or ``None`` if not configured.
    """
    try:
        mlflow_config = mgr.context.config_loader["mlflow"]
        name = mlflow_config.get("tracking", {}).get("experiment", {}).get("name")
        if name:
            logger.info(f"Using experiment name from mlflow.yml: {name}")
            return name
        logger.warning("mlflow.yml found but tracking.experiment.name is not set.")
    except (KeyError, TypeError):
        logger.info("No mlflow.yml configuration found. Experiment name must be provided via --experiment-name.")
    return None


def parse_runtime_params(params, silent=False):
    """Parse a JSON string of runtime parameters.

    Parameters
    ----------
    params : str
        JSON string of parameters, or falsy value.
    silent : bool
        Suppress console output when ``True``.

    Returns
    -------
    dict or None
        Parsed parameters dictionary, or ``None`` when *params* is
        empty or falsy.
    """
    if params and (parameters := json.loads(params.strip("'"))):
        if not silent:
            click.echo(f"Running with extra parameters:\n{json.dumps(parameters, indent=4)}")
    else:
        parameters = None
    return parameters


def warn_about_ignore_files():
    """Emit warnings about ``.amlignore`` and ``.gitignore`` files.

    Checks the current working directory for ignore files that control
    which source files are uploaded to Azure ML.
    """
    aml_ignore = Path.cwd().joinpath(".amlignore")
    git_ignore = Path.cwd().joinpath(".gitignore")
    if aml_ignore.exists():
        ignore_contents = aml_ignore.read_text().strip()
        if not ignore_contents:
            click.echo(
                click.style(
                    f".amlignore file is empty, which means all of the files from {Path.cwd()}"
                    "\nwill be uploaded to Azure ML. Make sure that you excluded sensitive files first!",
                    fg="yellow",
                )
            )
    elif git_ignore.exists():
        ignore_contents = git_ignore.read_text().strip()
        if ignore_contents:
            click.echo(
                click.style(
                    ".gitignore file detected, ignored files will not be uploaded to Azure ML"
                    "\nWe recommend to use .amlignore instead of .gitignore when working with Azure ML"
                    "\nSee https://github.com/MicrosoftDocs/azure-docs/blob/047cb7f625920183438f3e66472014ac2ebab098/includes/machine-learning-amlignore-gitignore.md",  # noqa
                    fg="yellow",
                )
            )


def verify_configuration_directory_for_azure(click_context, ctx: CliContext):
    """Check that the Kedro environment config directory is non-empty.

    If the directory is missing, empty, or contains only empty files,
    the user is prompted to continue or abort.

    Parameters
    ----------
    click_context : click.Context
        Active Click context (used for ``exit``).
    ctx : CliContext
        CLI context containing the Kedro environment name.
    """
    conf_dir = Path.cwd().joinpath(f"conf/{ctx.env}")

    exists = conf_dir.exists() and conf_dir.is_dir()
    is_empty = True
    has_only_empty_files = True

    if exists:
        for p in conf_dir.iterdir():
            is_empty = False
            if p.is_file():
                has_only_empty_files = p.lstat().st_size == 0

            if not has_only_empty_files:
                break

    msg = f"Configuration folder for your Kedro environment {conf_dir} "
    if not exists:
        msg += "does not exist or is not a directory,"
    if is_empty:
        msg += "is empty,"
    elif has_only_empty_files:
        msg += "contains only empty files,"

    if is_empty or has_only_empty_files:
        msg += (
            "\nwhich might cause issues when running in Azure ML."
            + "\nEither use different environment or provide non-empty configuration for your env."
            + "\nContinue?"
        )
        if not click.confirm(click.style(msg, fg="yellow")):
            click_context.exit(2)


def parse_extra_env_params(extra_env):
    """Validate and parse ``KEY=VALUE`` environment variable strings.

    Parameters
    ----------
    extra_env : iterable of str
        Strings in ``KEY=VALUE`` format.

    Returns
    -------
    dict of str to str
        Mapping of variable names to values.

    Raises
    ------
    Exception
        If any entry does not match the expected ``KEY=VALUE`` format.
    """
    for entry in extra_env:
        if not re.match("[A-Za-z0-9_]+=.*", entry):
            raise Exception(f"Invalid env-var: {entry}, expected format: KEY=VALUE")

    return {(e := entry.split("=", maxsplit=1))[0]: e[1] for entry in extra_env}


def dynamic_import_job_schedule_func_from_str(
    ctx: click.Context,
    param: click.Parameter,
    import_str: str,
) -> Callable | None:
    """Dynamically import a callback function from a dotted path.

    Parameters
    ----------
    ctx : click.Context
        Active Click context.
    param : click.Parameter
        Click parameter that triggered this callback.
    import_str : str
        Import path in ``module.path:function_name`` format.

    Returns
    -------
    callable or None
        Imported function, or ``None`` if *import_str* is ``None``.

    Raises
    ------
    click.BadParameter
        If the format is invalid, the module cannot be imported,
        or the attribute is not callable.
    """
    # base case: no callback
    if import_str is None:
        return

    # check format
    module_str, _, attrs_str = import_str.partition(":")
    if not module_str or not attrs_str:
        raise click.BadParameter("import_str must be in format <module>:<function>", param=param)

    try:
        module = importlib.import_module(module_str)
        instance = getattr(module, attrs_str)

        # fails if we try to import an attribute that is not a function
        if not callable(instance):
            raise click.BadParameter(f"The attribute '{attrs_str}' is not a callable function.", param=param)

        return instance
    except (ImportError, AttributeError, ValueError) as e:
        # catches errors if module or attribute does not exist
        raise click.BadParameter(f"Error: {e}", param=param) from e


def default_job_callback(job):
    """Print the Azure ML Studio URL after a job is scheduled.

    Parameters
    ----------
    job : Job
        The Azure ML pipeline job that was created.
    """
    click.echo(job.studio_url)


def compile_job_pipelines(
    ctx: CliContext,
    aml_env: str | None,
    params: str,
    extra_env: dict[str, str],
    load_versions: dict[str, str],
    job_names: list[str],
    output: str,
):
    """Compile pipelines for named jobs into YAML files.

    Parameters
    ----------
    ctx : CliContext
        CLI context containing the Kedro environment and metadata.
    aml_env : str or None
        Azure ML Environment override.
    params : str
        Runtime parameters override as a JSON string.
    extra_env : dict of str to str
        Extra environment variables to inject into steps.
    load_versions : dict of str to str
        Dataset version overrides.
    job_names : list of str
        Names of jobs to compile (must exist in config).
    output : str
        Output file path. Suffixed with the job name for multiple jobs.

    Raises
    ------
    click.ClickException
        If no ``jobs`` section is found or a requested job is missing.
    """
    with KedroContextManager(env=ctx.env, runtime_params=parse_runtime_params(params, True)) as mgr:
        config = mgr.plugin_config

        if not config.jobs:
            raise click.ClickException("No 'jobs' section found in azureml.yml config.")

        missing = set(job_names) - set(config.jobs.keys())
        if missing:
            raise click.ClickException(
                f"Job(s) not found in config: {', '.join(sorted(missing))}. "
                f"Available jobs: {', '.join(sorted(config.jobs.keys()))}"
            )

        selected_jobs = {k: v for k, v in config.jobs.items() if k in job_names}

        output_path = Path(output)
        multi = len(selected_jobs) > 1

        # Read default experiment name from mlflow.yml
        default_experiment_name = _read_mlflow_experiment_name(mgr)

        for job_name, job_config in selected_jobs.items():
            pipeline_opts = job_config.pipeline

            # Resolve experiment name: job > mlflow.yml > None
            job_experiment_name = job_config.experiment_name or default_experiment_name
            mlflow_run_name = job_config.display_name or job_name

            generator = AzureMLPipelineGenerator(
                pipeline_opts.pipeline_name,
                ctx.env,
                config,
                mgr.context.params,
                mgr.context.catalog,
                aml_env,
                params,
                extra_env=extra_env,
                load_versions=load_versions,
                filter_options=pipeline_opts,
                mlflow_run_name=mlflow_run_name,
                experiment_name=job_experiment_name,
            )
            az_pipeline = generator.generate()

            dest = output_path.with_stem(f"{output_path.stem}_{job_name}") if multi else output_path

            dest.write_text(str(az_pipeline))
            click.echo(f"Compiled job '{job_name}' to {dest}")


@contextmanager
def _prepare_jobs(
    ctx: CliContext,
    aml_env: str | None,
    params: str,
    extra_env: dict[str, str],
    load_versions: dict[str, str],
    job_names: list[str] | None,
):
    """Context manager that loads config, validates jobs, and generates pipelines.

    Parameters
    ----------
    ctx : CliContext
        CLI context containing the Kedro environment and metadata.
    aml_env : str or None
        Azure ML Environment override.
    params : str
        Runtime parameters override as a JSON string.
    extra_env : dict of str to str
        Extra environment variables to inject into steps.
    load_versions : dict of str to str
        Dataset version overrides.
    job_names : list of str or None
        If given, only prepare these jobs.

    Yields
    ------
    tuple
        ``(config, selected_jobs, prepared)`` where *prepared* is a dict
        mapping job names to ``(job_experiment_name, pipeline_job, job_config)``
        tuples.
    """
    with KedroContextManager(env=ctx.env, runtime_params=parse_runtime_params(params, True)) as mgr:
        config = mgr.plugin_config

        if not config.jobs:
            raise click.ClickException(
                "No 'jobs' section found in azureml.yml config. Define jobs to use this command."
            )

        selected_jobs = config.jobs
        if job_names:
            missing = set(job_names) - set(config.jobs.keys())
            if missing:
                raise click.ClickException(
                    f"Job(s) not found in config: {', '.join(sorted(missing))}. "
                    f"Available jobs: {', '.join(sorted(config.jobs.keys()))}"
                )
            selected_jobs = {k: v for k, v in config.jobs.items() if k in job_names}

        # Read default experiment name from mlflow.yml
        default_experiment_name = _read_mlflow_experiment_name(mgr)

        prepared: dict[str, tuple] = {}
        for job_name, job_config in selected_jobs.items():
            job_experiment_name = job_config.experiment_name or default_experiment_name
            mlflow_run_name = job_config.display_name or job_name

            pipeline_opts = job_config.pipeline
            generator = AzureMLPipelineGenerator(
                pipeline_opts.pipeline_name,
                ctx.env,
                config,
                mgr.context.params,
                mgr.context.catalog,
                aml_env,
                params,
                extra_env=extra_env,
                load_versions=load_versions,
                filter_options=pipeline_opts,
                mlflow_run_name=mlflow_run_name,
                experiment_name=job_experiment_name,
            )
            pipeline_job = generator.generate()

            if job_config.display_name:
                pipeline_job.display_name = job_config.display_name

            prepared[job_name] = (job_experiment_name, pipeline_job, job_config)

        yield config, selected_jobs, prepared


def run_jobs(
    ctx: CliContext,
    aml_env: str | None,
    params: str,
    extra_env: dict[str, str],
    load_versions: dict[str, str],
    job_names: list[str] | None,
    dry_run: bool,
    wait_for_completion: bool = False,
    on_job_scheduled: Callable | None = None,
    workspace_override: str | None = None,
):
    """Run jobs immediately, ignoring any configured schedule.

    Parameters
    ----------
    ctx : CliContext
        CLI context containing the Kedro environment and metadata.
    aml_env : str or None
        Azure ML Environment override.
    params : str
        Runtime parameters override as a JSON string.
    extra_env : dict of str to str
        Extra environment variables to inject into steps.
    load_versions : dict of str to str
        Dataset version overrides.
    job_names : list of str or None
        If given, only run these jobs.
    dry_run : bool
        Preview mode: print what would happen without calling Azure ML.
    wait_for_completion : bool
        Block until the pipeline run completes.
    on_job_scheduled : callable or None
        Callback invoked after each job is submitted.
    workspace_override : str or None
        Named workspace override for all jobs in this batch.

    Returns
    -------
    bool
        ``True`` if all jobs ran successfully.
    """
    from kedro_azureml_pipeline.client import AzureMLPipelinesClient

    with _prepare_jobs(ctx, aml_env, params, extra_env, load_versions, job_names) as (
        config,
        selected_jobs,
        prepared,
    ):
        results: dict[str, bool] = {}

        for job_name in selected_jobs:
            try:
                job_experiment_name, pipeline_job, job_config = prepared[job_name]
                workspace = config.workspace.resolve(workspace_override or job_config.workspace)
                pipeline_opts = job_config.pipeline

                if dry_run:
                    click.echo(
                        f"[DRY RUN] Would run job '{job_name}' immediately (pipeline '{pipeline_opts.pipeline_name}')"
                    )
                    results[job_name] = True
                else:
                    job_callback = on_job_scheduled or default_job_callback
                    az_client = AzureMLPipelinesClient(pipeline_job)
                    is_ok = az_client.run(
                        workspace,
                        config.compute,
                        wait_for_completion=wait_for_completion,
                        on_job_scheduled=job_callback,
                        compute_name=job_config.compute,
                        experiment_name=job_experiment_name,
                    )
                    if is_ok:
                        click.echo(
                            click.style(
                                f"Job '{job_name}' submitted for immediate execution",
                                fg="green",
                            )
                        )
                    results[job_name] = is_ok

            except Exception as e:
                click.echo(click.style(f"Failed to run job '{job_name}': {e}", fg="red"))
                logger.exception(f"Error running job '{job_name}'")
                results[job_name] = False

        succeeded = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        click.echo(f"\nRun summary: {succeeded} succeeded, {failed} failed (out of {len(results)} jobs)")

        return all(results.values())


def schedule_jobs(
    ctx: CliContext,
    aml_env: str | None,
    params: str,
    extra_env: dict[str, str],
    load_versions: dict[str, str],
    job_names: list[str] | None,
    dry_run: bool,
    workspace_override: str | None = None,
):
    """Create or update persistent Azure ML schedules for jobs.

    Every selected job must have a ``schedule`` configured; otherwise
    a ``ClickException`` is raised.

    Parameters
    ----------
    ctx : CliContext
        CLI context containing the Kedro environment and metadata.
    aml_env : str or None
        Azure ML Environment override.
    params : str
        Runtime parameters override as a JSON string.
    extra_env : dict of str to str
        Extra environment variables to inject into steps.
    load_versions : dict of str to str
        Dataset version overrides.
    job_names : list of str or None
        If given, only schedule these jobs.
    dry_run : bool
        Preview mode: print what would happen without calling Azure ML.
    workspace_override : str or None
        Named workspace override for all jobs in this batch.

    Returns
    -------
    bool
        ``True`` if all schedules were created/updated successfully.
    """
    from kedro_azureml_pipeline.scheduler import (
        AzureMLScheduleClient,
        build_job_schedule,
        build_trigger,
        resolve_schedule,
    )

    with _prepare_jobs(ctx, aml_env, params, extra_env, load_versions, job_names) as (
        config,
        selected_jobs,
        prepared,
    ):
        # Validate that all selected jobs have a schedule configured
        missing_schedule = [name for name, cfg in selected_jobs.items() if cfg.schedule is None]
        if missing_schedule:
            raise click.ClickException(
                f"Job(s) have no schedule configured: {', '.join(sorted(missing_schedule))}. "
                f"Add a schedule to the job config or use 'kedro azureml run' instead."
            )

        schedule_client = AzureMLScheduleClient()
        results: dict[str, bool] = {}

        for job_name in selected_jobs:
            try:
                job_experiment_name, pipeline_job, job_config = prepared[job_name]
                workspace = config.workspace.resolve(workspace_override or job_config.workspace)
                pipeline_opts = job_config.pipeline

                schedule_cfg = resolve_schedule(job_config.schedule, config.schedules)
                trigger = build_trigger(schedule_cfg)

                job_schedule = build_job_schedule(
                    name=job_name,
                    trigger=trigger,
                    pipeline_job=pipeline_job,
                    display_name=job_config.display_name,
                    description=job_config.description,
                )

                if dry_run:
                    trigger_desc = (
                        f"cron: {schedule_cfg.cron.expression}"
                        if schedule_cfg.cron
                        else f"recurrence: every {schedule_cfg.recurrence.interval} {schedule_cfg.recurrence.frequency}(s)"
                    )
                    click.echo(
                        f"[DRY RUN] Would create schedule '{job_name}' "
                        f"({trigger_desc}) "
                        f"for pipeline '{pipeline_opts.pipeline_name}'"
                    )
                    results[job_name] = True
                else:
                    result = schedule_client.create_or_update_schedule(
                        job_schedule,
                        workspace,
                    )
                    click.echo(
                        click.style(
                            f"Schedule '{result.name}' created/updated successfully",
                            fg="green",
                        )
                    )
                    results[job_name] = True

            except Exception as e:
                click.echo(click.style(f"Failed to schedule job '{job_name}': {e}", fg="red"))
                logger.exception(f"Error scheduling job '{job_name}'")
                results[job_name] = False

        succeeded = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        click.echo(f"\nSchedule summary: {succeeded} succeeded, {failed} failed (out of {len(results)} jobs)")

        return all(results.values())
