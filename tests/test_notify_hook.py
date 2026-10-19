"""Tests for NotificationHook: once-per-job webhook posting from Azure ML steps."""

import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kedro_azureml_pipeline.constants import (
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_NOTIFY,
    KEDRO_AZUREML_NOTIFY_OUTCOME,
    KEDRO_AZUREML_NOTIFY_SIBLINGS,
    KEDRO_AZUREML_NOTIFY_START,
)
from kedro_azureml_pipeline.hooks.notify import (
    SLACK_POST_MESSAGE_URL,
    THREAD_TAG,
    NotificationEvent,
    NotificationHook,
    SiblingOutcome,
    default_payload,
    studio_url,
)

WEBHOOK_VAR = "HOOK_URL"
WEBHOOK_URL = "https://hooks.example.test/services/secret-token"
TOKEN_VAR = "BOT_TOKEN"
TOKEN = "xoxb-secret-bot-token"
CHANNEL = "C0123456789"
ENV_VARS = [
    KEDRO_AZUREML_NOTIFY,
    KEDRO_AZUREML_NOTIFY_START,
    KEDRO_AZUREML_NOTIFY_OUTCOME,
    KEDRO_AZUREML_NOTIFY_SIBLINGS,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    "MLFLOW_EXPERIMENT_NAME",
    "KEDRO_ENV",
    "AZUREML_RUN_ID",
    "AZUREML_ROOT_RUN_ID",
    "AZUREML_ARM_SUBSCRIPTION",
    "AZUREML_ARM_RESOURCEGROUP",
    "AZUREML_ARM_WORKSPACE_NAME",
    WEBHOOK_VAR,
    TOKEN_VAR,
]
IDENTIFIERS = {
    "AZUREML_RUN_ID": "step-1",
    "AZUREML_ROOT_RUN_ID": "root-1",
    "AZUREML_ARM_SUBSCRIPTION": "sub",
    "AZUREML_ARM_RESOURCEGROUP": "rg",
    "AZUREML_ARM_WORKSPACE_NAME": "ws",
}


@pytest.fixture(autouse=True)
def clean_env():
    """Remove every variable the hook reads before and after each test."""
    saved = {k: os.environ.pop(k, None) for k in ENV_VARS}
    yield
    for k in ENV_VARS:
        os.environ.pop(k, None)
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


def stamp(
    *,
    events=("start", "success", "failure"),
    payload=None,
    wait_timeout=60,
    start=False,
    poster=False,
    siblings="",
    api=False,
    webhook=True,
):
    """Put the generator's stamped definition and markers into the environment.

    ``api=True`` names the Slack API transport and puts the token in the
    environment; ``webhook=False`` leaves the webhook out of the definition.
    """
    os.environ[KEDRO_AZUREML_NOTIFY] = json.dumps({
        "webhook_env": WEBHOOK_VAR if webhook else None,
        "token_env": TOKEN_VAR if api else None,
        "channel": CHANNEL if api else None,
        "events": list(events),
        "payload": payload,
        "wait_timeout": wait_timeout,
        "job_name": "job-a",
        "display_name": "Job A",
        "pipeline_name": "training",
    })
    os.environ["KEDRO_ENV"] = "prod"
    os.environ[WEBHOOK_VAR] = WEBHOOK_URL
    if api:
        os.environ[TOKEN_VAR] = TOKEN
    os.environ.update(IDENTIFIERS)
    if start:
        os.environ[KEDRO_AZUREML_NOTIFY_START] = "1"
    if poster:
        os.environ[KEDRO_AZUREML_NOTIFY_OUTCOME] = "1"
        os.environ[KEDRO_AZUREML_NOTIFY_SIBLINGS] = siblings


@pytest.fixture
def hook():
    """A hook with a controllable clock and a no-op sleep."""
    h = NotificationHook()
    ticks = iter(range(0, 100_000, 10))
    h._clock = lambda: next(ticks)
    h._sleep = MagicMock()
    return h


class _Posts(list):
    """A list of posts with the attributes the ``urlopen`` fixture sets."""


@pytest.fixture
def urlopen():
    """Capture every post as ``(url, body, timeout)``; the response body is ``posts.reply``."""
    posts = _Posts()
    posts.reply = b"ok"
    posts.headers = []

    def fake(request, timeout):
        posts.append((request.full_url, json.loads(request.data.decode("utf-8")), timeout))
        posts.headers.append(dict(request.header_items()))
        response = MagicMock()
        response.__enter__.return_value.read.return_value = posts.reply
        return response

    with patch("kedro_azureml_pipeline.hooks.notify.urllib.request.urlopen", side_effect=fake):
        yield posts


