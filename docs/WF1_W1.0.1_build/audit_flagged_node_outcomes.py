#!/usr/bin/env python3
"""Turn the flagged-node RISK list into an EVIDENCE list.

The pattern (onError swallow + code in an expression) is a risk factor, not a verdict - several
flagged nodes demonstrably post fine. For each one, read every retained execution and classify:

  PROVEN OK      - at least one run returned ok:true          -> pattern present, not biting
  PROVEN BROKEN  - runs exist and all errored                 -> fix now
  NEVER RUN      - no execution has exercised it              -> unknown, and unknown is the
                   dangerous state: it will first be exercised in an incident

That last bucket is the real finding. A node that has never run is not 'fine', it is untested -
which is exactly what WF-2's Reply Alert was until the flip made it fire.
"""
import json, os, ssl, time, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
IDS = {"WF-1": "2jdjKM2NJr473GdA", "WF-2": "jp7rum9Z0YDJkQWv", "WF-2R": "U8Bb7Pdq7S6nzYPa",
       "WF-2S": "6Y92ryBwYoy6z0Jx", "WF-2H": "nK3yIOqRcBearV8s", "WF-ERR": "BbrXPABgOaaTJjD6"}


def n8n(p, q=None):
    u = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    r = urllib.request.Request(u, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


flagged = json.load(open(os.path.join(HERE, "wf1-release-evidence",
                                      "audit_silent_failure_nodes.json"), encoding="utf-8"))
want = {}
for f in flagged:
    want.setdefault(f["wf"], set()).add(f["node"])

results = {}
for label, nodes in want.items():
    d = n8n("/api/v1/executions", {"workflowId": IDS[label], "limit": 250})
    rows = [e for e in (d.get("data") or []) if e.get("startedAt")]
    tally = {n: {"runs": 0, "ok": 0, "err": 0, "last_err": None} for n in nodes}
    for e in rows:
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        for n in nodes:
            if n not in rd:
                continue
            t = tally[n]
            t["runs"] += 1
            try:
                j = rd[n][0]["data"]["main"][0][0]["json"]
            except Exception:
                j = {}
            if j.get("ok") is True:
                t["ok"] += 1
            elif j.get("error") or rd[n][0].get("error"):
                t["err"] += 1
                t["last_err"] = str(j.get("error") or rd[n][0].get("error"))[:60]
        time.sleep(0.01)
    results[label] = tally

print(f"{'wf':<7} {'node':<26} {'runs':>5} {'ok':>4} {'err':>4}  verdict")
print("-" * 96)
buckets = {"PROVEN OK": [], "PROVEN BROKEN": [], "NEVER RUN": [], "MIXED": []}
for label, tally in results.items():
    for n, t in sorted(tally.items()):
        if t["runs"] == 0:
            v = "NEVER RUN"
        elif t["ok"] and not t["err"]:
            v = "PROVEN OK"
        elif t["err"] and not t["ok"]:
            v = "PROVEN BROKEN"
        else:
            v = "MIXED"
        buckets[v].append(f"{label}/{n}")
        extra = f"  last_err={t['last_err']}" if t["last_err"] else ""
        print(f"{label:<7} {n:<26} {t['runs']:>5} {t['ok']:>4} {t['err']:>4}  {v}{extra}")

print("\n--- summary ---")
for k, v in buckets.items():
    print(f"  {k:<14} {len(v)}")
    for x in v:
        print(f"      {x}")
print("\nNEVER RUN is the bucket that matters: those expressions have never been parsed by n8n in "
      "anger, so their first exercise will be during the incident they exist to report.")
json.dump({k: v for k, v in buckets.items()},
          open(os.path.join(HERE, "wf1-release-evidence", "audit_flagged_outcomes.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False)
