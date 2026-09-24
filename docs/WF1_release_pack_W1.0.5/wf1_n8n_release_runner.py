#!/usr/bin/env python3
"""Release helper for WF-1 HeyReach Receiver.

This script deliberately separates safe read-only operations from mutations.
Mutating commands require --apply. The live suite also requires explicit
acknowledgement that it creates real Pipedrive/Slack side effects.

It uses only the n8n Public API and the production webhook URL. It never calls
private /rest endpoints.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import datetime as dt
import hashlib
import json
import os
import random
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urljoin

import requests

NIL_GUID = "00000000-0000-0000-0000-000000000000"
DEFAULT_PAYLOAD = Path(__file__).with_name("WF-1 HeyReach Receiver - W1.0.6 api-payload.json")
DEFAULT_STATIC_TEST = Path(__file__).with_name("wf1_static_contract_tests.js")
DEFAULT_PATCHED = Path(__file__).with_name("WF-1 HeyReach Receiver - W1.0.6 patched.json")


class ReleaseError(RuntimeError):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"Invalid JSON in {path}: {exc}") from exc


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_api_root(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        raise ReleaseError("N8N_BASE_URL is empty")
    if value.endswith("/api/v1"):
        return value
    return value + "/api/v1"


def instance_root(api_root: str) -> str:
    return re.sub(r"/api/v1/?$", "", api_root.rstrip("/"))


# The n8n Public API PUT/POST settings schema rejects UI-only keys (e.g. timeSavedMode,
# availableInMCP) that the editor GET returns. Send only API-accepted settings.
ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def canonical_workflow_payload(workflow: Mapping[str, Any]) -> dict[str, Any]:
    required = ("name", "nodes", "connections", "settings")
    missing = [key for key in required if key not in workflow]
    if missing:
        raise ReleaseError(f"Workflow payload is missing required keys: {missing}")
    payload = {key: copy.deepcopy(workflow[key]) for key in required}
    if isinstance(payload.get("settings"), dict):
        payload["settings"] = {k: v for k, v in payload["settings"].items() if k in ALLOWED_SETTINGS}
    return payload


def node_map(workflow: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["name"]: node for node in workflow.get("nodes", [])}


def find_project_id(workflow: Mapping[str, Any]) -> str | None:
    direct = workflow.get("projectId")
    if isinstance(direct, str) and direct:
        return direct
    shared = workflow.get("shared")
    if isinstance(shared, list):
        for item in shared:
            if not isinstance(item, Mapping):
                continue
            project = item.get("project")
            if isinstance(project, Mapping) and project.get("id"):
                return str(project["id"])
            if item.get("projectId"):
                return str(item["projectId"])
    return None


def workflow_summary(workflow: Mapping[str, Any]) -> dict[str, Any]:
    credentials: dict[str, set[str]] = {}
    for node in workflow.get("nodes", []):
        for kind, ref in (node.get("credentials") or {}).items():
            if isinstance(ref, Mapping):
                label = str(ref.get("name") or ref.get("id") or "unknown")
            else:
                label = str(ref)
            credentials.setdefault(kind, set()).add(label)
    return {
        "id": workflow.get("id"),
        "name": workflow.get("name"),
        "active": workflow.get("active"),
        "versionId": workflow.get("versionId"),
        "nodeCount": len(workflow.get("nodes", [])),
        "connectionSourceCount": len(workflow.get("connections", {})),
        "projectId": find_project_id(workflow),
        "hasPinData": bool(workflow.get("pinData")),
        "errorWorkflow": (workflow.get("settings") or {}).get("errorWorkflow"),
        "credentials": {key: sorted(values) for key, values in sorted(credentials.items())},
    }


@dataclasses.dataclass
class N8nClient:
    api_root: str
    api_key: str
    timeout: float = 45.0

    def __post_init__(self) -> None:
        self.api_root = normalize_api_root(self.api_root)
        if not self.api_key:
            raise ReleaseError("N8N_API_KEY is empty")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-N8N-API-KEY": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "wf1-release-runner/1.0",
            }
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        read_retries: int = 2,
    ) -> Any:
        url = self.api_root.rstrip("/") + "/" + path.lstrip("/")
        method = method.upper()
        attempts = 1 + (read_retries if method == "GET" else 0)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=body,
                    timeout=self.timeout,
                )
                if 200 <= response.status_code < 300:
                    if response.status_code == 204 or not response.content:
                        return None
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ReleaseError(f"{method} {url} returned non-JSON success response") from exc
                text = response.text[:2000]
                raise ReleaseError(f"{method} {url} failed: HTTP {response.status_code}: {text}")
            except (requests.RequestException, ReleaseError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                time.sleep(0.75 * (2**attempt))
        assert last_error is not None
        raise last_error

    def get_workflow(self, workflow_id: str, *, include_pins: bool = True) -> dict[str, Any]:
        return self.request(
            "GET",
            f"workflows/{workflow_id}",
            params={"excludePinnedData": str(not include_pins).lower()},
        )

    def update_workflow(self, workflow_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.request("PUT", f"workflows/{workflow_id}", body=payload)

    def create_workflow(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.request("POST", "workflows", body=payload)

    def publish_workflow(self, workflow_id: str, version_id: str | None = None) -> dict[str, Any]:
        body = {"versionId": version_id} if version_id else {}
        return self.request("POST", f"workflows/{workflow_id}/activate", body=body)

    def unpublish_workflow(self, workflow_id: str) -> dict[str, Any]:
        result = self.request("POST", f"workflows/{workflow_id}/deactivate", body={})
        return result or {}

    def delete_workflow(self, workflow_id: str) -> dict[str, Any]:
        result = self.request("DELETE", f"workflows/{workflow_id}")
        return result or {}

    def transfer_workflow(self, workflow_id: str, destination_project_id: str) -> dict[str, Any]:
        result = self.request("PUT", f"workflows/{workflow_id}/transfer",
                              body={"destinationProjectId": destination_project_id})
        return result or {}

    def list_executions(self, workflow_id: str, *, limit: int = 50, include_data: bool = False) -> list[dict[str, Any]]:
        response = self.request(
            "GET",
            "executions",
            params={
                "workflowId": workflow_id,
                "limit": limit,
                "includeData": str(include_data).lower(),
            },
        )
        data = response.get("data", []) if isinstance(response, Mapping) else []
        if not isinstance(data, list):
            raise ReleaseError("Unexpected executions list response")
        return data

    def get_execution(self, execution_id: str | int) -> dict[str, Any]:
        params = {
            "includeData": "true",
            "ignoreDataSizeLimit": "true",
            "redactExecutionData": "false",
        }
        try:
            return self.request("GET", f"executions/{execution_id}", params=params)
        except ReleaseError:
            # Older n8n versions may not accept all newer query parameters.
            return self.request("GET", f"executions/{execution_id}", params={"includeData": "true"})


def run_static_tests(patched: Path, test_script: Path) -> None:
    if not patched.exists() or not test_script.exists():
        raise ReleaseError(f"Static test inputs missing: {patched}, {test_script}")
    proc = subprocess.run(
        ["node", str(test_script), str(patched)],
        check=False,
        text=True,
        capture_output=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise ReleaseError("Static contract tests failed")


def is_subset(expected: Any, actual: Any) -> bool:
    """Return True when every expected value is present in actual recursively."""
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        return all(key in actual and is_subset(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and expected == actual
    return expected == actual


def compare_import(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    """Compare intended behavior while tolerating API-added defaults/metadata."""
    problems: list[str] = []
    if expected.get("name") != actual.get("name"):
        problems.append("workflow name differs")
    if expected.get("connections") != actual.get("connections"):
        problems.append("connections differ")
    if not is_subset(expected.get("settings", {}), actual.get("settings", {})):
        problems.append("intended settings are not preserved")

    expected_nodes = node_map(expected)
    actual_nodes = node_map(actual)
    if set(expected_nodes) != set(actual_nodes):
        missing = sorted(set(expected_nodes) - set(actual_nodes))
        extra = sorted(set(actual_nodes) - set(expected_nodes))
        problems.append(f"node-name set differs; missing={missing}, extra={extra}")
    for name in sorted(set(expected_nodes) & set(actual_nodes)):
        exp = expected_nodes[name]
        got = actual_nodes[name]
        # These are the fields that carry behavior and must survive import.
        for key in (
            "id",
            "name",
            "type",
            "typeVersion",
            "parameters",
            "retryOnFail",
            "maxTries",
            "waitBetweenTries",
            "credentials",
            "disabled",
            "webhookId",
        ):
            if key in exp and exp.get(key) != got.get(key):
                problems.append(f"node {name!r} field {key!r} differs")
    return problems


def make_test_double_payload(base: Mapping[str, Any], project_id: str, run_id: str) -> tuple[dict[str, Any], str]:
    payload = canonical_workflow_payload(base)
    payload["name"] = f"WF-1 TEST DOUBLE {run_id}"
    # projectId is NOT accepted in the POST body by this API; placement is done
    # afterwards via the transfer endpoint so credentials resolve in the source project.
    path = f"hr-test-{run_id.lower()}-{secrets.token_hex(4)}"
    webhooks = [node for node in payload["nodes"] if node.get("type") == "n8n-nodes-base.webhook"]
    if len(webhooks) != 1:
        raise ReleaseError(f"Expected exactly one Webhook node; found {len(webhooks)}")
    webhook = webhooks[0]
    webhook.setdefault("parameters", {})["path"] = path
    webhook["webhookId"] = path
    return payload, path


def build_fixtures(run_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Build T1-T7 fixtures from the observed HeyReach payload contract.

    These are synthetic and must still be compared with captured real deliveries.
    """
    clean = re.sub(r"[^A-Za-z0-9]", "", run_id)[:18] or "Run"
    rng = random.Random(int(hashlib.sha256(clean.encode()).hexdigest()[:16], 16))
    lead4_id = rng.randint(700_000_000, 899_999_999)
    lead5_id = rng.randint(900_000_000, 999_999_999)
    base_time = utc_now().replace(microsecond=123000)

    campaign = {"id": f"camp-{clean}", "name": f"HR Test {clean} Campaign"}
    sender = {"id": f"sender-{clean}", "full_name": "Person-87a2e116"}
    conv4 = f"conv-{clean}-4"

    lead4 = {
        "id": lead4_id,
        "profile_url": f"https://www.linkedin.com/in/pii-1f328626{clean.lower()}-person-4/",
        "full_name": f"HR Test {clean} Person 4",
        "company_name": f"HR Test {clean} Company 4",
        "position": "Synthetic Test Engineer",
        "summary": "Synthetic WF-1 release test person 4.",
        "location": "Testville",
        # example.com is IANA-reserved for documentation and is accepted by
        # more validators than the syntactically valid but less widely
        # accepted .invalid TLD.
        "email_address": f"hr-test-{clean.lower()}-4@example.com",
        "tags": [],
        "lists": [],
    }
    lead5 = {
        "id": lead5_id,
        "profile_url": f"https://www.linkedin.com/in/pii-1f328626{clean.lower()}-person-5/",
        "full_name": f"HR Test {clean} Person 5",
        "company_name": f"HR Test {clean} Company 5",
        "position": "Synthetic Test Analyst",
        "summary": "Synthetic WF-1 release test person 5 with empty email.",
        "location": "Testville",
        "email_address": "",
        "tags": [],
        "lists": [],
    }

    def envelope(event: str, lead: Mapping[str, Any], offset: int, **extra: Any) -> dict[str, Any]:
        body = {
            "event_type": event,
            "correlation_id": NIL_GUID,
            "timestamp": iso_z(base_time + dt.timedelta(seconds=offset)),
            "campaign": copy.deepcopy(campaign),
            "sender": copy.deepcopy(sender),
            "lead": copy.deepcopy(lead),
        }
        body.update(extra)
        return body

    t1 = envelope(
        "connection_request_sent",
        lead4,
        1,
        connection_message="HR Test invitation note",
        conversation_id=conv4,
        recent_messages=[],
        is_inmail=False,
    )
    t2 = copy.deepcopy(t1)
    t3 = envelope(
        "connection_request_sent",
        lead4,
        3,
        connection_message="HR Test repeat invitation event",
        conversation_id=conv4,
        recent_messages=[],
        is_inmail=False,
    )
    reply_text = f"HR Test actual reply text {clean}"
    t4 = envelope(
        "every_message_reply_received",
        lead4,
        4,
        conversation_id=conv4,
        recent_messages=[
            {"message": "Prior outbound message", "is_reply": False, "message_type": "REGULAR"},
            {"message": reply_text, "is_reply": True, "message_type": "REGULAR"},
        ],
        is_inmail=False,
    )
    t5 = envelope(
        "connection_request_accepted",
        lead4,
        5,
        conversation_id=conv4,
        recent_messages=[],
        is_inmail=False,
    )
    t6 = envelope(
        "connection_request_sent",
        lead5,
        6,
        connection_message="HR Test empty-email invitation",
        conversation_id=f"conv-{clean}-5",
        recent_messages=[],
        is_inmail=False,
    )
    unknown = copy.deepcopy(lead5)
    unknown.update(
        {
            "id": rng.randint(500_000_000, 699_999_999),
            "profile_url": f"https://www.linkedin.com/in/pii-1f328626{clean.lower()}-unknown/",
            "full_name": f"HR Test {clean} Unknown",
            "company_name": "",
            "email_address": "",
        }
    )
    t7 = envelope(
        "every_message_reply_received",
        unknown,
        7,
        conversation_id=f"conv-{clean}-unknown",
        recent_messages=[
            {"message": "Unknown-profile test reply", "is_reply": True, "message_type": "REGULAR"}
        ],
        is_inmail=False,
    )
    # T8 — reply to invite: fresh person at Invited, reply carrying ZERO is_reply:false.
    lead8 = {
        "id": rng.randint(300_000_000, 399_999_999),
        "profile_url": f"https://www.linkedin.com/in/pii-1f328626{clean.lower()}-person-8/",
        "full_name": f"HR Test {clean} Person 8",
        "company_name": f"HR Test {clean} Company 8",
        "position": "Synthetic Invite Replier",
        "summary": "Synthetic WF-1 reply-to-invite person 8.",
        "location": "Testville",
        "email_address": f"hr-test-{clean.lower()}-8@example.com",
        "tags": [],
        "lists": [],
    }
    conv8 = f"conv-{clean}-8"
    t8_setup = envelope(
        "connection_request_sent", lead8, 8,
        connection_message="HR Test invite for person 8",
        conversation_id=conv8, recent_messages=[], is_inmail=False,
    )
    t8 = envelope(
        "every_message_reply_received", lead8, 9,
        conversation_id=conv8,
        recent_messages=[{"message": f"HR Test reply-to-invite {clean}", "is_reply": True, "message_type": "REGULAR"}],
        is_inmail=False,
    )
    # T-F10 — no-lead failure isolation: person's lead is deleted mid-suite before the reply.
    leadF10 = {
        "id": rng.randint(400_000_000, 499_999_999),
        "profile_url": f"https://www.linkedin.com/in/pii-1f328626{clean.lower()}-person-f10/",
        "full_name": f"HR Test {clean} Person F10",
        "company_name": f"HR Test {clean} Company F10",
        "position": "Synthetic No-Lead Case",
        "summary": "Synthetic WF-1 failure-isolation person F10.",
        "location": "Testville",
        "email_address": f"hr-test-{clean.lower()}-f10@example.com",
        "tags": [],
        "lists": [],
    }
    convF10 = f"conv-{clean}-f10"
    tf10_setup = envelope(
        "connection_request_sent", leadF10, 10,
        connection_message="HR Test invite for person F10",
        conversation_id=convF10, recent_messages=[], is_inmail=False,
    )
    tf10 = envelope(
        "every_message_reply_received", leadF10, 11,
        conversation_id=convF10,
        recent_messages=[{"message": f"HR Test no-lead reply {clean}", "is_reply": True, "message_type": "REGULAR"}],
        is_inmail=False,
    )
    return [
        ("T1", t1), ("T2", t2), ("T3", t3), ("T4", t4), ("T5", t5), ("T6", t6), ("T7", t7),
        ("T8-setup", t8_setup), ("T8", t8),
        ("TF10-setup", tf10_setup), ("TF10", tf10),
    ]


