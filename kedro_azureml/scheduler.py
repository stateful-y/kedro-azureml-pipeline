import logging
from typing import Dict, Optional, Union

from azure.ai.ml.entities import (
    CronTrigger,
    JobSchedule,
    RecurrencePattern,
    RecurrenceTrigger,
)
from azure.ai.ml.entities import Job

from kedro_azureml.client import _get_azureml_client
from kedro_azureml.config import (
    ScheduleConfig,
    JobConfig,
    WorkspaceConfig,
)

logger = logging.getLogger(__name__)


def resolve_schedule(
    schedule_ref: Union[ScheduleConfig, str],
    named_schedules: Optional[Dict[str, ScheduleConfig]],
) -> ScheduleConfig:
    """Resolve a schedule reference to a ``ScheduleConfig``.

    If *schedule_ref* is already a ``ScheduleConfig`` it is returned as-is.
    If it is a string, it is looked up in *named_schedules*.

    :param schedule_ref: An inline ``ScheduleConfig`` or a string key
        referencing a named schedule defined in the ``schedules`` section
        of ``azureml.yml``.
    :type schedule_ref: Union[ScheduleConfig, str]
    :param named_schedules: Mapping of schedule names to their configs,
        as parsed from the ``schedules`` section of ``azureml.yml``.
    :type named_schedules: Optional[Dict[str, ScheduleConfig]]
    :returns: The resolved schedule configuration.
    :rtype: ScheduleConfig
    :raises KeyError: If *schedule_ref* is a string that does not exist
        in *named_schedules*.
    """
    if isinstance(schedule_ref, ScheduleConfig):
        return schedule_ref
    if named_schedules is None or schedule_ref not in named_schedules:
        raise KeyError(
            f"Schedule '{schedule_ref}' not found in the 'schedules' section of azureml.yml"
        )
    return named_schedules[schedule_ref]


def build_trigger(config: ScheduleConfig) -> Union[CronTrigger, RecurrenceTrigger]:
    """Convert a ``ScheduleConfig`` into an Azure ML trigger object.

    Reads the ``cron`` or ``recurrence`` field of *config* and constructs
    the corresponding ``CronTrigger`` or ``RecurrenceTrigger``.

    :param config: Schedule configuration containing either a ``cron``
        or ``recurrence`` definition.
    :type config: ScheduleConfig
    :returns: The Azure ML trigger object ready to be used in a
        ``JobSchedule``.
    :rtype: Union[CronTrigger, RecurrenceTrigger]
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
    trigger: Union[CronTrigger, RecurrenceTrigger],
    pipeline_job: Job,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
) -> JobSchedule:
    """Wrap an Azure ML pipeline job into a ``JobSchedule``.

    :param name: Unique name for the schedule in the Azure ML workspace.
    :type name: str
    :param trigger: A ``CronTrigger`` or ``RecurrenceTrigger`` defining
        when the job should run.
    :type trigger: Union[CronTrigger, RecurrenceTrigger]
    :param pipeline_job: The Azure ML pipeline ``Job`` to execute on
        each trigger.
    :type pipeline_job: Job
    :param display_name: Optional human-readable display name.
    :type display_name: Optional[str]
    :param description: Optional description of the schedule.
    :type description: Optional[str]
    :returns: A ``JobSchedule`` ready to be submitted via
        ``ml_client.schedules.begin_create_or_update()``.
    :rtype: JobSchedule
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

    Wraps ``ml_client.schedules.begin_create_or_update()`` behind a
    thin interface that manages ``MLClient`` lifecycle via
    ``_get_azureml_client``.
    """

    def __init__(self):
        pass

    def create_or_update_schedule(
        self,
        schedule: JobSchedule,
        config: WorkspaceConfig,
    ) -> JobSchedule:
        """Create or update a schedule in the Azure ML workspace.

        :param schedule: The ``JobSchedule`` to create or update.
        :type schedule: JobSchedule
        :param config: Azure ML workspace configuration used to
            initialise the ``MLClient``.
        :type config: AzureMLConfig
        :returns: The created or updated ``JobSchedule`` as returned
            by the Azure ML service.
        :rtype: JobSchedule
        """
        with _get_azureml_client(config) as ml_client:
            result = ml_client.schedules.begin_create_or_update(
                schedule=schedule,
            ).result()
            logger.info(f"Schedule '{result.name}' created/updated successfully")
            return result
