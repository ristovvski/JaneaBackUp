"""
dnc_pre_add_gate_monitor -- synthetic liveness check for dnc_pre_add_gate, built 2026-08-20
after the gate silently lost its trigger registration overnight (crashed during the I-04
instance-strain incident, came back as a 404 with zero notification -- found only because Clay
happened to call it and Nik noticed). The gate now has an external consumer (Clay/Stefan); a dead
gate either blocks a launch or, worse, tempts someone to skip the check entirely. Same idle-guard
philosophy as the S3/I-04 reporters, adapted for a request-driven service instead of a poller:
fire a real synthetic request against the gate's OWN public webhook every 15 min, alert on
anything but a clean 2-way split; post one daily heartbeat so silence never reads as "nobody's
watching" (same class as the WF-2H fix this whole project keeps reusing).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
OPS_CHANNEL = "C0B8GCVNR5W"
CORE_ERROR_HANDLER_ID = "BbrXPABgOaaTJjD6"
GATE_WEBHOOK_URL = "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}"
# same not-yet-created-table situation as GATE_QUEUE_TABLE in build_dnc.py -- needs the real id
# substituted once Nik creates dnc_gate_queue (mode:"name" has proven unreliable from API-created
# workflows on this instance, 2026-08-26 finding). Both outputs of "Check Queue" feed the same
# next step so a missing/misresolving table degrades to "queue depth unknown", never kills the
# monitor.
GATE_QUEUE_TABLE = {"__rl": True, "mode": "name", "value": "dnc_gate_queue"}


def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_").replace("?", ""), "name": name,
         "type": ntype, "typeVersion": tv, "position": [x, y]}
    if extra:
        n.update(extra)
    return n


def conns(pairs):
    c = {}
    for a, b in pairs:
        c.setdefault(a, {"main": [[]]})
        c[a]["main"][0].append({"node": b, "type": "main", "index": 0})
    return c


def code_node(name, js, x, y=300):
    return node(name, "n8n-nodes-base.code", {"jsCode": js, "mode": "runOnceForAllItems"}, x, y, tv=2)


def if_bool(name, expr, x, y=300):
    return node(name, "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"},
                       "combinator": "and",
                       "conditions": [{"leftValue": expr, "rightValue": True,
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}
    }, x, y, tv=2)


def slack_post(name, text_expr, x, y=300, channel_expr=None):
    return node(name, "n8n-nodes-base.slack", {
        "resource": "message", "operation": "post", "select": "channel",
        "channelId": {"__rl": True, "mode": "id", "value": channel_expr or OPS_CHANNEL},
        "text": text_expr, "otherOptions": {}
    }, x, y, tv=2.2, extra={"credentials": {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}},
                            "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3})


def wf(name, nodes_, connections):
    return {"name": name, "nodes": nodes_, "connections": connections,
            "settings": {"executionOrder": "v1", "errorWorkflow": CORE_ERROR_HANDLER_ID}, "active": False}


def write(path, obj):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    json.load(open(full, encoding="utf-8"))
    print("wrote", path, "(%d nodes)" % len(obj["nodes"]))


check_js = (
    # a KNOWN fixture, same shape as the static test: one confirmed-blocked identity (Dennis,
    # already in the registry from this project's own earlier work) + one confirmed-clean
    # identity. A healthy gate returns exactly {clean:1, blocked:1, unresolvable:0}; anything
    # else -- wrong counts, a 404, a malformed body -- is the gate lying or dead, either way
    # worth knowing about before the next campaign launch trusts it.
    # duration_ms/row_count (2026-08-26, gate v2): the gate self-reports these now -- surfaced
    # here so the heartbeat shows real headroom over time instead of guessing at it.\n"
    "const resp = $json;\n"
    "const c = resp.counts || {};\n"
    "const healthy = resp.error === undefined && c.total === 2 && c.clean === 1 && c.blocked === 1 && c.unresolvable === 0;\n"
    "return [{ json: { healthy, counts: c, raw_error: resp.error || null,\n"
    "  duration_ms: resp.duration_ms != null ? resp.duration_ms : null } }];\n"
)
error_branch_js = (
    "return [{ json: { healthy: false, counts: null,\n"
    "  raw_error: ($json.error && $json.error.message) || 'request failed (see execution)' } }];\n"
)
report_js = (
    # queue-depth history + stuck-drainer detection, 2026-08-26 (gate v3): a silently stuck
    # drainer is the new failure mode a pure "is the gate up" check can't see -- the gate itself
    # would answer every synthetic ping just fine while a real backlog never moves. Stuck =
    # depth stayed >0 and non-decreasing across the last 4 readings (1h window at 15-min cadence
    # -- comfortably past the ~30min turnaround Nik accepted, so this doesn't cry wolf on a
    # normal-sized burst still draining). Alerts once per stuck EPISODE, not every 15 min while
    # stuck, and re-arms once depth actually drops.\n"
    "const r = $json;\n"
    "const sd = $getWorkflowStaticData('global');\n"
    "const today = new Date().toISOString().slice(0, 10);\n"
    "if (sd.statDate !== today) {\n"
    "  sd.statDate = today; sd.checksToday = 0; sd.failuresToday = 0;\n"
    "  sd.durationsToday = []; sd.maxDurationToday = null;\n"
    "}\n"
    "sd.checksToday += 1;\n"
    "if (!r.healthy) sd.failuresToday += 1;\n"
    "if (r.duration_ms != null) {\n"
    "  sd.durationsToday = sd.durationsToday || [];\n"
    "  sd.durationsToday.push(r.duration_ms);\n"
    "  if (sd.durationsToday.length > 200) sd.durationsToday.shift(); // bounded, never grows unbounded\n"
    "  sd.maxDurationToday = Math.max(sd.maxDurationToday || 0, r.duration_ms);\n"
    "}\n"
    "const queueRows = $('Check Queue').all().map(i => i.json);\n"
    # predicate fix, 2026-08-28: the old check (`queueRows.length === 1 && queueRows[0].error`)
    # was a NEGATIVE, absence-of-error check -- the exact class of bug this project already got
    # burned by once (n8n dataTable error branches are NOT uniform: some ops return {error:"..."},
    # others echo the original upstream input item unchanged with no marker at all). If "Check
    # Queue" ever failed by echoing its trigger's own item instead of an {error} object, that
    # single non-row item would have slipped past the old check as "1 ok row" -- a phantom
    # nonzero, never-draining depth, a FALSE stuck alert. Fixed with a POSITIVE shape check: a row
    # only counts if it actually looks like a real queued row (status + row_key both present, the
    # two columns every real Enqueue Rows write sets) -- true both when the array is genuinely
    # empty (vacuous .every()) and when it holds only real rows.\n"
    "const looksLikeRealRow = (r) => r && typeof r.status === 'string' && typeof r.row_key === 'string';\n"
    "const queueOk = queueRows.every(looksLikeRealRow);\n"
    "const depth = queueOk ? queueRows.length : null;\n"
    "sd.queueHistory = (sd.queueHistory || []).concat([{ depth }]).slice(-4);\n"
    "const h = sd.queueHistory;\n"
    # explicit depth>0 term, not just incidental via .every(): depth === 0 (a genuinely drained,
    # idle queue) must read as idle, never stuck -- made a first-class, self-documenting condition
    # instead of relying on it falling out of the history-every() check by coincidence.\n"
    "const stuck = depth != null && depth > 0 && h.length >= 4"
    " && h.every(x => x.depth != null && x.depth > 0) && h[h.length - 1].depth >= h[0].depth;\n"
    "const wasAlerted = !!sd.queueStuckAlerted;\n"
    "const shouldAlertQueue = stuck && !wasAlerted;\n"
    "sd.queueStuckAlerted = stuck;\n"
    "return [{ json: Object.assign({}, r, { checks_today: sd.checksToday, failures_today: sd.failuresToday,\n"
    "  max_duration_ms_today: sd.maxDurationToday, queue_depth: depth, queue_ok: queueOk,\n"
    "  queue_stuck: stuck, should_alert_queue: shouldAlertQueue }) }];\n"
)

nodes = [
    node("Poll Timer", "n8n-nodes-base.scheduleTrigger",
        {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}, -900, tv=1.2),
    node("Fire Gate", "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": GATE_WEBHOOK_URL,
        "sendBody": True, "specifyBody": "json",
        "jsonBody": json.dumps({"rows": [
            {"label": "monitor: known-blocked", "email": "pii-d50f3785@example.invalid"},
            {"label": "monitor: known-clean", "email": "monitor-clean-probe-xyz@example.invalid"},
        ]}),
        "options": {"timeout": 30000},
    }, -700, tv=4.2, extra={"onError": "continueErrorOutput", "retryOnFail": False}),
    code_node("Check Health", check_js, -500),
    code_node("Check Health (error branch)", error_branch_js, -500, y=160),
    node("Merge Health Paths", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 3, "options": {}}, -300, y=80, tv=3),
    node("Check Queue", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get", "dataTableId": GATE_QUEUE_TABLE,
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "status", "condition": "eq", "keyValue": "=pending"}]},
        "options": {}
    }, -700, y=260, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2}),
    code_node("Track + Report", report_js, -100, y=80),
    if_bool("Healthy?", "={{ $json.healthy }}", 100, y=80),
    slack_post("Alert: Gate Unhealthy",
               "=:rotating_light: dnc_pre_add_gate liveness check FAILED -- counts: {{ JSON.stringify($json.counts) }} "
               "error: {{ $json.raw_error }}. Campaign launches should NOT trust the gate until this clears. "
               "({{ $json.failures_today }} failure(s) today out of {{ $json.checks_today }} checks)",
               300, y=40),
    if_bool("Queue Stuck?", "={{ $json.should_alert_queue }}", 100, y=260),
    slack_post("Alert: Queue Stuck",
               "=:rotating_light: dnc_gate_queue_drainer looks STUCK -- depth {{ $json.queue_depth }} hasn't "
               "dropped across the last hour of checks. Real Clay/Stefan requests are waiting past the "
               "accepted ~30min turnaround. Check dnc_gate_queue_drainer's recent executions.",
               300, y=260),
    # daily heartbeat, independent trigger, same shape as S3/I-04's own -- silence must never be
    # mistaken for "nobody's watching" when EVERY check today happened to be healthy.
    node("Heartbeat Timer", "n8n-nodes-base.scheduleTrigger",
        {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]}}, -900, y=400, tv=1.2),
    code_node("Heartbeat Report", (
        # duration/headroom line, 2026-08-26: after the two burst incidents, "is it up" isn't
        # enough -- surface actual measured latency so headroom is seen, not guessed.\n"
        "const sd = $getWorkflowStaticData('global');\n"
        "const checks = sd.checksToday || 0, failures = sd.failuresToday || 0;\n"
        "const durations = sd.durationsToday || [];\n"
        "const maxDur = sd.maxDurationToday;\n"
        "const avgDur = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null;\n"
        "sd.checksToday = 0; sd.failuresToday = 0; sd.statDate = null; sd.durationsToday = []; sd.maxDurationToday = null;\n"
        "const durLine = avgDur != null ? ` -- 2-row check latency today: avg ${avgDur}ms, max ${maxDur}ms` : '';\n"
        "return [{ json: {\n"
        "  slack_text: `:heartbeat: DNC gate monitor alive: ${checks} check(s) today, ${failures} failure(s)${durLine}`,\n"
        "} }];\n"
    ), -700, y=400),
    slack_post("Heartbeat Post", "={{ $json.slack_text }}", -500, y=400),
]

connections = conns([
    ("Poll Timer", "Fire Gate"), ("Poll Timer", "Check Queue"),
    ("Track + Report", "Healthy?"), ("Track + Report", "Queue Stuck?"),
    ("Healthy?", "Alert: Gate Unhealthy"),
    ("Queue Stuck?", "Alert: Queue Stuck"),
    ("Heartbeat Timer", "Heartbeat Report"), ("Heartbeat Report", "Heartbeat Post"),
])
connections["Fire Gate"] = {"main": [
    [{"node": "Check Health", "type": "main", "index": 0}],
    [{"node": "Check Health (error branch)", "type": "main", "index": 0}],
]}
connections["Check Health"] = {"main": [[{"node": "Merge Health Paths", "type": "main", "index": 0}]]}
connections["Check Health (error branch)"] = {"main": [[{"node": "Merge Health Paths", "type": "main", "index": 1}]]}
# both outputs of Check Queue (success or table-not-found error) feed the SAME merge slot --
# index ordering (0/1 = gate health, 2 = queue) is what keeps $json in "Track + Report" pointing
# at the gate-health result regardless of how many queue rows tag along in the same merged batch.
connections["Check Queue"] = {"main": [
    [{"node": "Merge Health Paths", "type": "main", "index": 2}],
    [{"node": "Merge Health Paths", "type": "main", "index": 2}],
]}
connections["Merge Health Paths"] = {"main": [[{"node": "Track + Report", "type": "main", "index": 0}]]}
connections["Healthy?"] = {"main": [
    [], [{"node": "Alert: Gate Unhealthy", "type": "main", "index": 0}],
]}
connections["Queue Stuck?"] = {"main": [
    [], [{"node": "Alert: Queue Stuck", "type": "main", "index": 0}],
]}

write("workflows/dnc_pre_add_gate_monitor/dnc_pre_add_gate_monitor.json", wf("dnc_pre_add_gate_monitor", nodes, connections))
print("OK")