@pytest.fixture
def slack(monkeypatch):
    """A fake ``mlflow`` module whose client stores tags per run, patched into the hook's imports."""
    tags: dict[str, dict[str, str]] = {}
    mock = MagicMock()
    client = mock.MlflowClient.return_value
    client.set_tag.side_effect = lambda run_id, key, value: tags.setdefault(run_id, {}).__setitem__(key, value)
    client.get_run.side_effect = lambda run_id: SimpleNamespace(data=SimpleNamespace(tags=dict(tags.get(run_id, {}))))
    monkeypatch.setitem(__import__("sys").modules, "mlflow", mock)
    mock.tags = tags
    return mock


def _run(name, status, tags=None):
    """A minimal MLflow run object as ``search_runs`` returns it."""
    return SimpleNamespace(
        data=SimpleNamespace(tags={"kedro.node_name": name, **(tags or {})}), info=SimpleNamespace(status=status)
    )


def fake_mlflow(search_results):
    """An ``mlflow`` module whose client returns *search_results* page by page, repeating the last."""
    mock = MagicMock()
    client = mock.MlflowClient.return_value
    client.get_experiment_by_name.return_value = SimpleNamespace(experiment_id="exp-1")
    calls = iter(search_results)
    last = search_results[-1]
    client.search_runs.side_effect = lambda *a, **k: next(calls, last)
    return mock


class TestInert:
    """Without a stamped definition the hook does nothing."""

    def test_no_definition_posts_nothing(self, hook, urlopen):
        os.environ[KEDRO_AZUREML_NOTIFY_START] = "1"
        os.environ[KEDRO_AZUREML_NOTIFY_OUTCOME] = "1"
        hook.before_pipeline_run()
        hook.on_pipeline_error(RuntimeError("boom"))
        hook.after_pipeline_run()
        assert urlopen == []


class TestStart:
    """``start`` is posted once, by the announcer only."""

    def test_announcer_posts_start(self, hook, urlopen):
        stamp(start=True)
        hook.before_pipeline_run()
        assert len(urlopen) == 1
        url, body, timeout = urlopen[0]
        assert url == WEBHOOK_URL
        assert timeout == 10
        assert body["text"].startswith("[start] Job A (pipeline training, env prod) started.")
        assert (
            "https://ml.azure.com/runs/root-1?wsid=/subscriptions/sub/resourcegroups/rg/workspaces/ws" in body["text"]
        )

    def test_non_announcer_posts_nothing(self, hook, urlopen):
        stamp(start=False)
        hook.before_pipeline_run()
        assert urlopen == []

    def test_start_disabled_posts_nothing(self, hook, urlopen):
        stamp(events=["failure"], start=True)
        hook.before_pipeline_run()
        assert urlopen == []


class TestFailure:
    """``failure`` is posted by the step that raised."""

    def test_failure_names_node_and_error_head(self, hook, urlopen):
        stamp()
        os.environ[KEDRO_AZUREML_MLFLOW_NODE_NAME] = "tune_model"
        hook.before_pipeline_run()
        hook.on_pipeline_error(RuntimeError("x" * 300))
        assert len(urlopen) == 1
        text = urlopen[0][1]["text"]
        assert text.startswith("[failure] Job A (pipeline training, env prod) failed in node tune_model after ")
        assert "x" * 250 in text
        assert "x" * 251 not in text

    def test_failure_disabled_posts_nothing(self, hook, urlopen):
        stamp(events=["start", "success"])
        hook.on_pipeline_error(RuntimeError("boom"))
        assert urlopen == []

    def test_failure_without_node_name(self, hook, urlopen):
        stamp(events=["failure"])
        hook.on_pipeline_error(RuntimeError("boom"))
        assert "failed in node None" in urlopen[0][1]["text"]