def run_data(execution: Mapping[str, Any]) -> dict[str, Any]:
    data = execution.get("data")
    if not isinstance(data, Mapping):
        raise ReleaseError("Execution response has no detailed data; check includeData and retention settings")
    redaction = data.get("redactionInfo")
    if isinstance(redaction, Mapping) and redaction.get("isRedacted"):
        raise ReleaseError(f"Execution data is redacted: {redaction.get('reason') or 'unknown reason'}")
    result_data = data.get("resultData")
    if not isinstance(result_data, Mapping) or not isinstance(result_data.get("runData"), Mapping):
        raise ReleaseError("Execution data does not contain resultData.runData")
    return dict(result_data["runData"])


def node_outputs(execution: Mapping[str, Any], node_name: str) -> list[dict[str, Any]]:
    rd = run_data(execution)
    runs = rd.get(node_name, [])
    outputs: list[dict[str, Any]] = []
    if not isinstance(runs, list):
        return outputs
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        data = run.get("data")
        if not isinstance(data, Mapping):
            continue
        main = data.get("main")
        if not isinstance(main, list):
            continue
        for branch in main:
            if not isinstance(branch, list):
                continue
            for item in branch:
                if isinstance(item, Mapping) and isinstance(item.get("json"), Mapping):
                    outputs.append(dict(item["json"]))
    return outputs


