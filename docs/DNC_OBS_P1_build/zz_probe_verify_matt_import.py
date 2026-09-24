#!/usr/bin/env python3
"""
Verify the Matt Carothers connections fire actually landed. My chunk-fire report_js assumed a top-
level `action` field that only the noop/conflict branches of DNC__UpsertLedger__v1 return -- the
write branch (insert/update) returns the raw upserted ROW instead (confirmed by reading
build_dnc.py's Route/dt_upsert wiring), so every result came back "unknown" -- a report-node bug,
not necessarily a write bug. This probe checks the real registry state instead of trusting that
broken telemetry.

Two independent, simple checks (kept as separate single-branch flows -- no merge nodes -- after a
first draft with two merges got needlessly complex):
1. Count rows where owner_tag = "Matt Carothers" (exact-match filter, server-side) -- undercounts
   rows where a connection already had a stronger existing reason (owner_tag only gets set when
   the FINAL merged reason is manual_offboard_eligible).
2. Spot-check specific identity_keys (3 internal-colleague rows + 3 external rows) by exact get, to
   confirm `source` actually contains the "onboarding_import:Matt Carothers" token (parsed by
   splitting on the comma delimiter dncMergeSources uses -- never a substring-blob check).
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_"), "name": name,
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


def run_probe(name, webhook_path, nodes, wiring):
    wf_json = {"name": name, "nodes": nodes, "connections": conns(wiring), "settings": {}}
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            raise RuntimeError("activation did not take")
        webhook_url = BASE + "/webhook/" + webhook_path
        time.sleep(2)
        req = urllib.request.Request(webhook_url, method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
        result = json.loads(raw)
    except Exception:
        try:
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        except Exception:
            pass
        print(f"probe {name} FAILED, workflow id={wid} left for diagnosis")
        raise
    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    return result


def check_owner_tag_count():
    nodes = [
        node("Webhook", "n8n-nodes-base.webhook",
             {"httpMethod": "POST", "path": "zz-probe-matt-owner-count", "responseMode": "responseNode",
              "options": {}}, -600, extra={"webhookId": "zzprobe0012"}),
        node("Get by owner_tag", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "get",
            "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
            "returnAll": True, "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "owner_tag", "condition": "eq", "keyValue": "Matt Carothers"}]},
            "options": {}
        }, -400, tv=1),
        node("Report", "n8n-nodes-base.code",
             {"jsCode": "return [{ json: { owner_tag_match_count: $input.all().length } }];\n",
              "mode": "runOnceForAllItems"}, -200, tv=2),
        node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
    ]
    return run_probe("zz_probe_matt_owner_count", "zz-probe-matt-owner-count", nodes,
                      [("Webhook", "Get by owner_tag"), ("Get by owner_tag", "Report"), ("Report", "Respond")])


def check_spot_sample(sample):
    build_js = "return " + json.dumps(sample) + ".map(x => ({ json: x }));\n"
    nodes = [
        node("Webhook", "n8n-nodes-base.webhook",
             {"httpMethod": "POST", "path": "zz-probe-matt-spot-check", "responseMode": "responseNode",
              "options": {}}, -900, extra={"webhookId": "zzprobe0013"}),
        node("Build Items", "n8n-nodes-base.code", {"jsCode": build_js, "mode": "runOnceForAllItems"}, -680, tv=2),
        # single unambiguous condition -- every sampled row has a LinkedIn URL (confirmed: all
        # 1491 writable rows do), so no OR-with-a-possibly-empty-email ambiguity risk.
        node("Get Row", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "get",
            "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
            "matchType": "allConditions",
            "filters": {"conditions": [
                {"keyName": "linkedin_url_norm", "condition": "eq", "keyValue": "={{ $json.li }}"},
            ]}, "options": {}
        }, -400, tv=1),
        node("Report", "n8n-nodes-base.code", {
            "jsCode": (
                "const rows = $input.all().map(i => i.json);\n"
                "const out = rows.map(r => ({\n"
                "  full_name: r.full_name, identity_key: r.identity_key, reason: r.reason,\n"
                "  owner_tag: r.owner_tag, entry_type: r.entry_type, source: r.source,\n"
                "  has_matt_tag: (r.source || '').split(',').map(s => s.trim())"
                ".includes('onboarding_import:Matt Carothers'),\n"
                "}));\n"
                "return [{ json: { rows: out } }];\n"
            ), "mode": "runOnceForAllItems"}, -200, tv=2),
        node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
    ]
    return run_probe("zz_probe_matt_spot_check", "zz-probe-matt-spot-check", nodes,
                      [("Webhook", "Build Items"), ("Build Items", "Get Row"), ("Get Row", "Report"),
                       ("Report", "Respond")])


def main():
    with open(os.path.join(HERE, "fixtures", "matt_carothers_connections_writable.json"), encoding="utf-8") as f:
        rows = json.load(f)
    internal = [r for r in rows if (r.get("_company") or "").lower() == "janea systems"][:3]
    external = [r for r in rows if (r.get("_company") or "").lower() != "janea systems"][:3]
    sample = [{"li": r["linkedin_url"], "email": r["email"], "label": r["full_name"], "company": r["_company"]}
              for r in (internal + external)]

    print("=== owner_tag='Matt Carothers' count ===")
    owner_result = check_owner_tag_count()
    print(json.dumps(owner_result, indent=2))

    print("\n=== spot check (3 internal + 3 external) ===")
    spot_result = check_spot_sample(sample)
    for original, found in zip(sample, spot_result.get("rows", [])):
        print(f"  {original['label']:25s} ({original['company'] or 'external'}): "
              f"reason={found.get('reason')} owner_tag={found.get('owner_tag')} "
              f"entry_type={found.get('entry_type')} has_matt_tag={found.get('has_matt_tag')}\n"
              f"      source={found.get('source')!r}")


if __name__ == "__main__":
    main()