class TestOutcome:
    """The poster posts the outcome once, after its siblings."""

    def test_non_poster_posts_nothing(self, hook, urlopen):
        stamp(poster=False)
        hook.before_pipeline_run()
        hook.after_pipeline_run()
        assert urlopen == []

    def test_outcome_events_disabled_posts_nothing(self, hook, urlopen):
        stamp(events=["start"], poster=True)
        hook.after_pipeline_run()
        assert urlopen == []

    def test_no_siblings_posts_success_immediately(self, hook, urlopen):
        stamp(poster=True)
        hook.before_pipeline_run()
        with patch.dict("sys.modules", {"mlflow": MagicMock()}) as modules:
            hook.after_pipeline_run()
            modules["mlflow"].MlflowClient.assert_not_called()
        assert len(urlopen) == 1
        assert urlopen[0][1]["text"].startswith("[success] Job A (pipeline training, env prod) finished after 10s.")

    def test_success_disabled_but_failure_enabled_posts_nothing_on_success(self, hook, urlopen):
        stamp(events=["failure"], poster=True)
        hook.after_pipeline_run()
        assert urlopen == []

    def test_waits_for_two_siblings_then_posts_once(self, hook, urlopen):
        stamp(poster=True, siblings="leaf_a,leaf_b")
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "exp"
        mlflow = fake_mlflow([
            [],
            [_run("leaf_a", "RUNNING")],
            [_run("leaf_a", "FINISHED"), _run("leaf_b", "RUNNING")],
            [_run("leaf_a", "FINISHED"), _run("leaf_b", "FINISHED")],
        ])
        with patch.dict("sys.modules", {"mlflow": mlflow}):
            hook.after_pipeline_run()
        assert hook._sleep.call_count == 3
        client = mlflow.MlflowClient.return_value
        client.get_experiment_by_name.assert_called_once_with("exp")
        client.search_runs.assert_called_with(["exp-1"], filter_string="tags.mlflow.rootRunId = 'root-1'")
        assert len(urlopen) == 1
        assert urlopen[0][1]["text"].startswith("[success]")

    def test_experiment_name_falls_back_to_generator_variable(self, hook, urlopen):
        stamp(poster=True, siblings="leaf_a")
        os.environ[KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME] = "exp-from-generator"
        mlflow = fake_mlflow([[_run("leaf_a", "FINISHED")]])
        with patch.dict("sys.modules", {"mlflow": mlflow}):
            hook.after_pipeline_run()
        mlflow.MlflowClient.return_value.get_experiment_by_name.assert_called_once_with("exp-from-generator")
        assert len(urlopen) == 1

    def test_failed_sibling_with_error_tag_posts_nothing(self, hook, urlopen):
        stamp(poster=True, siblings="leaf_a")
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "exp"
        mlflow = fake_mlflow([[_run("leaf_a", "FAILED", {"kedro.error": "boom"})]])
        with patch.dict("sys.modules", {"mlflow": mlflow}):
            hook.after_pipeline_run()
        assert urlopen == []

    @pytest.mark.parametrize("status", ["FAILED", "KILLED"])
    def test_sibling_ended_without_error_tag_posts_failure_summary(self, hook, urlopen, status):
        stamp(poster=True, siblings="leaf_a,leaf_b")
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "exp"
        mlflow = fake_mlflow([[_run("leaf_a", status), _run("leaf_b", "FINISHED")]])
        with patch.dict("sys.modules", {"mlflow": mlflow}):
            hook.after_pipeline_run()
        assert len(urlopen) == 1
        text = urlopen[0][1]["text"]
        assert text.startswith("[failure] Job A (pipeline training, env prod) failed in node leaf_a")
        assert "step ended without reporting (killed or cancelled)" in text

    def test_unreported_sibling_with_failure_disabled_posts_nothing(self, hook, urlopen):
        stamp(events=["success"], poster=True, siblings="leaf_a")
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "exp"
        mlflow = fake_mlflow([[_run("leaf_a", "KILLED")]])
        with patch.dict("sys.modules", {"mlflow": mlflow}):
            hook.after_pipeline_run()
        assert urlopen == []

    def test_wait_cap_posts_outcome_unknown_naming_pending(self, hook, urlopen, caplog):
        stamp(poster=True, siblings="leaf_a,leaf_b", wait_timeout=25)
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "exp"
        mlflow = fake_mlflow([[_run("leaf_b", "FINISHED")]])
        with patch.dict("sys.modules", {"mlflow": mlflow}), caplog.at_level(logging.WARNING):
            hook.after_pipeline_run()
        assert len(urlopen) == 1
        text = urlopen[0][1]["text"]
        assert text.startswith("[unknown] Job A (pipeline training, env prod): outcome unknown")
        assert "Still pending: leaf_a" in text
        assert "gave up waiting for sibling steps ['leaf_a']" in caplog.text

    def test_missing_experiment_counts_as_pending(self, hook, urlopen):
        stamp(poster=True, siblings="leaf_a", wait_timeout=15)
        mlflow = fake_mlflow([[_run("leaf_a", "FINISHED")]])
        with patch.dict("sys.modules", {"mlflow": mlflow}):
            hook.after_pipeline_run()
        mlflow.MlflowClient.return_value.search_runs.assert_not_called()
        assert urlopen[0][1]["text"].startswith("[unknown]")

    def test_mlflow_not_installed_posts_success_with_warning(self, hook, urlopen, caplog):
        stamp(poster=True, siblings="leaf_a")
        with patch.dict("sys.modules", {"mlflow": None}), caplog.at_level(logging.WARNING):
            hook.after_pipeline_run()
        assert "mlflow is not installed" in caplog.text
        assert urlopen[0][1]["text"].startswith("[success]")