def first_output(execution: Mapping[str, Any], node_name: str) -> dict[str, Any] | None:
    outputs = node_outputs(execution, node_name)
    return outputs[0] if outputs else None


SLACK_NODE_NAMES = ("M7 Critical Slack", "M5 Slack Warn", "M6 Slack Warn",
                    "M7 Slack Warn", "M7 No Lead Warn", "Lead Resp Invalid")


def posted_slack_text(execution: Mapping[str, Any], node_name: str) -> str | None:
    """The text Slack actually posted (chat.postMessage response message.text)."""
    out = first_output(execution, node_name)
    if not isinstance(out, Mapping):
        return None
    msg = out.get("message")
    if isinstance(msg, Mapping) and isinstance(msg.get("text"), str):
        return msg["text"]
    if isinstance(out.get("text"), str):
        return out["text"]
    return None


def assert_no_slack_braces(execution: Mapping[str, Any], failures: list[str]) -> None:
    """Suite-global content guard: no Slack node may post an unrendered '{{' expression."""
    for name in SLACK_NODE_NAMES:
        txt = posted_slack_text(execution, name)
        if txt is not None and "{{" in txt:
            failures.append(f"Slack node {name!r} posted an UNRENDERED expression: {txt[:48]!r}")


def _is_reply_alert(t: str) -> bool:
    # Slack echoes the emoji either as a unicode char or its :shortcode:.
    return t.startswith("\U0001f4ac") or t.startswith(":speech_balloon:")


def _is_warn(t: str) -> bool:
    return t.startswith("⚠") or t.startswith(":warning:")


def nested_id(value: Mapping[str, Any] | None) -> Any:
    if not isinstance(value, Mapping):
        return None
    data = value.get("data")
    if isinstance(data, Mapping) and data.get("id") is not None:
        return data.get("id")
    return value.get("id")


