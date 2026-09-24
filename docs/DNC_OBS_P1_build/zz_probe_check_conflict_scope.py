#!/usr/bin/env python3
"""
Person-69cbb908's conflict (LinkedIn resolves to a Noah-Aug-11-import row, email resolves to a
DIFFERENT S3-own-write row) is a foreseeable side effect of fixing S3_PERSON_EXTRACT_JS: before
that fix, S3's own writes never had a LinkedIn URL, so they could never collide with the earlier
LI-keyed Noah-import rows. Now that li is read correctly, any of the other 4 people from the same
2026-08-12 Noah/Surfe batch could hit the identical split. Read-only check across all 5.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"
WEBHOOK_PATH = "zz-probe-check-conflict-scope"

CANDIDATES = [
    {"person_id": 85763, "name": "Person-69cbb908", "li_slug": "barryheavey"},
    {"person_id": 85762, "name": "Person-27241402", "li_slug": "sebastianlux"},
    {"person_id": 85760, "name": "Person-d443e430", "li_slug": "brycemcdonnell"},
    {"person_id": 85759, "name": "Person-6196b61e", "li_slug": "chrismccready"},
    {"person_id": 85758, "name": "Person-4988c2b0", "li_slug": "gildror"},
]


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
PD_TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]


def n8n(path, method="GET", body=None):
    import requests
    if method == "GET":
        r = requests.get(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}, timeout=30)
    else:
        r = requests.request(method, BASE + path, json=body,
                              headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                       "accept": "application/json"}, timeout=30)
    return r.json() if r.text else {}


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


def main():
    import requests
    # 1) confirm actual LinkedIn slugs live (don't trust the guessed slugs above)
    real_slugs = {}
    for c in CANDIDATES:
        r = requests.get(f"https://api.pipedrive.com/v1/persons/{c['person_id']}",
                          params={"api_token": PD_TOKEN}, timeout=20)
        d = (r.json() or {}).get("data") or {}
        li = d.get("66f0af69bec838dc3f90bb3f16c7d6087d8dbb20")
        real_slugs[c["person_id"]] = li

    build_js = "return " + json.dumps([
        {"pid": c["person_id"], "name": c["name"], "li": real_slugs[c["person_id"]]} for c in CANDIDATES
    ]) + ".map(x => ({ json: x }));\n"

    dt_get = node("Get by LI", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get",
        "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "linkedin_url_norm", "condition": "eq", "keyValue": "={{ $json.li }}"}]},
        "options": {}
    }, -400, tv=1)
    nodes = [
        node("Webhook", "n8n-nodes-base.webhook",
             {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
             -900, extra={"webhookId": "zzprobe0022"}),
        node("Build", "n8n-nodes-base.code", {"jsCode": build_js, "mode": "runOnceForAllItems"}, -680, tv=2),
        dt_get,
        node("Report", "n8n-nodes-base.code",
             {"jsCode": "return [{ json: { rows: $input.all().map(i => i.json) } }];\n", "mode": "runOnceForAllItems"},
             -200, tv=2),
        node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
    ]
    wf = {"name": "zz_probe_check_conflict_scope", "nodes": nodes,
          "connections": conns([("Webhook", "Build"), ("Build", "Get by LI"), ("Get by LI", "Report"),
                                 ("Report", "Respond")]), "settings": {}}
    created = n8n("/api/v1/workflows", "POST", {"name": wf["name"], "nodes": wf["nodes"],
                                                  "connections": wf["connections"], "settings": wf["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    req = urllib.request.Request(BASE + "/webhook/" + WEBHOOK_PATH, method="POST", data=b"{}",
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        raw = r.read()
    result = json.loads(raw)
    by_li_pid = {row.get("linkedin_url_norm"): row.get("pipedrive_person_id") for row in result.get("rows", [])}

    print("=== conflict-scope check ===")
    for c in CANDIDATES:
        li = real_slugs[c["person_id"]]
        li_norm = li  # already a full URL per live check
        found_pid = by_li_pid.get(li_norm)
        conflicts = found_pid is not None and found_pid != c["person_id"]
        also_none = found_pid is None
        print(f"  {c['name']:20s} pid={c['person_id']} li={li!r} "
              f"-> LI-row pid={found_pid} conflict_risk={'YES' if conflicts else ('no LI row' if also_none else 'same row, no conflict')}")

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")


if __name__ == "__main__":
    main()
