"""Shared n8n deploy helpers. Import these instead of hand-rolling a PUT body.

WHY: on 2026-08-10 a WF-1 deploy PUT returned a bare HTTP 400 and left the LIVE workflow
DEACTIVATED. Cause: `GET /workflows/{id}` returns settings keys that `PUT` refuses to accept
(`timeSavedMode`, `callerPolicy`, `availableInMCP`). The failure mode is nasty because the
deactivate has already happened by then - so a rejected PUT is not a no-op, it is an outage.
The rule lived in memory and still got walked into; it lives in code now.
"""

# Everything the n8n public API accepts on PUT /workflows/{id}. Anything else present in a GET
# response is UI-only and MUST be stripped.
ALLOWED_SETTINGS = ("executionOrder", "errorWorkflow", "saveDataSuccessExecution",
                    "saveDataErrorExecution", "saveManualExecutions", "saveExecutionProgress",
                    "executionTimeout", "timezone")


def put_body(wf):
    """Build a PUT-safe body from a workflow dict as returned by GET."""
    return {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": {k: v for k, v in (wf.get("settings") or {}).items()
                         if k in ALLOWED_SETTINGS}}


def stripped_keys(wf):
    """Which UI-only keys were dropped - worth printing so the strip is visible, not silent."""
    return sorted(k for k in (wf.get("settings") or {}) if k not in ALLOWED_SETTINGS)