def get_new_execution(
    client: N8nClient,
    workflow_id: str,
    before_ids: set[str],
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    candidate_id: str | None = None
    while time.monotonic() < deadline:
        executions = client.list_executions(workflow_id, limit=50, include_data=False)
        new_items = [item for item in executions if str(item.get("id")) not in before_ids]
        if new_items:
            new_items.sort(key=lambda x: str(x.get("startedAt") or ""), reverse=True)
            candidate_id = str(new_items[0]["id"])
            detail = client.get_execution(candidate_id)
            if detail.get("status") not in {"new", "running", "waiting"} and detail.get("stoppedAt"):
                return detail
        time.sleep(0.75)
    if candidate_id:
        return client.get_execution(candidate_id)
    raise ReleaseError(f"No new execution appeared for workflow {workflow_id} within {timeout}s")


@dataclasses.dataclass
class TestResult:
    test_id: str
    status: str
    execution_id: str | None
    execution_status: str | None
    webhook_status: int | None
    assertions: list[str]
    failures: list[str]
    blockers: list[str]
    executed_nodes: list[str]
    fixture_sha256: str
    evidence: dict[str, Any]


def require_nodes(nodes: set[str], required: Iterable[str], failures: list[str]) -> None:
    for name in required:
        if name not in nodes:
            failures.append(f"required node did not execute: {name}")


def forbid_nodes(nodes: set[str], forbidden: Iterable[str], failures: list[str]) -> None:
    for name in forbidden:
        if name in nodes:
            failures.append(f"forbidden node executed: {name}")


def evaluate_test(
    test_id: str,
    execution: Mapping[str, Any],
    webhook_response: requests.Response,
    fixture: Mapping[str, Any],
    expected_labels: Mapping[str, str],
) -> TestResult:
    assertions: list[str] = []
    failures: list[str] = []
    blockers: list[str] = []
    evidence: dict[str, Any] = {}
    execution_id = str(execution.get("id")) if execution.get("id") is not None else None
    execution_status = str(execution.get("status")) if execution.get("status") is not None else None
    if execution_status != "success":
        failures.append(f"execution status is {execution_status!r}, expected 'success'")
    if webhook_response.status_code != 200:
        failures.append(f"webhook HTTP status is {webhook_response.status_code}, expected 200")
    try:
        rd = run_data(execution)
    except ReleaseError as exc:
        return TestResult(
            test_id,
            "BLOCKED",
            execution_id,
            execution_status,
            webhook_response.status_code,
            assertions,
            failures,
            [str(exc)],
            [],
            sha256_json(fixture),
            evidence,
        )
    nodes = set(rd)
    evidence["webhookBody"] = webhook_response.text[:1000]
    # Suite-global: any Slack node that posted a literal '{{' is a hard failure (F12.1).
    assert_no_slack_braces(execution, failures)

    all_write_nodes = {
        "Org Create",
        "Person Create",
        "Create Lead",
        "Create Activity",
        "M5 Person Patch Accepted",
        "M5 Lead Patch",
        "M6 Activity",
        "M6 Person Patch",
        "M7 Person Patch",
        "M7 Lead Patch",
        "M7 Reply Activity",
        "M8 Task",
    }

    if test_id == "T1":
        require_nodes(nodes, ["Dedupe", "Normalize", "IF Email Present", "Person Create", "Create Lead", "Create Activity"], failures)
        forbid_nodes(nodes, ["Lead Resp Invalid", "M5 Slack Warn", "M6 Slack Warn", "M7 Slack Warn"], failures)
        ids = {
            "organization": nested_id(first_output(execution, "Org Create")),
            "person": nested_id(first_output(execution, "Person Create")),
            "lead": nested_id(first_output(execution, "Create Lead")),
            "activity": nested_id(first_output(execution, "Create Activity")),
        }
        evidence["createdIds"] = ids
        for kind in ("person", "lead", "activity"):
            if not ids[kind]:
                blockers.append(f"could not prove created {kind} ID from node output")
        assertions.append("new-person create path and invite activity executed")

    elif test_id == "T2":
        require_nodes(nodes, ["Dedupe"], failures)
        forbid_nodes(nodes, ["Normalize", *sorted(all_write_nodes)], failures)
        assertions.append("identical replay stopped at Dedupe with no write nodes")

    elif test_id == "T3":
        require_nodes(nodes, ["Select Existing Lead", "Sent IF Lead ID", "Create Activity"], failures)
        forbid_nodes(nodes, ["Create Lead", "Lead Resp Invalid"], failures)
        evidence["selectedLead"] = first_output(execution, "Select Existing Lead")
        evidence["activityId"] = nested_id(first_output(execution, "Create Activity"))
        if not evidence["activityId"]:
            blockers.append("could not prove repeat-event activity ID from node output")
        assertions.append("existing lead path executed without duplicate lead or false warning")

    elif test_id == "T4":
        # W1.0.1: critical alert fires BEFORE CRM writes via M7 Reply Context -> M7 Critical Slack.
        # The old M8 Slack / M8 Slack Text tail is gone.
        require_nodes(
            nodes,
            ["M7 Reply Context", "M7 Critical Slack", "M7 Build", "M7 Labels Compute",
             "M7 Lead Patch", "M7 Reply Activity", "M8 Task"],
            failures,
        )
        forbid_nodes(nodes, ["M8 Slack", "M8 Slack Text"], failures)
        build = first_output(execution, "M7 Build") or {}
        ctx = first_output(execution, "M7 Reply Context") or {}
        expected_text = fixture.get("recent_messages", [])[-1].get("message")
        expected_conv = f"{fixture.get('sender', {}).get('id')}:{fixture.get('conversation_id')}"
        if build.get("reply_text") != expected_text:
            failures.append(f"M7 reply_text={build.get('reply_text')!r}, expected {expected_text!r}")
        if build.get("conversation_id") != expected_conv:
            failures.append(f"M7 conversation={build.get('conversation_id')!r}, expected {expected_conv!r}")
        if not build.get("lead_id"):
            failures.append("M7 Build emitted no lead_id")
        if build.get("isTransition") is not True:
            failures.append("first reply was not classified as transition")
        if expected_text and expected_text not in str(ctx.get("alert_text", "")):
            failures.append("critical alert text does not contain the actual reply text")
        labels = first_output(execution, "M7 Labels Compute") or {}
        if expected_labels.get("responded") and labels.get("targetLabel") != expected_labels["responded"]:
            failures.append("M7 target label is not CONFIG.labels.responded")
        crit = first_output(execution, "M7 Critical Slack")
        evidence.update(
            {
                "m7Build": build,
                "replyContext": ctx,
                "labels": labels,
                "replyActivityId": nested_id(first_output(execution, "M7 Reply Activity")),
                "taskId": nested_id(first_output(execution, "M8 Task")),
                "criticalSlack": crit,
            }
        )
        if not evidence["replyActivityId"]:
            blockers.append("could not prove completed reply activity ID")
        if not evidence["taskId"]:
            blockers.append("could not prove transition task ID")
        if not isinstance(crit, Mapping) or crit.get("ok") is not True:
            blockers.append("M7 Critical Slack output does not prove ok=true")
        crit_text = posted_slack_text(execution, "M7 Critical Slack")
        evidence["criticalSlackText"] = crit_text
        if crit_text is None:
            blockers.append("could not read posted critical Slack text (message.text)")
        else:
            if not _is_reply_alert(crit_text):
                failures.append(f"critical alert posted text is not the rendered reply alert: {crit_text[:48]!r}")
            if expected_text and expected_text not in crit_text:
                failures.append("critical alert POSTED text does not contain the actual reply text")
            if "{{" in crit_text:
                failures.append("critical alert POSTED an unrendered expression")
        assertions.append("critical alert fired first with rendered reply text; reply activity, task, responded label; M8 Slack absent")

    elif test_id == "T5":
        require_nodes(nodes, ["M5 Person Get", "M5 Labels Compute", "M5 IF Lead ID", "M5 Lead Patch"], failures)
        labels = first_output(execution, "M5 Labels Compute") or {}
        if int(labels.get("effectiveRank") or 0) < 4:
            failures.append(f"late accepted effectiveRank={labels.get('effectiveRank')!r}, expected >=4")
        if expected_labels.get("responded") and labels.get("targetLabel") != expected_labels["responded"]:
            failures.append("late accepted target label is not responded")
        patch = first_output(execution, "M5 Person Patch Accepted")
        evidence["labels"] = labels
        evidence["personPatchResult"] = patch
        if "M5 Person Patch Accepted" not in nodes:
            failures.append("late accepted did not execute Person Patch needed for connected_at")
        elif not isinstance(patch, Mapping):
            blockers.append("Person Patch output unavailable; connected_at side effect not proven")
        else:
            data = patch.get("data") if isinstance(patch.get("data"), Mapping) else {}
            custom = data.get("custom_fields") if isinstance(data, Mapping) else None
            if not isinstance(custom, Mapping):
                blockers.append("Person Patch response did not expose custom_fields; query Pipedrive directly for connected_at proof")
        assertions.append("late accepted effective rank and label remain at replied state")

    elif test_id == "T6":
        require_nodes(nodes, ["IF Email Present", "Person Search URL", "Person Create", "Create Lead", "Create Activity"], failures)
        forbid_nodes(nodes, ["Person Search Email"], failures)
        person = first_output(execution, "Person Create") or {}
        pdata = person.get("data") if isinstance(person.get("data"), Mapping) else {}
        emails = None
        if isinstance(pdata, Mapping):
            emails = pdata.get("emails", pdata.get("email"))
        ids = {
            "organization": nested_id(first_output(execution, "Org Create")),
            "person": nested_id(first_output(execution, "Person Create")),
            "lead": nested_id(first_output(execution, "Create Lead")),
            "activity": nested_id(first_output(execution, "Create Activity")),
        }
        evidence["personCreateResult"] = person
        evidence["createdIds"] = ids
        if emails not in (None, [], ""):
            failures.append(f"empty-email Person response unexpectedly contains email data: {emails!r}")
        for kind in ("person", "lead", "activity"):
            if not ids[kind]:
                blockers.append(f"could not prove T6 created {kind} ID from node output")
        assertions.append("empty email bypassed email search and Person create completed")

    elif test_id == "T7":
        # Unknown person: critical alert (with actual reply text) must STILL fire, warn fires,
        # and NO Pipedrive write occurs.
        require_nodes(nodes, ["M7 Reply Context", "M7 Critical Slack", "M7 IF Email Present",
                              "M7 Person Search URL", "M7 Slack Warn"], failures)
        forbid_nodes(nodes, ["M7 Person Patch", "M7 Lead Patch", "M7 Reply Activity", "M8 Task",
                             "Person Create", "Create Lead", "Create Activity", "Org Create"], failures)
        ctx = first_output(execution, "M7 Reply Context") or {}
        crit = first_output(execution, "M7 Critical Slack")
        expected_text = fixture.get("recent_messages", [])[-1].get("message")
        if not isinstance(crit, Mapping) or crit.get("ok") is not True:
            blockers.append("unknown-person critical Slack output does not prove ok=true")
        crit_text = posted_slack_text(execution, "M7 Critical Slack")
        warn_text = posted_slack_text(execution, "M7 Slack Warn")
        if crit_text is None:
            blockers.append("could not read posted critical Slack text (message.text)")
        else:
            if not _is_reply_alert(crit_text):
                failures.append(f"unknown-person critical alert POSTED text malformed: {crit_text[:48]!r}")
            if expected_text and expected_text not in crit_text:
                failures.append("unknown-person critical alert POSTED text lacks the actual reply text")
            if "{{" in crit_text:
                failures.append("unknown-person critical alert POSTED an unrendered expression")
        if warn_text is not None and not _is_warn(warn_text):
            failures.append(f"M7 Slack Warn POSTED text malformed: {warn_text[:48]!r}")
        evidence.update({
            "replyContext": ctx,
            "criticalSlack": crit,
            "criticalSlackText": crit_text,
            "slackWarnResult": first_output(execution, "M7 Slack Warn"),
            "slackWarnText": warn_text,
        })
        assertions.append("unknown reply: critical alert POSTED with actual reply text, M7 Slack Warn fired, zero Pipedrive writes")

    elif test_id in ("T8-setup", "TF10-setup"):
        # Setup events create a fresh person + lead via the connection_request_sent branch.
        require_nodes(nodes, ["Person Create", "Create Lead"], failures)
        ids = {
            "organization": nested_id(first_output(execution, "Org Create")),
            "person": nested_id(first_output(execution, "Person Create")),
            "lead": nested_id(first_output(execution, "Create Lead")),
            "activity": nested_id(first_output(execution, "Create Activity")),
        }
        evidence["createdIds"] = ids
        if not ids["person"]:
            blockers.append(f"{test_id} could not prove created person ID")
        if not ids["lead"]:
            blockers.append(f"{test_id} could not prove created lead ID")
        assertions.append(f"{test_id}: fresh person + lead created at Invited")

    elif test_id == "T8":
        require_nodes(nodes, ["M7 Reply Context", "M7 Critical Slack", "M7 Build",
                              "M7 Labels Compute", "M7 Lead Patch", "M7 Reply Activity", "M8 Task"], failures)
        build = first_output(execution, "M7 Build") or {}
        ctx = first_output(execution, "M7 Reply Context") or {}
        if build.get("targetStage") != "Replied to invite":
            failures.append(f"T8 targetStage={build.get('targetStage')!r}, expected 'Replied to invite'")
        if build.get("isTransition") is not True:
            failures.append("T8 reply was not classified as a transition")
        labels = first_output(execution, "M7 Labels Compute") or {}
        if expected_labels.get("responded") and labels.get("targetLabel") != expected_labels["responded"]:
            failures.append("T8 target label is not CONFIG.labels.responded")
        expected_text = fixture.get("recent_messages", [])[-1].get("message")
        if expected_text and expected_text not in str(ctx.get("alert_text", "")):
            failures.append("T8 critical alert text does not contain the actual reply text")
        crit_text = posted_slack_text(execution, "M7 Critical Slack")
        if crit_text is None:
            blockers.append("T8 could not read posted critical Slack text (message.text)")
        else:
            if not _is_reply_alert(crit_text):
                failures.append(f"T8 critical alert POSTED text malformed: {crit_text[:48]!r}")
            if expected_text and expected_text not in crit_text:
                failures.append("T8 critical alert POSTED text lacks the actual reply text")
            if "{{" in crit_text:
                failures.append("T8 critical alert POSTED an unrendered expression")
        evidence.update({
            "m7Build": build,
            "replyContext": ctx,
            "labels": labels,
            "taskId": nested_id(first_output(execution, "M8 Task")),
            "criticalSlack": first_output(execution, "M7 Critical Slack"),
            "criticalSlackText": crit_text,
        })
        if not evidence["taskId"]:
            blockers.append("T8 could not prove transition task ID")
        assertions.append("reply-to-invite -> 'Replied to invite', responded label, task created, correct POSTED alert text")

    elif test_id == "TF10":
        # Lead was deleted mid-suite: alert must still fire, No Lead Warn fires, zero CRM writes.
        require_nodes(nodes, ["M7 Reply Context", "M7 Critical Slack", "M7 No Lead Warn"], failures)
        forbid_nodes(nodes, ["M7 Lead Patch", "M7 Reply Activity", "M8 Task"], failures)
        ctx = first_output(execution, "M7 Reply Context") or {}
        crit = first_output(execution, "M7 Critical Slack")
        expected_text = fixture.get("recent_messages", [])[-1].get("message")
        if not isinstance(crit, Mapping) or crit.get("ok") is not True:
            blockers.append("TF10 critical Slack output does not prove ok=true")
        crit_text = posted_slack_text(execution, "M7 Critical Slack")
        nolead_text = posted_slack_text(execution, "M7 No Lead Warn")
        if crit_text is None:
            blockers.append("TF10 could not read posted critical Slack text (message.text)")
        else:
            if not _is_reply_alert(crit_text):
                failures.append(f"TF10 critical alert POSTED text malformed: {crit_text[:48]!r}")
            if expected_text and expected_text not in crit_text:
                failures.append("TF10 critical alert POSTED text lacks the actual reply text")
            if "{{" in crit_text:
                failures.append("TF10 critical alert POSTED an unrendered expression")
        if nolead_text is not None and not _is_warn(nolead_text):
            failures.append(f"M7 No Lead Warn POSTED text malformed: {nolead_text[:48]!r}")
        evidence.update({
            "replyContext": ctx,
            "criticalSlack": crit,
            "criticalSlackText": crit_text,
            "noLeadWarn": first_output(execution, "M7 No Lead Warn"),
            "noLeadWarnText": nolead_text,
        })
        assertions.append("no-lead reply: critical alert POSTED with reply text, M7 No Lead Warn fired, zero lead/activity/task writes")

    else:
        blockers.append(f"No evaluator implemented for {test_id}")

    status = "FAIL" if failures else ("BLOCKED" if blockers else "PASS")
    return TestResult(
        test_id=test_id,
        status=status,
        execution_id=execution_id,
        execution_status=execution_status,
        webhook_status=webhook_response.status_code,
        assertions=assertions,
        failures=failures,
        blockers=blockers,
        executed_nodes=sorted(nodes),
        fixture_sha256=sha256_json(fixture),
        evidence=evidence,
    )


def parse_config_values(payload: Mapping[str, Any]) -> dict[str, Any]:
    cfg_node = node_map(payload).get("CONFIG")
    if not cfg_node:
        return {}
    raw = (cfg_node.get("parameters") or {}).get("jsonOutput")
    if not isinstance(raw, str):
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def collect_cleanup_ids(results: Sequence[TestResult]) -> dict[str, list[Any]]:
    out: dict[str, set[Any]] = {
        "organizations": set(),
        "persons": set(),
        "leads": set(),
        "activities": set(),
    }
    for result in results:
        created = result.evidence.get("createdIds")
        if isinstance(created, Mapping):
            mapping = {
                "organization": "organizations",
                "person": "persons",
                "lead": "leads",
                "activity": "activities",
            }
            for key, bucket in mapping.items():
                if created.get(key):
                    out[bucket].add(created[key])
        for key in ("activityId", "replyActivityId", "taskId"):
            if result.evidence.get(key):
                out["activities"].add(result.evidence[key])
    return {key: sorted(values, key=str) for key, values in out.items()}


def render_markdown_report(run_id: str, state: Mapping[str, Any], results: Sequence[TestResult]) -> str:
    lines = [
        f"# WF-1 live test report — {run_id}",
        "",
        f"- Test double ID: `{state.get('workflowId')}`",
        f"- Webhook path: `{state.get('webhookPath')}`",
        f"- Generated at: `{iso_z(utc_now())}`",
        "",
        "| Test | Result | Execution | n8n status | Webhook |",
        "|---|---|---:|---|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result.test_id} | **{result.status}** | {result.execution_id or ''} | {result.execution_status or ''} | {result.webhook_status or ''} |"
        )
    for result in results:
        lines.extend(["", f"## {result.test_id} — {result.status}"])
        lines.append(f"Fixture SHA-256: `{result.fixture_sha256}`")
        if result.assertions:
            lines.append("\nAssertions:")
            lines.extend(f"- {item}" for item in result.assertions)
        if result.failures:
            lines.append("\nFailures:")
            lines.extend(f"- {item}" for item in result.failures)
        if result.blockers:
            lines.append("\nBlocked evidence:")
            lines.extend(f"- {item}" for item in result.blockers)
        lines.append("\nExecuted nodes:")
        lines.append("```text")
        lines.extend(result.executed_nodes)
        lines.append("```")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "`PASS` means both the execution path and the evidence available through n8n satisfied the implemented assertion. ",
            "`BLOCKED` means the path looked correct but a remote side effect could not be proven from retained execution data; verify it through Pipedrive/Slack directly. ",
            "`FAIL` means an asserted path or invariant was violated.",
            "",
        ]
    )
    return "\n".join(lines)