class TestPosting:
    """The post never raises and never logs the URL."""

    def test_http_error_is_logged_without_url(self, hook, caplog):
        stamp(start=True)
        with (
            patch("kedro_azureml_pipeline.hooks.notify.urllib.request.urlopen", side_effect=TimeoutError("slow")),
            caplog.at_level(logging.WARNING),
        ):
            hook.before_pipeline_run()
        assert "posting the 'start' notification failed: TimeoutError" in caplog.text
        assert "secret-token" not in caplog.text

    def test_unset_webhook_variable_logs_and_skips(self, hook, urlopen, caplog):
        stamp(start=True)
        del os.environ[WEBHOOK_VAR]
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert urlopen == []
        assert f"{WEBHOOK_VAR} is unset" in caplog.text

    def test_non_http_url_is_refused(self, hook, urlopen, caplog):
        stamp(start=True)
        os.environ[WEBHOOK_VAR] = "file:///etc/passwd"
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert urlopen == []
        assert "is not an http(s) URL" in caplog.text

    def test_success_is_logged_at_info(self, hook, urlopen, caplog):
        stamp(start=True)
        with caplog.at_level(logging.INFO):
            hook.before_pipeline_run()
        assert "posted the 'start' notification for job job-a" in caplog.text
        assert "secret-token" not in caplog.text


