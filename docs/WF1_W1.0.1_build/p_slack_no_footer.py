#!/usr/bin/env python3
"""Item 4 - drop the "link to workflow" attribution footer from EVERY Slack post in the estate.

Nik: the attribution line is noise; error alerts already carry an explicit execution link. Applies
to every workflow that posts, not just WF-1/WF-2 - the ops channel's unreadability comes from the
sum of all posters, so fixing two of six would leave the noise mostly intact.

`includeLinkToWorkflow` lives in the same `otherOptions` collection as the unfurl flags, which were
verified stored earlier tonight, so the shape is known rather than guessed.

Same honest limit as before: read-back proves the flag is STORED. Whether the footer disappears is
observational on the next post. Benign failure mode - the footer simply stays.
"""
import argparse, copy, json, os, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(path, q=None, method="GET", body=None, attempt=0):
    import time
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, q, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

# discover every workflow that has a Slack node - do not hardcode the list
rows, cursor = [], None
while True:
    q = {"limit": 100}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/workflows", q)
    rows += (p or {}).get("data") or []
    cursor = (p or {}).get("nextCursor")
    if not cursor:
        break

plans = {}
total = 0
for w in rows:
    wf = n8n(f"/api/v1/workflows/{w['id']}")
    slack = [n for n in wf["nodes"] if n["type"].endswith("slack")]
    if not slack:
        continue
    orig = copy.deepcopy(wf)
    todo = []
    for n in slack:
        oo = n.setdefault("parameters", {}).setdefault("otherOptions", {})
        if not isinstance(oo, dict):
            raise SystemExit(f"{w['name']}/{n['name']}: otherOptions is not an object")
        if oo.get("includeLinkToWorkflow") is False:
            continue
        oo["includeLinkToWorkflow"] = False
        todo.append(n["name"])
    total += len(todo)
    plans[w["id"]] = {"wf": wf, "orig": orig, "name": w["name"],
                      "slack": len(slack), "todo": todo, "active": w.get("active")}
    print(f"{w['name'][:38]:<40} slack={len(slack):<3} to_update={len(todo)}")

print(f"\ntotal Slack nodes to update: {total}")
if not total:
    print("(already applied everywhere)")
    sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
problems = []
for wid, p in plans.items():
    if not p["todo"]:
        continue
    safe = "".join(c if c.isalnum() else "_" for c in p["name"])[:24]
    with open(os.path.join(HERE, f"{safe}_backup_before_footer_{stamp}.json"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(p["orig"], indent=2, ensure_ascii=False))
    d = stripped_keys(p["wf"])
    n8n(f"/api/v1/workflows/{wid}", None, "PUT", put_body(p["wf"]))
    after = n8n(f"/api/v1/workflows/{wid}")
    aslack = [n for n in after["nodes"] if n["type"].endswith("slack")]
    bad = [n["name"] for n in aslack
           if ((n.get("parameters") or {}).get("otherOptions") or {}).get(
               "includeLinkToWorkflow") is not False]
    if bad:
        problems.append(f"{p['name']}: {bad}")
    if after.get("active") is not p["active"]:
        problems.append(f"{p['name']}: active={after.get('active')}")
    if len(after["nodes"]) != len(p["orig"]["nodes"]):
        problems.append(f"{p['name']}: node count changed")
    print(f"  {p['name'][:34]:<36} versionId={str(after.get('versionId'))[:8]} "
          f"active={after.get('active')} all_footerless="
          f"{not bad}")

print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for x in problems:
    print("  -", x)
sys.exit(1 if problems else 0)