def cmd_preflight(args: argparse.Namespace) -> None:
    client = N8nClient(args.base_url, args.api_key)
    workflow = client.get_workflow(args.workflow_id, include_pins=True)
    out_dir = Path(args.out_dir)
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    backup = out_dir / f"wf1-preflight-{args.workflow_id}-{stamp}.json"
    dump_json(backup, workflow)
    summary = workflow_summary(workflow)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Backup: {backup}")
    if workflow.get("active") is True:
        raise ReleaseError("WF-1 is active/published. Abort before any update.")
    if workflow.get("pinData"):
        print("WARNING: current live workflow contains pinData", file=sys.stderr)
    if args.run_static:
        run_static_tests(Path(args.patched), Path(args.static_test))


def cmd_deploy(args: argparse.Namespace) -> None:
    client = N8nClient(args.base_url, args.api_key)
    intended = canonical_workflow_payload(load_json(Path(args.payload)))
    current = client.get_workflow(args.workflow_id, include_pins=True)
    if current.get("active") is True:
        raise ReleaseError("Refusing to PUT: target workflow is active/published")
    out_dir = Path(args.out_dir)
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    backup = out_dir / f"wf1-before-put-{args.workflow_id}-{stamp}.json"
    dump_json(backup, current)
    print(f"Backup written: {backup}")
    problems_before = compare_import(intended, current)
    print(f"Current-vs-intended differences detected: {len(problems_before)}")
    for problem in problems_before[:50]:
        print(f"  - {problem}")
    if not args.apply:
        print("DRY RUN: no PUT sent. Re-run with --apply after reviewing the backup and diff.")
        return
    client.update_workflow(args.workflow_id, intended)
    actual = client.get_workflow(args.workflow_id, include_pins=True)
    if actual.get("active") is True:
        raise ReleaseError("Safety violation: workflow became active after PUT")
    problems = compare_import(intended, actual)
    response_path = out_dir / f"wf1-after-put-{args.workflow_id}-{stamp}.json"
    dump_json(response_path, actual)
    if problems:
        for problem in problems:
            print(f"VERIFY FAIL: {problem}", file=sys.stderr)
        raise ReleaseError(f"Post-import verification found {len(problems)} differences")
    print(f"PUT and re-GET verification passed. Saved: {response_path}")