class TestSlackApi:
    """The Slack API transport: bearer posts, a thread per run, webhook fallback."""

    def test_start_posts_to_chat_post_message_with_bearer_token(self, hook, urlopen, slack):
        stamp(start=True, api=True)
        urlopen.reply = b'{"ok": true, "ts": "1700000000.000100"}'
        hook.before_pipeline_run()
        (url, body, timeout) = urlopen[0]
        headers = urlopen.headers[0]
        assert url == SLACK_POST_MESSAGE_URL
        assert body["channel"] == CHANNEL
        assert body["text"].startswith("[start] Job A")
        assert "thread_ts" not in body
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        assert timeout == 10

    def test_start_records_the_thread_on_the_root_run(self, hook, urlopen, slack):
        stamp(start=True, api=True)
        urlopen.reply = b'{"ok": true, "ts": "1700000000.000100"}'
        hook.before_pipeline_run()
        assert slack.tags == {"root-1": {THREAD_TAG: "1700000000.000100"}}

    def test_outcome_replies_in_the_thread_and_broadcasts(self, hook, urlopen, slack):
        stamp(poster=True, api=True)
        slack.tags["root-1"] = {THREAD_TAG: "1700000000.000100"}
        urlopen.reply = b'{"ok": true, "ts": "1700000000.000200"}'
        hook.before_pipeline_run()
        hook.after_pipeline_run()
        (_, body, _) = urlopen[-1]
        assert body["thread_ts"] == "1700000000.000100"
        assert body["reply_broadcast"] is True
        assert body["text"].startswith("[success] Job A")
        assert slack.tags["root-1"] == {THREAD_TAG: "1700000000.000100"}, "outcomes never rewrite the thread"

    def test_failure_replies_in_the_thread(self, hook, urlopen, slack):
        stamp(api=True)
        slack.tags["root-1"] = {THREAD_TAG: "1700000000.000100"}
        urlopen.reply = b'{"ok": true}'
        hook.before_pipeline_run()
        hook.on_pipeline_error(RuntimeError("boom"))
        assert urlopen[-1][1]["thread_ts"] == "1700000000.000100"

    def test_outcome_without_a_thread_posts_plainly(self, hook, urlopen, slack):
        stamp(poster=True, api=True)
        urlopen.reply = b'{"ok": true}'
        hook.before_pipeline_run()
        hook.after_pipeline_run()
        assert "thread_ts" not in urlopen[-1][1]

    def test_unreadable_thread_posts_plainly_with_warning(self, hook, urlopen, slack, caplog):
        stamp(poster=True, api=True)
        slack.MlflowClient.return_value.get_run.side_effect = ConnectionError("down")
        urlopen.reply = b'{"ok": true}'
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
            hook.after_pipeline_run()
        assert "thread_ts" not in urlopen[-1][1]
        assert "could not read the notification thread: ConnectionError" in caplog.text

    def test_thread_lookup_needs_a_root_run_id(self, hook, urlopen, slack):
        stamp(poster=True, api=True)
        del os.environ["AZUREML_ROOT_RUN_ID"]
        urlopen.reply = b'{"ok": true}'
        hook.before_pipeline_run()
        hook.after_pipeline_run()
        slack.MlflowClient.return_value.get_run.assert_not_called()

    def test_recording_the_thread_needs_a_root_run_id(self, hook, urlopen, slack):
        stamp(start=True, api=True)
        del os.environ["AZUREML_ROOT_RUN_ID"]
        urlopen.reply = b'{"ok": true, "ts": "1"}'
        hook.before_pipeline_run()
        assert slack.tags == {}

    def test_start_without_a_timestamp_records_nothing(self, hook, urlopen, slack):
        stamp(start=True, api=True)
        urlopen.reply = b'{"ok": true}'
        hook.before_pipeline_run()
        assert slack.tags == {}

    def test_unrecordable_thread_is_logged(self, hook, urlopen, slack, caplog):
        stamp(start=True, api=True)
        slack.MlflowClient.return_value.set_tag.side_effect = ConnectionError("down")
        urlopen.reply = b'{"ok": true, "ts": "1"}'
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert "could not record the notification thread: ConnectionError" in caplog.text

    def test_mlflow_not_installed_posts_without_a_thread(self, hook, urlopen, monkeypatch, caplog):
        stamp(start=True, api=True)
        monkeypatch.setitem(__import__("sys").modules, "mlflow", None)
        urlopen.reply = b'{"ok": true, "ts": "1"}'
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert len(urlopen) == 1
        assert "could not record the notification thread: ModuleNotFoundError" in caplog.text

    def test_refusal_is_logged_with_slack_error(self, hook, urlopen, slack, caplog):
        stamp(start=True, api=True)
        urlopen.reply = b'{"ok": false, "error": "not_in_channel"}'
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert "Slack refused the 'start' notification: not_in_channel" in caplog.text
        assert slack.tags == {}
        assert TOKEN not in caplog.text

    @pytest.mark.parametrize("reply", [b"not json", b"[1, 2]"])
    def test_non_object_reply_counts_as_refused(self, hook, urlopen, slack, caplog, reply):
        stamp(start=True, api=True)
        urlopen.reply = reply
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert "Slack refused the 'start' notification: None" in caplog.text

    def test_transport_error_is_logged_without_token(self, hook, slack, caplog):
        stamp(start=True, api=True)
        with (
            patch("kedro_azureml_pipeline.hooks.notify.urllib.request.urlopen", side_effect=TimeoutError("slow")),
            caplog.at_level(logging.WARNING),
        ):
            hook.before_pipeline_run()
        assert "posting the 'start' notification failed: TimeoutError" in caplog.text
        assert TOKEN not in caplog.text

    def test_missing_token_falls_back_to_the_webhook(self, hook, urlopen, slack):
        stamp(start=True, api=True)
        del os.environ[TOKEN_VAR]
        hook.before_pipeline_run()
        assert urlopen[0][0] == WEBHOOK_URL
        assert "channel" not in urlopen[0][1]

    def test_missing_token_and_no_webhook_names_the_token_variable(self, hook, urlopen, slack, caplog):
        stamp(start=True, api=True, webhook=False)
        del os.environ[TOKEN_VAR]
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert urlopen == []
        assert f"{TOKEN_VAR} is unset" in caplog.text

    def test_custom_builder_payload_is_sent_with_the_channel(self, hook, urlopen, slack):
        stamp(start=True, api=True, payload=f"{__name__}:build_blocks")
        urlopen.reply = b'{"ok": true}'
        hook.before_pipeline_run()
        body = urlopen[0][1]
        assert body["channel"] == CHANNEL
        assert body["blocks"][0]["text"]["text"] == "start Job A"


def build_blocks(event):
    """Payload builder returning Slack blocks."""
    return {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"{event.event} {event.display_name}"}}]}


def build_broken(event):
    """Payload builder that raises."""
    raise ValueError(f"cannot render {event.event}")


def build_not_mapping(event):
    """Payload builder returning the wrong type."""
    return [event.event]


