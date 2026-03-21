import importlib
import json
import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

import click

from kedro_azureml.generator import AzureMLPipelineGenerator
from kedro_azureml.manager import KedroContextManager
from kedro_azureml.utils import CliContext

logger = logging.getLogger()


def _read_mlflow_experiment_name(mgr: KedroContextManager) -> Optional[str]:
    """Read experiment name from mlflow.yml via the Kedro config loader."""
    try:
        mlflow_config = mgr.context.config_loader["mlflow"]
        name = mlflow_config.get("tracking", {}).get("experiment", {}).get("name")
        if name:
            logger.info(f"Using experiment name from mlflow.yml: {name}")
            return name
        logger.warning(
            "mlflow.yml found but tracking.experiment.name is not set."
        )
    except (KeyError, TypeError):
        logger.info(
            "No mlflow.yml configuration found. "
            "Experiment name must be provided via --experiment-name."
        )
    return None


def parse_runtime_params(params, silent=False):
    """Parse a JSON string of runtime parameters.

    If *params* is a non-empty JSON string it is decoded and, unless
    *silent* is ``True``, echoed to the console.

    :param params: JSON string of parameters, or falsy value.
    :type params: str
    :param silent: Suppress console output when ``True``.
    :type silent: bool

    :returns: Parsed parameters dictionary, or ``None`` when *params*
        is empty or falsy.
    :rtype: Optional[dict]
    """
    if params and (parameters := json.loads(params.strip("'"))):
        if not silent:
            click.echo(
                f"Running with extra parameters:\n{json.dumps(parameters, indent=4)}"
            )
    else:
        parameters = None
    return parameters


def warn_about_ignore_files():
    """Emit warnings about ``.amlignore`` and ``.gitignore`` files.

    Checks the current working directory for ignore files that control
    which files are uploaded to Azure ML during code-upload runs, and
    prints a yellow warning if the configuration looks problematic
    (e.g. an empty ``.amlignore``).
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
    the user is prompted to continue or abort. Aborting exits with
    code 2.

    :param click_context: The active Click context (used for ``exit``).
    :type click_context: click.Context
    :param ctx: CLI context containing the Kedro environment name.
    :type ctx: CliContext
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

    :param extra_env: Iterable of strings in ``KEY=VALUE`` format.
    :type extra_env: Iterable[str]

    :returns: Mapping of environment variable names to values.
    :rtype: Dict[str, str]

    :raises Exception: If any entry does not match the ``KEY=VALUE``
        format.
    """
    for entry in extra_env:
        if not re.match("[A-Za-z0-9_]+=.*", entry):
            raise Exception(f"Invalid env-var: {entry}, expected format: KEY=VALUE")

    return {(e := entry.split("=", maxsplit=1))[0]: e[1] for entry in extra_env}


def dynamic_import_job_schedule_func_from_str(
    ctx: click.Context,
    param: click.Parameter,
    import_str: str,
) -> Optional[Callable]:
    """
    Dynamically import and retrieve a function from a specified module.

    The function must have exactly one parameter of type azure.ai.ml.entities.Job.
    Note that there is no  check on the parameter type
    This function is designed to be used in Click-based command-line applications.

    :param ctx: The Click context.
    :type ctx: click.Context
    :param param: The Click parameter associated with this function.
    :type param: click.Parameter
    :param import_str: A string in the format 'path.to.file:function'
        specifying the module and function to import.
    :type import_str: str

    :returns: The imported function.
    :rtype: Any

    :raises click.BadParameter: If the `import_str` is not in the correct format,
        if the specified module cannot be imported,
        if the specified attribute cannot be retrieved from the module,
        if the retrieved attribute is not a callable function,

    Example usage:
    >>> instance = dynamic_import_job_schedule_func_from_str(
        ctx, param, "my_module:my_function"
    )

    Inspired by the `uvicorn/importer.py` module's `import_from_string` function.
    """
    # base case: no callback
    if import_str is None:
        return

    # check format
    module_str, _, attrs_str = import_str.partition(":")
    if not module_str or not attrs_str:
        raise click.BadParameter(
            "import_str must be in format <module>:<function>", param=param
        )

    try:
        module = importlib.import_module(module_str)
        instance = getattr(module, attrs_str)

        # fails if we try to import an attribute that is not a function
        if not callable(instance):
            raise click.BadParameter(
                f"The attribute '{attrs_str}' is not a callable function.", param=param
            )

        return instance
    except (ImportError, AttributeError, ValueError) as e:
        # catches errors if module or attribute does not exist
        raise click.BadParameter(f"Error: {e}", param=param)


def default_job_callback(job):
    """Default callback invoked after a job is scheduled.

    Prints the Azure ML Studio URL to the console.

    :param job: The Azure ML pipeline job that was created.
    :type job: azure.ai.ml.entities.Job
    """
    click.echo(job.studio_url)