def cmd_create_double(args: argparse.Namespace) -> None:
    client = N8nClient(args.base_url, args.api_key)
    source = client.get_workflow(args.source_workflow_id, include_pins=False)
    if source.get("active") is True:
        raise ReleaseError("Source production workflow is active/published; abort")
    project_id = args.project_id or find_project_id(source)
    if not project_id:
        raise ReleaseError("Could not determine project ID; pass --project-id explicitly")
    base = canonical_workflow_payload(load_json(Path(args.payload)))
    run_id = args.run_id or utc_now().strftime("%Y%m%dT%H%M%S")
    payload, webhook_path = make_test_double_payload(base, project_id, run_id)
    out_dir = Path(args.out_dir)
    preview = out_dir / f"test-double-payload-{run_id}.json"
    dump_json(preview, payload)
    print(f"Prepared test double payload: {preview}")
    print(f"Webhook path: {webhook_path}")
    if not args.apply:
        print("DRY RUN: test double not created. Re-run with --apply.")
        return
    created = client.create_workflow(payload)
    workflow_id = str(created.get("id"))
    if not workflow_id:
        raise ReleaseError("Create workflow response has no id")
    if created.get("active") is True:
        raise ReleaseError("Unexpected: newly created test double is already active")
    # Place the double in the source project so its credentials resolve.
    created_project = find_project_id(created)
    if project_id and created_project != project_id:
        try:
            client.transfer_workflow(workflow_id, project_id)
            print(f"Transferred test double to project {project_id}")
        except ReleaseError as exc:
            print(f"WARNING: could not transfer double to project {project_id}: {exc}", file=sys.stderr)
    actual = client.get_workflow(workflow_id, include_pins=True)
    problems = compare_import(payload, actual)
    if problems:
        raise ReleaseError("Created test double does not match payload: " + "; ".join(problems[:20]))
    state = {
        "runId": run_id,
        "workflowId": workflow_id,
        "webhookPath": webhook_path,
        "projectId": project_id,
        "createdVersionId": actual.get("versionId"),
        "published": False,
        "createdAt": iso_z(utc_now()),
        "sourceWorkflowId": args.source_workflow_id,
    }
    if args.publish:
        published = client.publish_workflow(workflow_id, str(actual.get("versionId") or "") or None)
        verified = client.get_workflow(workflow_id, include_pins=False)
        if verified.get("active") is not True:
            raise ReleaseError("Publish endpoint returned, but test double is not active")
        state["published"] = True
        state["publishedVersionId"] = verified.get("versionId")
        state["publishResponseActive"] = published.get("active")
    state_path = out_dir / f"test-double-state-{run_id}.json"
    dump_json(state_path, state)
    print(json.dumps(state, indent=2))
    print(f"State file: {state_path}")