class TestPayloadBuilder:
    """Custom payload builders and the default fallback."""

    def test_custom_builder_mapping_is_posted_unchanged(self, hook, urlopen):
        stamp(start=True, payload="tests.test_notify_hook:build_blocks")
        hook.before_pipeline_run()
        assert urlopen[0][1] == build_blocks(NotificationEvent("start", "job-a", "Job A", "training", "prod"))

    def test_builder_receives_full_event(self, hook, urlopen):
        seen = []
        stamp(events=["failure"], payload="tests.test_notify_hook:build_blocks")
        os.environ[KEDRO_AZUREML_MLFLOW_NODE_NAME] = "fit_model"
        hook.before_pipeline_run()
        with patch("tests.test_notify_hook.build_blocks", side_effect=lambda e: seen.append(e) or {"text": "x"}):
            hook.on_pipeline_error(RuntimeError("boom"))
        event = seen[0]
        assert event.event == "failure"
        assert event.node == "fit_model"
        assert event.error == "boom"
        assert event.root_run_id == "root-1"
        assert event.environment == IDENTIFIERS
        assert event.elapsed_seconds == 10

    def test_raising_builder_falls_back_to_default(self, hook, urlopen, caplog):
        stamp(start=True, payload="tests.test_notify_hook:build_broken")
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert "payload builder tests.test_notify_hook:build_broken failed (cannot render start)" in caplog.text
        assert urlopen[0][1]["text"].startswith("[start]")

    def test_non_mapping_builder_falls_back_to_default(self, hook, urlopen, caplog):
        stamp(start=True, payload="tests.test_notify_hook:build_not_mapping")
        with caplog.at_level(logging.WARNING):
            hook.before_pipeline_run()
        assert "returned list, not a mapping" in caplog.text
        assert urlopen[0][1]["text"].startswith("[start]")


class TestHelpers:
    """Studio URL and default payload rendering."""

    def test_studio_url_requires_every_identifier(self):
        assert studio_url(IDENTIFIERS) == (
            "https://ml.azure.com/runs/root-1?wsid=/subscriptions/sub/resourcegroups/rg/workspaces/ws"
        )
        partial = dict(IDENTIFIERS)
        del partial["AZUREML_ARM_WORKSPACE_NAME"]
        assert studio_url(partial) is None

    def test_default_payload_without_link_or_elapsed(self):
        event = NotificationEvent("success", "job-a", "Job A", "training", "prod")
        assert default_payload(event) == {"text": "[success] Job A (pipeline training, env prod) finished."}

    def test_default_payload_uses_root_run_id_when_no_studio_url(self):
        event = NotificationEvent("start", "job-a", "Job A", "training", "prod", root_run_id="root-9")
        assert default_payload(event)["text"].endswith("started. Run: root-9")

    def test_sibling_outcome_defaults(self):
        assert SiblingOutcome(finished=True) == SiblingOutcome(True, (), (), ())


from kedro_azureml_pipeline.hooks.notify import (  # noqa: E402
    DEGRADED_SINCE_TAG,
    JOB_NAME_TAG,
    LAST_POST_TAG,
    OUTAGE_THREAD_TAG,
    STATE_TAG,
    WARNING_TABLES_TAG,
    decide_outage,
    warning_tables,
)

HOUR_MS = 3_600_000
REPEAT = {"repeat_ms": 24 * HOUR_MS, "tolerance_ms": 15 * 60_000}
EMPTY = "actual_system_conditions:empty:2026-09-30T08:55:00+00:00"
STALE = "actual_gas_price:stale:2026-10-01T00:00:00+00:00"


def _degraded(since=0, last_post=0, tables="actual_system_conditions", thread="100.1"):
    return {
        STATE_TAG: "degraded",
        DEGRADED_SINCE_TAG: str(since),
        LAST_POST_TAG: str(last_post),
        WARNING_TABLES_TAG: tables,
        OUTAGE_THREAD_TAG: thread,
    }


