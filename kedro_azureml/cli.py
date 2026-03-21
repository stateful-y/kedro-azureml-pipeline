import json
import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import click
from kedro.framework.cli.project import LOAD_VERSION_HELP
from kedro.framework.cli.utils import _split_load_versions
from kedro.framework.startup import ProjectMetadata

from kedro_azureml.cli_functions import (
    compile_job_pipelines,
    dynamic_import_job_schedule_func_from_str,
    parse_extra_env_params,
    parse_runtime_params,
    submit_scheduled_jobs,
    verify_configuration_directory_for_azure,
    warn_about_ignore_files,
)
from kedro_azureml.config import CONFIG_TEMPLATE_YAML
from kedro_azureml.manager import KedroContextManager
from kedro_azureml.runner import AzurePipelinesRunner
from kedro_azureml.utils import CliContext

logger = logging.getLogger(__name__)


@click.group("AzureML")
def commands():
    """Kedro plugin adding support for Azure ML Pipelines"""
    pass


@commands.group(
    name="azureml", context_settings=dict(help_option_names=["-h", "--help"])
)
@click.option(
    "-e",
    "--env",
    "env",
    type=str,
    default=lambda: os.environ.get("KEDRO_ENV", "local"),
    help="Environment to use.",
)
@click.pass_obj
@click.pass_context
def azureml_group(ctx, metadata: ProjectMetadata, env):
    ctx.obj = CliContext(env, metadata)


@azureml_group.command()
@click.argument("subscription_id")
@click.argument("resource_group")
@click.argument("workspace_name")
@click.argument("cluster_name")
@click.option(
    "--azureml-environment",
    "--aml-env",
    default=None,
    type=str,
    help="Azure ML environment to use with code flow",
)
@click.pass_obj
def init(
    ctx: CliContext,
    subscription_id,
    resource_group,
    workspace_name,
    cluster_name,
    azureml_environment: Optional[str],
):
    """
    Creates basic configuration for Kedro AzureML plugin
    """

    if not azureml_environment:
        raise click.UsageError(
            "You must specify --azure_ml_environment/--aml_env"
        )

    target_path = Path.cwd().joinpath("conf/base/azureml.yml")

    cfg = CONFIG_TEMPLATE_YAML.format(
        **{
            "subscription_id": subscription_id,
            "resource_group": resource_group,
            "workspace_name": workspace_name,
            "cluster_name": cluster_name,
            "environment_name": azureml_environment or "~",
            "code_directory": ".",
        }
    )
    target_path.write_text(cfg)

    click.echo(f"Configuration generated in {target_path}")

    aml_ignore = Path.cwd().joinpath(".amlignore")
    if aml_ignore.exists():
        click.echo(
            click.style(
                ".amlignore file already exist, make sure that all of the relevant files"
                "\nwill get uploaded to Azure ML if you're using Code Upload option with this plugin",
                fg="yellow",
            )
        )
    else:
        aml_ignore.write_text("")


@azureml_group.command()
@click.option(
    "--azureml-environment",
    "--aml-env",
    "aml_env",
    type=str,
    help="Azure ML Environment to use for pipeline execution.",
)
@click.option(
    "-j",
    "--job",
    "job_names",
    type=str,
    multiple=True,
    required=True,
    help="Name(s) of job(s) from the 'jobs' config section to compile.",
)
@click.option(
    "--params",
    "params",
    type=str,
    help="Parameters override in form of JSON string",
)
@click.option(
    "-o",
    "--output",
    type=click.types.Path(exists=False, dir_okay=False),
    default="pipeline.yaml",
    help="Pipeline YAML definition file. "
    "With multiple jobs, each file is suffixed with the job name.",
)
@click.option(
    "--env-var",
    type=str,
    multiple=True,
    help="Environment variables to be injected in the steps, format: KEY=VALUE",
)
@click.option(
    "--load-versions",
    "-lv",
    type=str,
    default="",
    help=LOAD_VERSION_HELP,
    callback=_split_load_versions,
)
@click.pass_obj
def compile(
    ctx: CliContext,
    aml_env: Optional[str],
    job_names: Tuple[str],
    params: str,
    output: str,
    env_var: Tuple[str],
    load_versions: Dict[str, str],
):
    """Compile job pipeline(s) into YAML format."""
    params = json.dumps(p) if (p := parse_runtime_params(params)) else ""
    extra_env = parse_extra_env_params(env_var)

    compile_job_pipelines(
        ctx=ctx,
        aml_env=aml_env,
        params=params,
        extra_env=extra_env,
        load_versions=load_versions,
        job_names=list(job_names),
        output=output,
    )