def cmd_emit_fixtures(args: argparse.Namespace) -> None:
    run_id = args.run_id or utc_now().strftime("%Y%m%dT%H%M%S")
    fixtures = build_fixtures(run_id)
    out_dir = Path(args.out_dir) / f"fixtures-{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for test_id, fixture in fixtures:
        path = out_dir / f"{test_id}.json"
        dump_json(path, fixture)
        manifest.append({"test": test_id, "file": path.name, "sha256": sha256_json(fixture)})
    dump_json(out_dir / "manifest.json", manifest)
    print(f"Wrote {len(fixtures)} fixtures to {out_dir}")


def cmd_run_suite(args: argparse.Namespace) -> None:
    if not args.melisa_warned or not args.confirm_synthetic_side_effects:
        raise ReleaseError(
            "Live suite creates real Pipedrive entities and Slack/Zapier side effects. "
            "Pass --melisa-warned and --confirm-synthetic-side-effects."
        )
    client = N8nClient(args.base_url, args.api_key)
    state = load_json(Path(args.state))
    workflow_id = str(state.get("workflowId") or "")
    webhook_path = str(state.get("webhookPath") or "")
    if not workflow_id or not webhook_path:
        raise ReleaseError("State file lacks workflowId/webhookPath")
    workflow = client.get_workflow(workflow_id, include_pins=False)
    if workflow.get("active") is not True:
        raise ReleaseError("Test double is not published/active")
    payload = canonical_workflow_payload(load_json(Path(args.payload)))
    cfg = parse_config_values(payload)
    expected_labels = cfg.get("labels") if isinstance(cfg.get("labels"), Mapping) else {}
    run_id = str(state.get("runId") or utc_now().strftime("%Y%m%dT%H%M%S"))
    fixtures = build_fixtures(run_id)
    if getattr(args, "tests", None):
        want = {t.strip() for t in args.tests.split(",") if t.strip()}
        fixtures = [(tid, fx) for tid, fx in fixtures if tid in want]
        if not fixtures:
            raise ReleaseError(f"--tests matched no fixtures: {sorted(want)}")
    out_dir = Path(args.out_dir) / f"live-{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir = out_dir / "fixtures"
    fixture_dir.mkdir(exist_ok=True)
    webhook_url = instance_root(client.api_root).rstrip("/") + "/webhook/" + webhook_path

    results: list[TestResult] = []
    tf10_deleted: dict[str, Any] = {}
    for test_id, fixture in fixtures:
        dump_json(fixture_dir / f"{test_id}.json", fixture)
        before = {str(item.get("id")) for item in client.list_executions(workflow_id, limit=50)}
        started = iso_z(utc_now())
        try:
            response = requests.post(
                webhook_url,
                json=fixture,
                headers={"Content-Type": "application/json", "User-Agent": "wf1-release-runner/1.0"},
                timeout=args.webhook_timeout,
            )
            execution = get_new_execution(client, workflow_id, before, timeout=args.execution_timeout)
            # Preserve the complete execution object before reducing it to the
            # assertion-oriented report. This is essential for node-level
            # audit evidence and later forensic review.
            dump_json(out_dir / f"{test_id}-execution.json", execution)
            result = evaluate_test(test_id, execution, response, fixture, expected_labels)
            result.evidence["requestStartedAt"] = started
            result.evidence["webhookUrl"] = webhook_url
        except Exception as exc:  # Keep the rest of the suite and preserve evidence.
            result = TestResult(
                test_id=test_id,
                status="FAIL",
                execution_id=None,
                execution_status=None,
                webhook_status=None,
                assertions=[],
                failures=[f"runner exception: {type(exc).__name__}: {exc}"],
                blockers=[],
                executed_nodes=[],
                fixture_sha256=sha256_json(fixture),
                evidence={"requestStartedAt": started, "webhookUrl": webhook_url},
            )
        results.append(result)
        dump_json(out_dir / f"{test_id}-result.json", dataclasses.asdict(result))
        print(f"{test_id}: {result.status} execution={result.execution_id}")

        # T-F10 craft step: delete the just-created lead so the following reply hits the no-lead path.
        if test_id == "TF10-setup":
            created = result.evidence.get("createdIds") or {}
            lead_to_delete = created.get("lead")
            if lead_to_delete and args.pipedrive_token:
                ok, detail = pipedrive_delete(args.pipedrive_base_url, args.pipedrive_token, "v1/leads/{id}", lead_to_delete)
                print(f"TF10 craft: DELETE lead {lead_to_delete}: {detail}")
                tf10_deleted["lead"] = {"id": lead_to_delete, "ok": ok, "detail": detail}
                if not ok:
                    print(f"WARNING: could not delete lead {lead_to_delete}; T-F10 may not exercise the no-lead path", file=sys.stderr)
            else:
                print("WARNING: TF10-setup produced no lead id or no Pipedrive token supplied; T-F10 skipped craft", file=sys.stderr)
                tf10_deleted["lead"] = {"id": lead_to_delete, "ok": False, "detail": "no token or no lead id"}

        # Avoid racing eventual-consistency reads in Pipedrive between dependent tests.
        time.sleep(args.between_tests)

    report = {
        "runId": run_id,
        "testDouble": state,
        "generatedAt": iso_z(utc_now()),
        "results": [dataclasses.asdict(item) for item in results],
        "cleanup": collect_cleanup_ids(results),
        "tf10CraftDeletion": tf10_deleted,
        "summary": {
            status: sum(1 for item in results if item.status == status)
            for status in ("PASS", "FAIL", "BLOCKED")
        },
    }
    dump_json(out_dir / "live-test-report.json", report)
    (out_dir / "live-test-report.md").write_text(
        render_markdown_report(run_id, state, results), encoding="utf-8"
    )
    dump_json(out_dir / "cleanup-manifest.json", report["cleanup"])
    print(json.dumps(report["summary"], indent=2))
    print(f"Report directory: {out_dir}")
    if any(item.status == "FAIL" for item in results):
        raise ReleaseError("One or more live tests failed")