class TestDecideOutage:
    """Every cell of the decision table, on run start times."""

    def test_a_clean_run_with_no_history_posts_nothing(self):
        decision = decide_outage(None, (), 0, **REPEAT)
        assert (decision.post, decision.state) == (None, {STATE_TAG: "clean"})

    def test_the_first_degraded_run_warns_and_starts_the_outage(self):
        decision = decide_outage({STATE_TAG: "clean"}, (EMPTY,), 9 * HOUR_MS, **REPEAT)
        assert (decision.post, decision.reminder, decision.thread) == ("warning", False, None)
        assert decision.state[DEGRADED_SINCE_TAG] == str(9 * HOUR_MS)
        assert decision.state[WARNING_TABLES_TAG] == "actual_system_conditions"

    def test_a_degraded_run_within_the_interval_posts_nothing(self):
        decision = decide_outage(_degraded(), (EMPTY,), 5 * HOUR_MS, **REPEAT)
        assert decision.post is None
        assert decision.state[LAST_POST_TAG] == "0"
        assert decision.state[OUTAGE_THREAD_TAG] == "100.1"

    def test_a_run_slightly_early_inside_the_tolerance_reminds(self):
        decision = decide_outage(_degraded(), (EMPTY,), 24 * HOUR_MS - 2 * 60_000, **REPEAT)
        assert (decision.post, decision.reminder, decision.thread) == ("warning", True, "100.1")
        assert decision.state[LAST_POST_TAG] == str(24 * HOUR_MS - 2 * 60_000)

    def test_a_table_new_to_the_outage_warns_at_once(self):
        decision = decide_outage(_degraded(), (EMPTY, STALE), 4 * HOUR_MS, **REPEAT)
        assert (decision.post, decision.reminder) == ("warning", False)
        assert decision.state[WARNING_TABLES_TAG] == "actual_gas_price,actual_system_conditions"

    def test_a_flapping_table_does_not_warn_again(self):
        previous = _degraded(tables="actual_gas_price,actual_system_conditions")
        assert decide_outage(previous, (EMPTY, STALE), 6 * HOUR_MS, **REPEAT).post is None

    def test_a_clean_run_after_an_outage_recovers_in_its_thread(self):
        decision = decide_outage(_degraded(since=7), (), 30 * HOUR_MS, **REPEAT)
        assert (decision.post, decision.thread) == ("recovered", "100.1")
        assert decision.state == {STATE_TAG: "clean", DEGRADED_SINCE_TAG: "7"}

    def test_an_outage_without_a_thread_keeps_none(self):
        decision = decide_outage(_degraded(thread=""), (EMPTY,), 25 * HOUR_MS, **REPEAT)
        assert (decision.post, decision.thread) == ("warning", None)
        assert OUTAGE_THREAD_TAG not in decision.state

    def test_a_missing_start_has_no_instant(self):
        from kedro_azureml_pipeline.hooks.notify import _iso_from_ms

        assert _iso_from_ms(None) is None
        assert _iso_from_ms("") is None

    def test_tables_are_read_from_entries(self):
        assert warning_tables((EMPTY, STALE, EMPTY, ":broken")) == ("actual_gas_price", "actual_system_conditions")


def _root(run_id, tags=None, start=0):
    return SimpleNamespace(
        data=SimpleNamespace(tags=dict(tags or {})), info=SimpleNamespace(run_id=run_id, start_time=start)
    )


def outage_mlflow(steps, previous=(), *, start=48 * HOUR_MS, fail=None):
    """An ``mlflow`` module serving the job's step runs, its previous runs, and the root's start."""
    mock = MagicMock()
    client = mock.MlflowClient.return_value
    client.get_experiment_by_name.return_value = SimpleNamespace(experiment_id="exp-1")
    tags: dict[str, dict[str, str]] = {}

    def search(_ids, filter_string="", **kwargs):
        if fail and fail in filter_string:
            raise RuntimeError("search refused")
        return list(previous) if JOB_NAME_TAG in filter_string else list(steps)

    def set_tag(run_id, key, value):
        if fail == "set_tag":
            raise RuntimeError("tag refused")
        tags.setdefault(run_id, {})[key] = value

    client.search_runs.side_effect = search
    client.get_run.side_effect = lambda run_id: _root(run_id, tags.get(run_id), start)
    client.set_tag.side_effect = set_tag
    mock.tags = tags
    return mock


def _step(name, warning=None):
    tags = {"kedro.node_name": name}
    if warning:
        tags["kedro.warning"] = warning
    return SimpleNamespace(data=SimpleNamespace(tags=tags), info=SimpleNamespace(status="FINISHED"))


OUTAGE_EVENTS = ("failure", "warning", "recovered")