@azureml_group.command()
@click.option(
    "-w",
    "--workspace",
    "workspace_name",
    type=str,
    default=None,
    help="Named workspace from config to use for all jobs in this batch.",
)
@click.option(
    "--azureml-environment",
    "--aml-env",
    "aml_env",
    type=str,
    help="Azure ML Environment to use for pipeline execution.",
)
@click.option(
    "-j",
    "--job",
    "job_names",
    type=str,
    multiple=True,
    required=True,
    help="Name(s) of job(s) from the 'jobs' config section.",
)
@click.option(
    "--params",
    "params",
    type=str,
    help="Parameters override in form of JSON string",
)
@click.option(
    "--env-var",
    type=str,
    multiple=True,
    help="Environment variables to be injected in the steps, format: KEY=VALUE",
)
@click.option(
    "--load-versions",
    "-lv",
    type=str,
    default="",
    help=LOAD_VERSION_HELP,
    callback=_split_load_versions,
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview what would be submitted without actually calling Azure ML.",
)
@click.option(
    "--once",
    is_flag=True,
    default=False,
    help="Force immediate run even if the job has a schedule configured.",
)
@click.option(
    "--wait-for-completion",
    is_flag=True,
    default=False,
    help="Block until the pipeline run completes (useful in CI).",
)
@click.option(
    "--on-job-scheduled",
    type=str,
    default=None,
    callback=dynamic_import_job_schedule_func_from_str,
    help="Callback function invoked after each job is scheduled, "
    "format: path.to.module:function_name",
)
@click.pass_obj
@click.pass_context
def submit(
    click_context: click.Context,
    ctx: CliContext,
    workspace_name: Optional[str],
    aml_env: Optional[str],
    job_names: Tuple[str],
    params: str,
    env_var: Tuple[str],
    load_versions: Dict[str, str],
    dry_run: bool,
    once: bool,
    wait_for_completion: bool,
    on_job_scheduled: Optional[Callable],
):
    """Submit named jobs to Azure ML.

    Jobs are defined in the 'jobs' section of azureml.yml. Each job specifies
    its pipeline, optional schedule, display name, compute, and experiment.

    Jobs with a schedule create persistent Azure ML schedules; jobs without
    a schedule run immediately. Use --once to force an immediate run even
    when a schedule is configured.
    """
    params = json.dumps(p) if (p := parse_runtime_params(params)) else ""

    if workspace_name:
        click.echo(f"Overriding workspace to: {workspace_name}")

    if aml_env:
        click.echo(f"Overriding Azure ML Environment to: {aml_env}")

    warn_about_ignore_files()
    verify_configuration_directory_for_azure(click_context, ctx)

    extra_env = parse_extra_env_params(env_var)

    is_ok = submit_scheduled_jobs(
        ctx=ctx,
        aml_env=aml_env,
        params=params,
        extra_env=extra_env,
        load_versions=load_versions,
        job_names=list(job_names),
        dry_run=dry_run,
        once=once,
        wait_for_completion=wait_for_completion,
        on_job_scheduled=on_job_scheduled,
        workspace_override=workspace_name,
    )

    if is_ok:
        click.echo(click.style("All jobs submitted successfully", fg="green"))
        click_context.exit(0)
    else:
        click.echo(click.style("Some jobs failed to submit", fg="red"))
        click_context.exit(1)


@azureml_group.command(hidden=True)
@click.option(
    "-p",
    "--pipeline",
    "pipeline",
    type=str,
    help="Name of pipeline to run",
    default="__default__",
)
@click.option(
    "-n", "--node", "node", type=str, help="Name of the node to run", required=True
)
@click.option(
    "--params",
    "params",
    type=str,
    help="Parameters override in form of `key=value`",
)
@click.option(
    "--az-input",
    "azure_inputs",
    type=(str, click.Path(exists=True, file_okay=True, dir_okay=True)),
    multiple=True,
    help="Name and path of Azure ML Pipeline input",
)
@click.option(
    "--az-output",
    "azure_outputs",
    type=(str, click.Path(exists=True, file_okay=True, dir_okay=True)),
    multiple=True,
    help="Name and path of Azure ML Pipeline output",
)
@click.pass_obj
def execute(
    ctx: CliContext,
    pipeline: str,
    node: str,
    params: str,
    azure_inputs: List[Tuple[str, str]],
    azure_outputs: List[Tuple[str, str]],
):
    # 1. Run kedro
    parameters = parse_runtime_params(params)
    azure_inputs = {ds_name: data_path for ds_name, data_path in azure_inputs}
    azure_outputs = {ds_name: data_path for ds_name, data_path in azure_outputs}
    data_paths = {**azure_inputs, **azure_outputs}

    with KedroContextManager(env=ctx.env, runtime_params=parameters) as mgr:
        runner = AzurePipelinesRunner(data_paths=data_paths)
        mgr.session.run(pipeline, node_names=[node], runner=runner)