def pipedrive_delete(base: str, token: str, path: str, entity_id: Any) -> tuple[bool, str]:
    url = base.rstrip("/") + "/" + path.strip("/").format(id=entity_id)
    try:
        response = requests.delete(url, params={"api_token": token}, timeout=30)
    except requests.RequestException as exc:
        return False, str(exc)
    if 200 <= response.status_code < 300 or response.status_code == 404:
        return True, f"HTTP {response.status_code}"
    return False, f"HTTP {response.status_code}: {response.text[:500]}"


def cmd_cleanup_pipedrive(args: argparse.Namespace) -> None:
    manifest = load_json(Path(args.manifest))
    token = args.pipedrive_token
    base = args.pipedrive_base_url.rstrip("/")
    if not token:
        raise ReleaseError("PIPEDRIVE_API_TOKEN/--pipedrive-token is required")
    print(json.dumps(manifest, indent=2))
    if not args.apply:
        print("DRY RUN: no Pipedrive DELETE calls sent. Re-run with --apply.")
        return
    order = [
        ("activities", "api/v2/activities/{id}"),
        ("leads", "v1/leads/{id}"),
        ("persons", "api/v2/persons/{id}"),
        ("organizations", "api/v2/organizations/{id}"),
    ]
    failures: list[str] = []
    for bucket, path in order:
        for entity_id in manifest.get(bucket, []):
            ok, detail = pipedrive_delete(base, token, path, entity_id)
            print(f"DELETE {bucket}/{entity_id}: {detail}")
            if not ok:
                failures.append(f"{bucket}/{entity_id}: {detail}")
    if failures:
        raise ReleaseError("Cleanup failures: " + "; ".join(failures))


def cmd_teardown(args: argparse.Namespace) -> None:
    client = N8nClient(args.base_url, args.api_key)
    state = load_json(Path(args.state))
    workflow_id = str(state.get("workflowId") or "")
    if not workflow_id:
        raise ReleaseError("State file lacks workflowId")
    workflow = client.get_workflow(workflow_id, include_pins=False)
    print(json.dumps(workflow_summary(workflow), indent=2))
    if not args.apply:
        print("DRY RUN: test double not unpublished/deleted. Re-run with --apply.")
        return
    if workflow.get("active") is True:
        client.unpublish_workflow(workflow_id)
        workflow = client.get_workflow(workflow_id, include_pins=False)
        if workflow.get("active") is True:
            raise ReleaseError("Test double remains active after deactivate")
    if args.delete:
        client.delete_workflow(workflow_id)
        print(f"Deleted test double {workflow_id}")
    else:
        print(f"Unpublished test double {workflow_id}; retained for evidence review")


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=os.getenv("N8N_BASE_URL", ""),
        help="n8n instance URL or API root; env N8N_BASE_URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("N8N_API_KEY", ""),
        help="n8n Public API key; env N8N_API_KEY",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", help="Read-only backup and safety inspection")
    add_connection_args(p)
    p.add_argument("--workflow-id", default=os.getenv("WF1_ID", ""), required=not bool(os.getenv("WF1_ID")))
    p.add_argument("--out-dir", default="wf1-release-evidence")
    p.add_argument("--run-static", action="store_true")
    p.add_argument("--patched", default=str(DEFAULT_PATCHED))
    p.add_argument("--static-test", default=str(DEFAULT_STATIC_TEST))
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("deploy", help="PUT patched production workflow after inactive precheck")
    add_connection_args(p)
    p.add_argument("--workflow-id", default=os.getenv("WF1_ID", ""), required=not bool(os.getenv("WF1_ID")))
    p.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    p.add_argument("--out-dir", default="wf1-release-evidence")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_deploy)

    p = sub.add_parser("create-double", help="Create and optionally publish production-mode test double")
    add_connection_args(p)
    p.add_argument("--source-workflow-id", default=os.getenv("WF1_ID", ""), required=not bool(os.getenv("WF1_ID")))
    p.add_argument("--project-id", default=os.getenv("N8N_PROJECT_ID"))
    p.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    p.add_argument("--run-id")
    p.add_argument("--out-dir", default="wf1-release-evidence")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_create_double)

    p = sub.add_parser("emit-fixtures", help="Write synthetic T1-T7 fixture files without network calls")
    p.add_argument("--run-id")
    p.add_argument("--out-dir", default="wf1-release-evidence")
    p.set_defaults(func=cmd_emit_fixtures)

    p = sub.add_parser("run-suite", help="Run T1-T7 against a published test double")
    add_connection_args(p)
    p.add_argument("--state", required=True, help="State JSON produced by create-double")
    p.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    p.add_argument("--out-dir", default="wf1-release-evidence")
    p.add_argument("--execution-timeout", type=float, default=90.0)
    p.add_argument("--webhook-timeout", type=float, default=30.0)
    p.add_argument("--between-tests", type=float, default=2.0)
    p.add_argument("--melisa-warned", action="store_true")
    p.add_argument("--confirm-synthetic-side-effects", action="store_true")
    p.add_argument("--tests", default=None, help="comma-separated fixture ids to run (default: all)")
    p.add_argument("--pipedrive-base-url", default=os.getenv("PIPEDRIVE_BASE_URL", "https://api.pipedrive.com"))
    p.add_argument("--pipedrive-token", default=os.getenv("PIPEDRIVE_API_TOKEN", ""),
                   help="Used only for the T-F10 mid-suite lead deletion; env PIPEDRIVE_API_TOKEN")
    p.set_defaults(func=cmd_run_suite)

    p = sub.add_parser("cleanup-pipedrive", help="Delete synthetic entities from a cleanup manifest")
    p.add_argument("--manifest", required=True)
    p.add_argument(
        "--pipedrive-base-url",
        default=os.getenv("PIPEDRIVE_BASE_URL", "https://api.pipedrive.com"),
    )
    p.add_argument("--pipedrive-token", default=os.getenv("PIPEDRIVE_API_TOKEN", ""))
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_cleanup_pipedrive)

    p = sub.add_parser("teardown", help="Unpublish and optionally delete the test double")
    add_connection_args(p)
    p.add_argument("--state", required=True)
    p.add_argument("--delete", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_teardown)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
