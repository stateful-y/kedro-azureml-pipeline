"""Azure ML schedule creation and management."""

import logging

from azure.ai.ml.entities import (
    CronTrigger,
    Job,
    JobSchedule,
    RecurrencePattern,
    RecurrenceTrigger,
)

from kedro_azureml_pipeline.client import _get_azureml_client
from kedro_azureml_pipeline.config import (
    ScheduleConfig,
    WorkspaceConfig,
)

logger = logging.getLogger(__name__)


def resolve_schedule(
    schedule_ref: ScheduleConfig | str,
    named_schedules: dict[str, ScheduleConfig] | None,
) -> ScheduleConfig:
    """Resolve a schedule reference to a ``ScheduleConfig``.

    If *schedule_ref* is already a ``ScheduleConfig`` it is returned
    as-is. If it is a string, it is looked up in *named_schedules*.

    Parameters
    ----------
    schedule_ref : ScheduleConfig or str
        Inline config or a named schedule key.
    named_schedules : dict of str to ScheduleConfig or None
        Named schedules from the ``schedules`` section of ``azureml.yml``.

    Returns
    -------
    ScheduleConfig
        Resolved schedule configuration.

    Raises
    ------
    KeyError
        If *schedule_ref* is a string not found in *named_schedules*.

    See Also
    --------
    `kedro_azureml_pipeline.config.ScheduleConfig` : The resolved configuration type.
    `kedro_azureml_pipeline.scheduler.build_trigger` : Next step after resolving.
    """
    if isinstance(schedule_ref, ScheduleConfig):
        return schedule_ref
    if named_schedules is None or schedule_ref not in named_schedules:
        raise KeyError(f"Schedule '{schedule_ref}' not found in the 'schedules' section of azureml.yml")
    return named_schedules[schedule_ref]


def build_trigger(config: ScheduleConfig) -> CronTrigger | RecurrenceTrigger:
    """Convert a ``ScheduleConfig`` into an Azure ML trigger object.

    Parameters
    ----------
    config : ScheduleConfig
        Schedule configuration with either a ``cron`` or ``recurrence``
        definition.

    Returns
    -------
    CronTrigger or RecurrenceTrigger
        Azure ML trigger ready for a ``JobSchedule``.

    See Also
    --------
    `kedro_azureml_pipeline.scheduler.resolve_schedule` : Resolves config before building.
    `kedro_azureml_pipeline.scheduler.build_job_schedule` : Wraps the trigger into a schedule.
    """
    if config.cron:
        kwargs = {"expression": config.cron.expression, "time_zone": config.cron.time_zone}
        if config.cron.start_time:
            kwargs["start_time"] = config.cron.start_time
        if config.cron.end_time:
            kwargs["end_time"] = config.cron.end_time
        return CronTrigger(**kwargs)

    rec = config.recurrence
    kwargs = {
        "frequency": rec.frequency,
        "interval": rec.interval,
        "time_zone": rec.time_zone,
    }
    if rec.start_time:
        kwargs["start_time"] = rec.start_time
    if rec.end_time:
        kwargs["end_time"] = rec.end_time
    if rec.schedule:
        pattern_kwargs = {}
        if rec.schedule.hours is not None:
            pattern_kwargs["hours"] = rec.schedule.hours
        if rec.schedule.minutes is not None:
            pattern_kwargs["minutes"] = rec.schedule.minutes
        if rec.schedule.week_days is not None:
            pattern_kwargs["week_days"] = rec.schedule.week_days
        kwargs["schedule"] = RecurrencePattern(**pattern_kwargs)

    return RecurrenceTrigger(**kwargs)


def build_job_schedule(
    name: str,
    trigger: CronTrigger | RecurrenceTrigger,
    pipeline_job: Job,
    display_name: str | None = None,
    description: str | None = None,
) -> JobSchedule:
    """Wrap an Azure ML pipeline job into a ``JobSchedule``.

    Parameters
    ----------
    name : str
        Unique schedule name in the Azure ML workspace.
    trigger : CronTrigger or RecurrenceTrigger
        Trigger defining when the job should run.
    pipeline_job : Job
        Azure ML pipeline job to execute on each trigger.
    display_name : str or None
        Human-readable display name.
    description : str or None
        Schedule description.

    Returns
    -------
    JobSchedule
        Ready to submit via ``ml_client.schedules``.

    See Also
    --------
    `kedro_azureml_pipeline.scheduler.build_trigger` : Creates the trigger argument.
    `kedro_azureml_pipeline.scheduler.AzureMLScheduleClient` : Submits this schedule.
    """
    kwargs = {
        "name": name,
        "trigger": trigger,
        "create_job": pipeline_job,
    }
    if display_name:
        kwargs["display_name"] = display_name
    if description:
        kwargs["description"] = description
    return JobSchedule(**kwargs)


class AzureMLScheduleClient:
    """Client for creating and updating Azure ML schedules.

    See Also
    --------
    `kedro_azureml_pipeline.client.AzureMLPipelinesClient` : Immediate job submission.
    `kedro_azureml_pipeline.scheduler.build_job_schedule` : Builds schedules for this client.
    `kedro_azureml_pipeline.config.ScheduleConfig` : Schedule trigger configuration.
    """

    def create_or_update_schedule(
        self,
        schedule: JobSchedule,
        config: WorkspaceConfig,
    ) -> JobSchedule:
        """Create or update a schedule in the Azure ML workspace.

        Parameters
        ----------
        schedule : JobSchedule
            The schedule to create or update.
        config : WorkspaceConfig
            Workspace configuration for the ``MLClient``.

        Returns
        -------
        JobSchedule
            The schedule as returned by the Azure ML service.
        """
        with _get_azureml_client(config) as ml_client:
            result = ml_client.schedules.begin_create_or_update(
                schedule=schedule,
            ).result()
            logger.info(f"Schedule '{result.name}' created/updated successfully")
            return result