def compile_job_pipelines(
    ctx: CliContext,
    aml_env: Optional[str],
    params: str,
    extra_env: Dict[str, str],
    load_versions: Dict[str, str],
    job_names: List[str],
    output: str,
):
    """
    Compile pipelines for named jobs into YAML files.

    Each selected job is resolved from the ``jobs`` config section,
    its Kedro pipeline is generated as an Azure ML pipeline definition,
    and the result is written to a YAML file.  When multiple jobs are
    compiled, each output file is suffixed with the job name.

    :param ctx: CLI context containing the Kedro environment and metadata.
    :type ctx: CliContext
    :param aml_env: Azure ML Environment override.
    :type aml_env: Optional[str]
    :param params: Runtime parameters override as a JSON string.
    :type params: str
    :param extra_env: Extra environment variables to inject into steps.
    :type extra_env: Dict[str, str]
    :param load_versions: Dataset version overrides.
    :type load_versions: Dict[str, str]
    :param job_names: Names of jobs to compile (must exist in config).
    :type job_names: List[str]
    :param output: Output file path.  Suffixed with the job name when
        compiling multiple jobs.
    :type output: str

    :raises click.ClickException: If no ``jobs`` section is found in
        config or if any requested job name is missing.
    """
    with KedroContextManager(
        env=ctx.env, runtime_params=parse_runtime_params(params, True)
    ) as mgr:
        config = mgr.plugin_config

        if not config.jobs:
            raise click.ClickException(
                "No 'jobs' section found in azureml.yml config."
            )

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

            if multi:
                dest = output_path.with_stem(f"{output_path.stem}_{job_name}")
            else:
                dest = output_path

            dest.write_text(str(az_pipeline))
            click.echo(f"Compiled job '{job_name}' to {dest}")


def submit_scheduled_jobs(
    ctx: CliContext,
    aml_env: Optional[str],
    params: str,
    extra_env: Dict[str, str],
    load_versions: Dict[str, str],
    job_names: Optional[List[str]],
    dry_run: bool,
    once: bool = False,
    wait_for_completion: bool = False,
    on_job_scheduled: Optional[Callable] = None,
    workspace_override: Optional[str] = None,
):
    """
    Submit jobs defined in the ``jobs`` section of ``azureml.yml``.

    Depending on each job's config and the *once* flag, jobs are either
    submitted as persistent Azure ML schedules or run immediately.

    :param ctx: CLI context containing the Kedro environment and metadata.
    :type ctx: CliContext
    :param aml_env: Azure ML Environment override.
    :type aml_env: Optional[str]
    :param params: Runtime parameters override as a JSON string.
    :type params: str
    :param extra_env: Extra environment variables to inject into steps.
    :type extra_env: Dict[str, str]
    :param load_versions: Dataset version overrides.
    :type load_versions: Dict[str, str]
    :param job_names: If given, only submit these jobs.
    :type job_names: Optional[List[str]]
    :param dry_run: Preview mode — print what would happen without
        calling Azure ML.
    :type dry_run: bool
    :param once: Force immediate run even when a schedule is configured.
    :type once: bool
    :param wait_for_completion: Block until the pipeline run completes.
    :type wait_for_completion: bool
    :param on_job_scheduled: Callback invoked after each job is scheduled.
    :type on_job_scheduled: Optional[Callable]

    :returns: ``True`` if all jobs were submitted successfully.
    :rtype: bool
    """
    from kedro_azureml.client import AzureMLPipelinesClient, _get_azureml_client
    from kedro_azureml.config import ScheduleConfig
    from kedro_azureml.scheduler import (
        AzureMLScheduleClient,
        build_job_schedule,
        build_trigger,
        resolve_schedule,
    )

    with KedroContextManager(
        env=ctx.env, runtime_params=parse_runtime_params(params, True)
    ) as mgr:
        config = mgr.plugin_config

        if not config.jobs:
            raise click.ClickException(
                "No 'jobs' section found in azureml.yml config. "
                "Define jobs to use the submit command."
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

        schedule_client = AzureMLScheduleClient()
        results: Dict[str, bool] = {}

        # Read default experiment name from mlflow.yml
        default_experiment_name = _read_mlflow_experiment_name(mgr)

        for job_name, job_config in selected_jobs.items():
            try:
                # Resolve workspace: CLI override > job-level > __default__
                workspace = config.workspace.resolve(
                    workspace_override or job_config.workspace
                )

                # Resolve experiment name: job-level override > mlflow.yml
                job_experiment_name = job_config.experiment_name or default_experiment_name
                mlflow_run_name = job_config.display_name or job_name

                # Generate pipeline job
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

                # Decide: schedule or immediate run
                has_schedule = job_config.schedule is not None
                run_immediately = once or not has_schedule

                if run_immediately:
                    # Immediate run via AzureMLPipelinesClient
                    if dry_run:
                        click.echo(
                            f"[DRY RUN] Would run job '{job_name}' immediately "
                            f"(pipeline '{pipeline_opts.pipeline_name}')"
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
                else:
                    # Persistent schedule
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
                click.echo(
                    click.style(
                        f"Failed to submit job '{job_name}': {e}",
                        fg="red",
                    )
                )
                logger.exception(f"Error submitting job '{job_name}'")
                results[job_name] = False

        # Summary
        succeeded = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        click.echo(
            f"\nSubmit summary: {succeeded} succeeded, {failed} failed "
            f"(out of {len(results)} jobs)"
        )

        return all(results.values())