class TestOutageReporting:
    """The poster reports degraded runs from every step and keeps the outage state."""

    def _run(self, hook, mlflow, **stamp_kwargs):
        stamp(events=stamp_kwargs.pop("events", OUTAGE_EVENTS), poster=True, **stamp_kwargs)
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "exp"
        with patch.dict("sys.modules", {"mlflow": mlflow}):
            hook.after_pipeline_run()

    def test_a_warning_on_a_non_leaf_step_starts_an_outage_thread(self, hook, urlopen):
        urlopen.reply = b'{"ok": true, "ts": "200.5"}'
        mlflow = outage_mlflow([_step("prepare", EMPTY), _step("prune")])
        self._run(hook, mlflow, api=True)

        (_, body, _) = urlopen[0]
        assert body["text"].startswith("[warning] Job A")
        assert "actual_system_conditions:empty" in body["text"]
        assert "thread_ts" not in body
        assert mlflow.tags["root-1"][OUTAGE_THREAD_TAG] == "200.5"
        assert mlflow.tags["root-1"][JOB_NAME_TAG] == "job-a"
        assert mlflow.tags["root-1"][STATE_TAG] == "degraded"

    def test_a_reminder_replies_in_the_outage_thread(self, hook, urlopen):
        urlopen.reply = b'{"ok": true, "ts": "300.1"}'
        previous = [_root("root-1"), _root("root-0", _degraded(since=0, thread="200.5"))]
        self._run(hook, outage_mlflow([_step("prepare", EMPTY)], previous, start=24 * HOUR_MS), api=True)

        (_, body, _) = urlopen[0]
        assert body["text"].startswith("[warning] reminder: Job A")
        assert (body["thread_ts"], body["reply_broadcast"]) == ("200.5", True)

    def test_recovery_replies_in_the_outage_thread(self, hook, urlopen):
        urlopen.reply = b'{"ok": true, "ts": "400.1"}'
        previous = [_root("root-0", _degraded(since=0, thread="200.5"))]
        mlflow = outage_mlflow([_step("prepare"), _step("prune")], previous)
        self._run(hook, mlflow, api=True)

        (_, body, _) = urlopen[0]
        assert body["text"].startswith(
            "[recovered] Job A (pipeline training, env prod) is no longer degraded (since 1970-01-01T00:00:00+00:00)"
        )
        assert body["thread_ts"] == "200.5"
        assert mlflow.tags["root-1"][STATE_TAG] == "clean"

    def test_a_quiet_degraded_run_posts_nothing_and_keeps_the_state(self, hook, urlopen):
        previous = [_root("root-0", _degraded(since=0))]
        mlflow = outage_mlflow([_step("prepare", EMPTY)], previous, start=2 * HOUR_MS)
        self._run(hook, mlflow)

        assert urlopen == []
        assert mlflow.tags["root-1"][LAST_POST_TAG] == "0"

    def test_the_webhook_posts_a_separate_message(self, hook, urlopen):
        previous = [_root("root-0", _degraded(since=0, thread="200.5"))]
        self._run(hook, outage_mlflow([_step("prepare", EMPTY)], previous, start=25 * HOUR_MS))

        (url, body, _) = urlopen[0]
        assert url == WEBHOOK_URL
        assert body["text"].startswith("[warning] reminder:")

    def test_a_degraded_run_posts_a_warning_instead_of_success(self, hook, urlopen):
        self._run(hook, outage_mlflow([_step("prepare", EMPTY)]), events=("success", "warning"))

        assert [body["text"].split()[0] for _, body, _ in urlopen] == ["[warning]"]

    def test_a_clean_run_still_posts_success(self, hook, urlopen):
        self._run(hook, outage_mlflow([_step("prepare")]), events=("success", "warning"))

        assert [body["text"].split()[0] for _, body, _ in urlopen] == ["[success]"]

    def test_an_unsubscribed_event_is_not_posted_but_the_state_is_kept(self, hook, urlopen):
        mlflow = outage_mlflow([_step("prepare", EMPTY)])
        self._run(hook, mlflow, events=("failure", "recovered"))

        assert urlopen == []
        assert mlflow.tags["root-1"][STATE_TAG] == "degraded"

    def test_a_previous_run_lookup_error_counts_as_no_history(self, hook, urlopen, caplog):
        self._run(hook, outage_mlflow([_step("prepare", EMPTY)], fail=JOB_NAME_TAG))

        assert urlopen[0][1]["text"].startswith("[warning] Job A")
        assert "could not read the job's previous run" in caplog.text

    def test_unreadable_degraded_marks_report_nothing(self, hook, urlopen, caplog):
        self._run(hook, outage_mlflow([], fail="mlflow.rootRunId"))

        assert urlopen == []
        assert "could not read the job's degraded marks" in caplog.text

    def test_an_unrecordable_state_is_logged(self, hook, urlopen, caplog):
        self._run(hook, outage_mlflow([_step("prepare", EMPTY)], fail="set_tag"))

        assert urlopen[0][1]["text"].startswith("[warning]")
        assert "could not record" in caplog.text

    def test_no_root_run_reports_nothing(self, hook, urlopen, caplog):
        stamp(events=OUTAGE_EVENTS, poster=True)
        os.environ.pop("AZUREML_ROOT_RUN_ID")
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "exp"
        with patch.dict("sys.modules", {"mlflow": outage_mlflow([_step("prepare", EMPTY)])}):
            hook.after_pipeline_run()

        assert urlopen == []
        assert "not reporting degraded runs" in caplog.text

    def test_mlflow_not_installed_reports_nothing(self, hook, urlopen, monkeypatch, caplog):
        stamp(events=OUTAGE_EVENTS, poster=True)
        monkeypatch.setitem(__import__("sys").modules, "mlflow", None)
        hook.after_pipeline_run()

        assert urlopen == []
        assert "not reporting degraded runs" in caplog.text
