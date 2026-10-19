"""Hook that posts a job's run events to a webhook or the Slack API, once per job.

Every Kedro node runs as its own Azure ML step, so Kedro's pipeline hooks fire
once per node. The generator therefore stamps each step with the job's
notification definition and marks one root step as the *announcer* and one
leaf step as the *poster*. The announcer posts ``start``. A step that raises
posts ``failure``. The poster, once its own node is done, waits until every
sibling leaf has reached a terminal state and then posts ``success``, or a
failure summary for a sibling that died without reporting.

The hook is inert unless ``KEDRO_AZUREML_NOTIFY`` is present, which only the
generator sets, so a local ``kedro run`` never posts.

With the Slack API transport the ``start`` message opens a thread: its
timestamp is written as a tag on the job's root MLflow run, and the outcome
messages of the same run reply in that thread while also being sent to the
channel. Messages posted through the API carry the app's own name and icon
and no "Added by" label, which a webhook attachment always shows.

A step that served its output with a missing or stale input marks its own MLflow run
with a ``kedro.warning`` tag. When ``warning`` or ``recovered`` is subscribed, the poster
reads the tag from every step of the job, compares the job with its previous completed
run, and posts a ``warning`` when an outage starts, a reminder when it lasts, and
``recovered`` when it ends. The outage's state is written on the job's root run, and its
follow-up messages reply in the thread of its first warning.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from kedro.framework.hooks import hook_impl

from kedro_azureml_pipeline.constants import (
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_NOTIFY,
    KEDRO_AZUREML_NOTIFY_OUTCOME,
    KEDRO_AZUREML_NOTIFY_SIBLINGS,
    KEDRO_AZUREML_NOTIFY_START,
)

logger = logging.getLogger(__name__)

POST_TIMEOUT_SECONDS = 10
POLL_INTERVAL_SECONDS = 15
ERROR_HEAD_CHARS = 250
TERMINAL_RUN_STATUSES = frozenset({"FINISHED", "FAILED", "KILLED"})
ROOT_RUN_TAG = "mlflow.rootRunId"
NODE_NAME_TAG = "kedro.node_name"
ERROR_TAG = "kedro.error"
THREAD_TAG = "kedro.notify_thread"
# The degraded marking a step writes: ``table:reason:last_data`` entries joined by ``;``.
WARNING_TAG = "kedro.warning"
# The outage state the poster writes on the job's root run. Plain names: Azure ML's
# MLflow store refuses a backticked key and a key containing a filter keyword.
JOB_NAME_TAG = "kedro.job_name"
STATE_TAG = "kedro.notify_state"
DEGRADED_SINCE_TAG = "kedro.notify_degraded_since"
LAST_POST_TAG = "kedro.notify_last_post_run_start"
WARNING_TABLES_TAG = "kedro.notify_warning_tables"
OUTAGE_THREAD_TAG = "kedro.notify_outage_thread"
CLEAN = "clean"
DEGRADED = "degraded"
PREVIOUS_RUNS_SCANNED = 50
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
_IDENTIFIER_VARS = (
    "AZUREML_RUN_ID",
    "AZUREML_ROOT_RUN_ID",
    "AZUREML_ARM_SUBSCRIPTION",
    "AZUREML_ARM_RESOURCEGROUP",
    "AZUREML_ARM_WORKSPACE_NAME",
)


@dataclass(frozen=True)
class NotificationEvent:
    """What a payload builder receives.

    Parameters
    ----------
    event : str
        ``"start"``, ``"success"``, ``"failure"``, ``"warning"``, ``"recovered"``, or
        ``"unknown"`` when the poster gave up waiting for its siblings.
    job_name : str
        Name of the job in ``azureml.yml``.
    display_name : str
        Display name of the job.
    pipeline_name : str
        Registered Kedro pipeline name.
    kedro_env : str
        Kedro environment the step runs with.
    node : str or None
        Node the step ran; for ``failure`` the node that raised, or the sibling
        that died without reporting.
    error : str or None
        First characters of the exception for ``failure``; the pending sibling
        names for ``unknown``.
    root_run_id : str or None
        Azure ML root run id of the job.
    studio_url : str or None
        Azure ML Studio URL of the job, when the workspace identifiers are present.
    elapsed_seconds : float or None
        Seconds since the step's pipeline started, for outcome events.
    environment : Mapping of str to str
        Raw Azure ML identifiers present in the step environment.
    warnings : tuple of str
        For ``warning``, the job's ``kedro.warning`` entries, ``table:reason:last_data``.
    degraded_since : str or None
        For ``warning`` and ``recovered``, when the outage's first degraded run started,
        as an ISO 8601 UTC instant.
    reminder : bool
        For ``warning``, whether it repeats an outage already reported.

    See Also
    --------
    [NotificationHook][kedro_azureml_pipeline.hooks.NotificationHook] : Builds and posts the event.
    [NotificationConfig][kedro_azureml_pipeline.config.NotificationConfig] : Names the payload builder.
    """

    event: str
    job_name: str
    display_name: str
    pipeline_name: str
    kedro_env: str
    node: str | None = None
    error: str | None = None
    root_run_id: str | None = None
    studio_url: str | None = None
    elapsed_seconds: float | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    degraded_since: str | None = None
    reminder: bool = False


@dataclass(frozen=True)
class OutageDecision:
    """What the poster does about a job's degraded state, and the state it writes.

    Parameters
    ----------
    post : str or None
        ``"warning"``, ``"recovered"``, or ``None`` to post nothing.
    reminder : bool
        The warning repeats an outage already reported.
    thread : str or None
        The outage's thread to reply in, or ``None`` to post a new top-level message.
    state : dict of str to str
        The tags to write on the current root run.

    See Also
    --------
    [decide_outage][kedro_azureml_pipeline.hooks.notify.decide_outage] : Makes the decision.
    """

    post: str | None
    reminder: bool = False
    thread: str | None = None
    state: dict[str, str] = field(default_factory=dict)


def warning_tables(entries: tuple[str, ...]) -> tuple[str, ...]:
    """Return the table names of ``kedro.warning`` entries, sorted and unique.

    Parameters
    ----------
    entries : tuple of str
        ``table:reason:last_data`` entries.

    Returns
    -------
    tuple of str
        The tables.
    """
    return tuple(sorted({entry.split(":", 1)[0] for entry in entries if entry.split(":", 1)[0]}))


def decide_outage(
    previous: Mapping[str, str] | None,
    entries: tuple[str, ...],
    run_start_ms: int,
    *,
    repeat_ms: int,
    tolerance_ms: int,
) -> OutageDecision:
    """Decide the message and the state for a completed run, from its previous completed run.

    =================  =======================  ===============================================
    previous           this run clean           this run degraded
    =================  =======================  ===============================================
    none or clean      nothing                  ``warning``, starting the outage
    degraded           ``recovered``            ``warning`` if a table is new to the outage;
                                                a reminder once ``repeat - tolerance`` has
                                                passed since the run that last posted; else
                                                nothing
    =================  =======================  ===============================================

    Times are run start times, so the reminder does not drift with how long a run waits
    before posting. Tables accumulate over the outage, so a table that flaps does not warn
    again on its own.

    Parameters
    ----------
    previous : Mapping of str to str or None
        The previous completed run's tags, or ``None`` when there is none.
    entries : tuple of str
        This run's ``kedro.warning`` entries; empty for a clean run.
    run_start_ms : int
        This run's start, in epoch milliseconds.
    repeat_ms : int
        The reminder interval, in milliseconds.
    tolerance_ms : int
        How much earlier than the interval a reminder may come, in milliseconds.

    Returns
    -------
    OutageDecision
        What to post, where, and the state to write.
    """
    was_degraded = previous is not None and previous.get(STATE_TAG) == DEGRADED
    tables = warning_tables(entries)
    if not tables:
        if was_degraded:
            return OutageDecision(
                "recovered",
                thread=previous.get(OUTAGE_THREAD_TAG) or None,
                state={STATE_TAG: CLEAN, DEGRADED_SINCE_TAG: previous.get(DEGRADED_SINCE_TAG, "")},
            )
        return OutageDecision(None, state={STATE_TAG: CLEAN})
    if not was_degraded:
        state = {
            STATE_TAG: DEGRADED,
            DEGRADED_SINCE_TAG: str(run_start_ms),
            LAST_POST_TAG: str(run_start_ms),
            WARNING_TABLES_TAG: ",".join(tables),
        }
        return OutageDecision("warning", state=state)
    known = set(filter(None, previous.get(WARNING_TABLES_TAG, "").split(",")))
    last_post = int(previous.get(LAST_POST_TAG) or 0)
    thread = previous.get(OUTAGE_THREAD_TAG) or None
    state = {
        STATE_TAG: DEGRADED,
        DEGRADED_SINCE_TAG: previous.get(DEGRADED_SINCE_TAG) or str(run_start_ms),
        LAST_POST_TAG: str(last_post),
        WARNING_TABLES_TAG: ",".join(sorted(known | set(tables))),
    }
    if thread:
        state[OUTAGE_THREAD_TAG] = thread
    if set(tables) - known:
        return OutageDecision("warning", thread=thread, state={**state, LAST_POST_TAG: str(run_start_ms)})
    if run_start_ms - last_post >= repeat_ms - tolerance_ms:
        return OutageDecision(
            "warning", reminder=True, thread=thread, state={**state, LAST_POST_TAG: str(run_start_ms)}
        )
    return OutageDecision(None, state=state)


def _iso_from_ms(value: str | None) -> str | None:
    """An epoch-millisecond tag value as an ISO 8601 UTC instant, or ``None``."""
    if not value:
        return None
    from datetime import UTC, datetime

    return datetime.fromtimestamp(int(value) / 1000, UTC).isoformat()


@dataclass(frozen=True)
class SiblingOutcome:
    """Result of waiting for the poster's sibling leaves.

    Parameters
    ----------
    finished : bool
        Every sibling reached ``FINISHED``.
    pending : tuple of str
        Siblings still not terminal when the wait cap expired.
    reported : tuple of str
        Siblings that failed after running their own error hook.
    unreported : tuple of str
        Siblings that failed or were cancelled without running their error hook.

    See Also
    --------
    [NotificationHook][kedro_azureml_pipeline.hooks.NotificationHook] : Turns this into the outcome message.
    """

    finished: bool
    pending: tuple[str, ...] = ()
    reported: tuple[str, ...] = ()
    unreported: tuple[str, ...] = ()


def studio_url(env: Mapping[str, str]) -> str | None:
    """Build the Azure ML Studio URL of the root run from the step environment.

    Parameters
    ----------
    env : Mapping of str to str
        The step's environment variables.

    Returns
    -------
    str or None
        The URL, or ``None`` when any identifier is missing.
    """
    root = env.get("AZUREML_ROOT_RUN_ID")
    subscription = env.get("AZUREML_ARM_SUBSCRIPTION")
    resource_group = env.get("AZUREML_ARM_RESOURCEGROUP")
    workspace = env.get("AZUREML_ARM_WORKSPACE_NAME")
    if not all((root, subscription, resource_group, workspace)):
        return None
    return (
        f"https://ml.azure.com/runs/{root}?wsid=/subscriptions/{subscription}"
        f"/resourcegroups/{resource_group}/workspaces/{workspace}"
    )


def default_payload(event: NotificationEvent) -> dict[str, Any]:
    """Render the plain ``{"text": ...}`` payload Slack incoming webhooks accept.

    Parameters
    ----------
    event : NotificationEvent
        The event to render.

    Returns
    -------
    dict of str to Any
        A mapping with a single ``text`` field.
    """
    where = f"{event.display_name} (pipeline {event.pipeline_name}, env {event.kedro_env})"
    if event.event == "start":
        text = f"[start] {where} started."
    elif event.event == "success":
        text = f"[success] {where} finished{_elapsed(event)}."
    elif event.event == "failure":
        text = f"[failure] {where} failed in node {event.node}{_elapsed(event)}: {event.error}"
    elif event.event == "warning":
        label = "[warning] reminder:" if event.reminder else "[warning]"
        text = f"{label} {where} ran degraded since {event.degraded_since}: {'; '.join(event.warnings)}"
    elif event.event == "recovered":
        text = f"[recovered] {where} is no longer degraded (since {event.degraded_since})."
    else:
        text = f"[unknown] {where}: outcome unknown{_elapsed(event)}. Still pending: {event.error}"
    link = event.studio_url or event.root_run_id
    if link:
        text += f" Run: {link}"
    return {"text": text}


def _elapsed(event: NotificationEvent) -> str:
    """Format the elapsed time of an outcome event as a suffix.

    Parameters
    ----------
    event : NotificationEvent
        The event whose ``elapsed_seconds`` to format.

    Returns
    -------
    str
        `` after Ns`` or an empty string.
    """
    if event.elapsed_seconds is None:
        return ""
    return f" after {int(event.elapsed_seconds)}s"


class NotificationHook:
    """Post a job's ``start``, ``success``, and ``failure`` events to a webhook.

    Lifecycle
    ---------
    1. ``before_pipeline_run``: records the start time; the announcer posts ``start``.
    2. ``on_pipeline_error``: the raising step posts ``failure``.
    3. ``after_pipeline_run``: the poster waits for its sibling leaves through
       MLflow, then posts ``success``, a failure summary for a sibling that died
       without reporting, or ``unknown`` when the wait cap expires.

    Posting never raises: any error is logged at WARNING and swallowed, and
    neither the webhook URL nor the bot token is ever logged.

    See Also
    --------
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Stamps the definition and roles.
    [NotificationConfig][kedro_azureml_pipeline.config.NotificationConfig] : The definition shape.
    [MlflowAzureMLHook][kedro_azureml_pipeline.hooks.MlflowAzureMLHook] : Writes the tags the sibling wait reads.
    """

    def __init__(self) -> None:
        self._started_at: float | None = None
        self._clock: Callable[[], float] = time.monotonic
        self._sleep: Callable[[float], None] = time.sleep

    @staticmethod
    def _definition() -> dict[str, Any] | None:
        """Read the stamped definition, or ``None`` when the hook is inert.

        Returns
        -------
        dict of str to Any or None
            The definition the generator stamped, or ``None``.
        """
        raw = os.environ.get(KEDRO_AZUREML_NOTIFY)
        if not raw:
            return None
        return json.loads(raw)

    @hook_impl
    def before_pipeline_run(self) -> None:
        """Record the start time and, on the announcer step, post ``start``."""
        definition = self._definition()
        if definition is None:
            return
        self._started_at = self._clock()
        if os.environ.get(KEDRO_AZUREML_NOTIFY_START) == "1" and "start" in definition["events"]:
            self._post(definition, self._event(definition, "start"))

    @hook_impl
    def on_pipeline_error(self, error: Exception) -> None:
        """Post ``failure`` from the step that raised.

        Parameters
        ----------
        error : Exception
            The exception that ended the step.
        """
        definition = self._definition()
        if definition is None or "failure" not in definition["events"]:
            return
        event = self._event(
            definition,
            "failure",
            node=os.environ.get(KEDRO_AZUREML_MLFLOW_NODE_NAME) or None,
            error=str(error)[:ERROR_HEAD_CHARS],
        )
        self._post(definition, event)

    @hook_impl
    def after_pipeline_run(self) -> None:
        """On the poster step, wait for the sibling leaves and post the outcome."""
        definition = self._definition()
        if definition is None or os.environ.get(KEDRO_AZUREML_NOTIFY_OUTCOME) != "1":
            return
        events = set(definition["events"])
        if not events & {"success", "failure", "warning", "recovered"}:
            return
        siblings = tuple(name for name in os.environ.get(KEDRO_AZUREML_NOTIFY_SIBLINGS, "").split(",") if name)
        outcome = self._await_siblings(siblings, int(definition["wait_timeout"]))
        if outcome.finished:
            degraded = self._report_outage(definition) if events & {"warning", "recovered"} else False
            if "success" in events and not (degraded and "warning" in events):
                self._post(definition, self._event(definition, "success"))
            return
        if outcome.pending:
            self._post(
                definition,
                self._event(definition, "unknown", error=", ".join(outcome.pending)),
            )
            return
        if outcome.unreported and "failure" in definition["events"]:
            self._post(
                definition,
                self._event(
                    definition,
                    "failure",
                    node=", ".join(outcome.unreported),
                    error="step ended without reporting (killed or cancelled)",
                ),
            )

    def _report_outage(self, definition: dict[str, Any]) -> bool:
        """Post ``warning`` or ``recovered`` for a finished job and write its outage state.

        Reads ``kedro.warning`` from every step run of the job, not only the leaves, finds
        the job's previous completed run by its ``kedro.job_name`` tag, applies
        [decide_outage][kedro_azureml_pipeline.hooks.notify.decide_outage], and writes
        the state on the current root run. A lookup that fails counts as no history, so it
        errs toward a warning. Never raises.

        Parameters
        ----------
        definition : dict of str to Any
            The stamped definition.

        Returns
        -------
        bool
            Whether the job ran degraded.
        """
        try:
            import mlflow
        except ImportError:
            logger.warning("kedro-azureml-pipeline: mlflow is not installed; not reporting degraded runs")
            return False
        client = mlflow.MlflowClient()
        root_run_id = os.environ.get("AZUREML_ROOT_RUN_ID", "")
        experiment = self._experiment(client)
        if experiment is None or not root_run_id:
            logger.warning("kedro-azureml-pipeline: no experiment or root run; not reporting degraded runs")
            return False
        try:
            steps = client.search_runs(
                [experiment.experiment_id], filter_string=f"tags.{ROOT_RUN_TAG} = '{root_run_id}'"
            )
            entries = tuple(
                sorted({
                    entry
                    for run in steps
                    for entry in (run.data.tags.get(WARNING_TAG) or "").split(";")
                    if entry.strip()
                })
            )
            run_start_ms = int(client.get_run(root_run_id).info.start_time)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kedro-azureml-pipeline: could not read the job's degraded marks: %s", type(exc).__name__)
            return False
        previous = self._previous_run_tags(client, experiment.experiment_id, definition["job_name"], root_run_id)
        decision = decide_outage(
            previous,
            entries,
            run_start_ms,
            repeat_ms=int(definition.get("warning_repeat_hours", 24)) * 3_600_000,
            tolerance_ms=int(definition.get("warning_repeat_tolerance_minutes", 15)) * 60_000,
        )
        state = {JOB_NAME_TAG: definition["job_name"], **decision.state}
        if decision.post is not None and decision.post in definition["events"]:
            event = self._event(
                definition,
                decision.post,
                warnings=entries,
                degraded_since=_iso_from_ms(decision.state.get(DEGRADED_SINCE_TAG)),
                reminder=decision.reminder,
            )
            posted_ts = self._post(definition, event, thread_ts=decision.thread, outage=True)
            if decision.post == "warning" and decision.thread is None and posted_ts:
                state[OUTAGE_THREAD_TAG] = posted_ts
        for key, value in state.items():
            try:
                client.set_tag(root_run_id, key, value)
            except Exception as exc:  # noqa: BLE001
                logger.warning("kedro-azureml-pipeline: could not record %s: %s", key, type(exc).__name__)
        return bool(entries)

    @staticmethod
    def _previous_run_tags(client: Any, experiment_id: str, job_name: str, root_run_id: str) -> dict[str, str] | None:
        """Return the tags of the job's newest other root run that recorded an outage state, or ``None``.

        Failed runs never record one, so they are skipped. A lookup that fails is logged and
        counts as no history.
        """
        try:
            runs = client.search_runs(
                [experiment_id],
                filter_string=f"tags.{JOB_NAME_TAG} = '{job_name}'",
                order_by=["attributes.start_time DESC"],
                max_results=PREVIOUS_RUNS_SCANNED,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("kedro-azureml-pipeline: could not read the job's previous run: %s", type(exc).__name__)
            return None
        for run in runs:
            if run.info.run_id != root_run_id and STATE_TAG in run.data.tags:
                return dict(run.data.tags)
        return None

    @staticmethod
    def _experiment(client: Any) -> Any:
        """Return the job's MLflow experiment, from the step environment, or ``None``."""
        name = os.environ.get("MLFLOW_EXPERIMENT_NAME") or os.environ.get(KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME)
        return client.get_experiment_by_name(name) if name else None

    def _await_siblings(self, siblings: tuple[str, ...], wait_timeout: int) -> SiblingOutcome:
        """Poll MLflow until every sibling leaf run is terminal or the cap expires.

        Sibling runs are the step runs under the same Azure ML root run tagged
        with the sibling node names by the MLflow hook. A sibling with no run
        yet has not started and counts as pending.

        Parameters
        ----------
        siblings : tuple of str
            Node names of the other leaf steps.
        wait_timeout : int
            Seconds to wait before giving up.

        Returns
        -------
        SiblingOutcome
            What became of the siblings.
        """
        if not siblings:
            return SiblingOutcome(finished=True)
        try:
            import mlflow
        except ImportError:
            logger.warning(
                "kedro-azureml-pipeline: mlflow is not installed; posting the outcome without checking siblings"
            )
            return SiblingOutcome(finished=True)
        client = mlflow.MlflowClient()
        experiment = self._experiment(client)
        root_run_id = os.environ.get("AZUREML_ROOT_RUN_ID", "")
        pending = set(siblings)
        reported: list[str] = []
        unreported: list[str] = []
        deadline = self._clock() + wait_timeout
        while True:
            if experiment is not None:
                runs = client.search_runs(
                    [experiment.experiment_id], filter_string=f"tags.{ROOT_RUN_TAG} = '{root_run_id}'"
                )
                for run in runs:
                    name = run.data.tags.get(NODE_NAME_TAG)
                    if name not in pending or run.info.status not in TERMINAL_RUN_STATUSES:
                        continue
                    pending.discard(name)
                    if run.info.status != "FINISHED":
                        (reported if ERROR_TAG in run.data.tags else unreported).append(name)
            if not pending:
                break
            if self._clock() >= deadline:
                logger.warning("kedro-azureml-pipeline: gave up waiting for sibling steps %s", sorted(pending))
                return SiblingOutcome(
                    finished=False,
                    pending=tuple(sorted(pending)),
                    reported=tuple(reported),
                    unreported=tuple(unreported),
                )
            self._sleep(POLL_INTERVAL_SECONDS)
        return SiblingOutcome(
            finished=not reported and not unreported, reported=tuple(reported), unreported=tuple(unreported)
        )

    def _event(self, definition: dict[str, Any], kind: str, **extra: Any) -> NotificationEvent:
        """Assemble a ``NotificationEvent`` from the definition and the step environment.

        Parameters
        ----------
        definition : dict of str to Any
            The stamped definition.
        kind : str
            The event name.
        **extra : Any
            ``node`` and ``error`` for failure and unknown events.

        Returns
        -------
        NotificationEvent
            The event to render and post.
        """
        identifiers = {name: os.environ[name] for name in _IDENTIFIER_VARS if name in os.environ}
        elapsed = None if kind == "start" or self._started_at is None else self._clock() - self._started_at
        return NotificationEvent(
            event=kind,
            job_name=definition["job_name"],
            display_name=definition["display_name"],
            pipeline_name=definition["pipeline_name"],
            kedro_env=os.environ.get("KEDRO_ENV", ""),
            root_run_id=identifiers.get("AZUREML_ROOT_RUN_ID"),
            studio_url=studio_url(identifiers),
            elapsed_seconds=elapsed,
            environment=identifiers,
            **extra,
        )

    def _post(
        self,
        definition: dict[str, Any],
        event: NotificationEvent,
        *,
        thread_ts: str | None = None,
        outage: bool = False,
    ) -> str | None:
        """Render *event* and send it through the configured transport, swallowing every error.

        The Slack API is used when the definition names ``token_env`` and the
        token is present in the step; otherwise the webhook when its URL is
        present; otherwise nothing is posted and a warning names the variable.

        Parameters
        ----------
        definition : dict of str to Any
            The stamped definition naming the transport variables and the builder.
        event : NotificationEvent
            The event to send.
        thread_ts : str or None, default: None
            With *outage*, the outage thread to reply in; ``None`` posts at top level.
        outage : bool, default: False
            Thread by the outage instead of by the run's ``start`` message.

        Returns
        -------
        str or None
            The Slack timestamp of the posted message, through the Slack API only.
        """
        token_env = definition.get("token_env")
        token = os.environ.get(token_env) if token_env else None
        if token:
            return self._post_api(definition, event, token, thread_ts=thread_ts, outage=outage)
        webhook_env = definition.get("webhook_env")
        url = os.environ.get(webhook_env) if webhook_env else None
        if not url:
            logger.warning(
                "kedro-azureml-pipeline: %s is unset; not posting the '%s' notification",
                webhook_env or token_env,
                event.event,
            )
            return None
        if not url.startswith(("https://", "http://")):
            logger.warning(
                "kedro-azureml-pipeline: %s is not an http(s) URL; not posting the '%s' notification",
                webhook_env,
                event.event,
            )
            return None
        payload = self._render(definition.get("payload"), event)
        if self._send(url, dict(payload), {}, event) is not None:
            logger.info("kedro-azureml-pipeline: posted the '%s' notification for job %s", event.event, event.job_name)
        return None

    def _post_api(
        self,
        definition: dict[str, Any],
        event: NotificationEvent,
        token: str,
        *,
        thread_ts: str | None = None,
        outage: bool = False,
    ) -> str | None:
        """Post *event* with ``chat.postMessage``, threading outcomes under the run's ``start``.

        An outage message threads under the outage's first warning instead, and the first
        warning itself posts at top level, since a Slack thread needs a top-level parent.

        Parameters
        ----------
        definition : dict of str to Any
            The stamped definition naming the channel and the builder.
        event : NotificationEvent
            The event to send.
        token : str
            The bot token; sent as a bearer header and never logged.
        thread_ts : str or None, default: None
            With *outage*, the outage thread to reply in.
        outage : bool, default: False
            Thread by the outage instead of by the run's ``start`` message.

        Returns
        -------
        str or None
            The posted message's timestamp, or ``None`` when it was not posted.
        """
        body = {"channel": definition["channel"], **self._render(definition.get("payload"), event)}
        reply_to = thread_ts if outage else (None if event.event == "start" else self._thread_ts(event.root_run_id))
        if reply_to:
            body["thread_ts"] = reply_to
            body["reply_broadcast"] = True
        response = self._send(SLACK_POST_MESSAGE_URL, body, {"Authorization": f"Bearer {token}"}, event)
        if response is None:
            return None
        if not response.get("ok"):
            logger.warning(
                "kedro-azureml-pipeline: Slack refused the '%s' notification: %s", event.event, response.get("error")
            )
            return None
        logger.info("kedro-azureml-pipeline: posted the '%s' notification for job %s", event.event, event.job_name)
        if event.event == "start" and response.get("ts"):
            self._record_thread(event.root_run_id, str(response["ts"]))
        return str(response["ts"]) if response.get("ts") else None

    @staticmethod
    def _send(
        url: str, body: dict[str, Any], headers: dict[str, str], event: NotificationEvent
    ) -> dict[str, Any] | None:
        """POST *body* as JSON and return the decoded JSON response, or ``None`` on any error.

        A response that is not a JSON object (a webhook answers ``ok`` in plain
        text) decodes to an empty mapping, which still counts as delivered.

        Parameters
        ----------
        url : str
            Where to post.
        body : dict of str to Any
            The request body.
        headers : dict of str to str
            Extra request headers, such as the bearer token.
        event : NotificationEvent
            The event, for the warning.

        Returns
        -------
        dict of str to Any or None
            The decoded response, or ``None`` when the request failed.
        """
        request = urllib.request.Request(  # noqa: S310
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=POST_TIMEOUT_SECONDS) as response:  # noqa: S310
                raw = response.read()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kedro-azureml-pipeline: posting the '%s' notification failed: %s", event.event, type(exc).__name__
            )
            return None
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _thread_ts(root_run_id: str | None) -> str | None:
        """Read the thread timestamp the announcer tagged the root run with.

        Parameters
        ----------
        root_run_id : str or None
            The job's root run id.

        Returns
        -------
        str or None
            The ``start`` message timestamp, or ``None`` when absent or unreadable.
        """
        if not root_run_id:
            return None
        try:
            import mlflow

            return mlflow.MlflowClient().get_run(root_run_id).data.tags.get(THREAD_TAG) or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("kedro-azureml-pipeline: could not read the notification thread: %s", type(exc).__name__)
            return None

    @staticmethod
    def _record_thread(root_run_id: str | None, thread_ts: str) -> None:
        """Tag the root run with the ``start`` message timestamp for the outcome steps.

        Parameters
        ----------
        root_run_id : str or None
            The job's root run id; nothing is recorded without one.
        thread_ts : str
            The timestamp Slack returned for the ``start`` message.
        """
        if not root_run_id:
            return
        try:
            import mlflow

            mlflow.MlflowClient().set_tag(root_run_id, THREAD_TAG, thread_ts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kedro-azureml-pipeline: could not record the notification thread: %s", type(exc).__name__)

    @staticmethod
    def _render(builder_ref: str | None, event: NotificationEvent) -> Mapping[str, Any]:
        """Run the payload builder, falling back to the default payload on any error.

        Parameters
        ----------
        builder_ref : str or None
            ``module.path:function_name`` reference, or ``None`` for the default.
        event : NotificationEvent
            The event to render.

        Returns
        -------
        Mapping of str to Any
            The request body.
        """
        if builder_ref is None:
            return default_payload(event)
        from kedro_azureml_pipeline.cli.functions import import_callable

        try:
            payload = import_callable(builder_ref)(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kedro-azureml-pipeline: payload builder %s failed (%s); posting the default payload", builder_ref, exc
            )
            return default_payload(event)
        if not isinstance(payload, Mapping):
            logger.warning(
                "kedro-azureml-pipeline: payload builder %s returned %s, not a mapping; posting the default payload",
                builder_ref,
                type(payload).__name__,
            )
            return default_payload(event)
        return payload


notify_hook = NotificationHook()
