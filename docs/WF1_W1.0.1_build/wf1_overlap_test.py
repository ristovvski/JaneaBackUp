#!/usr/bin/env python3
"""ITEM 1 - is WF-1 exposed to the same staticData lost-update race? Read-only.

The auditor's method, rebuilt rather than copied so the two results are independent:
  * pull every WF-1 execution with start AND stop times
  * find OVERLAPPING pairs (B starts before A stops) - n8n persists staticData once, at execution
    end, as a whole object, so an overlap is a chance for the last finisher to clobber the other
  * for each execution, ask whether the claim it should have written is actually present
  * compare the loss rate for OVERLAPPED executions against NON-overlapped ones

The comparison is the whole test. A high absolute loss rate could have many causes; a loss rate that
tracks overlap is the race. WF-1 is structurally exposed by the same shape as WF-2 - webhook per
event, HeyReach bursting ~185/day - so the question is empirical, not architectural.

Verdict only. No writes; no deploy tonight regardless of outcome.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:100]}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


wf = n8n(f"/api/v1/workflows/{WF1}")
sd = (wf.get("staticData") or {}).get("global") or {}
print(f"WF-1 {wf.get('versionId')}  staticData stores: "
      f"{ {k: (len(v) if isinstance(v, dict) else type(v).__name__) for k, v in sd.items()} }")
seen_store = sd.get("seen") or {}
alerted = sd.get("__alerted_v1") or {}

ded = next((n for n in wf["nodes"] if n["name"] == "Dedupe"), None)
if ded:
    js = (ded.get("parameters") or {}).get("jsCode") or ""
    for i, line in enumerate(js.splitlines(), 1):
        if "seen[" in line or "const key" in line or "__dedupe" in line:
            print(f"   Dedupe:{i}| {line.strip()[:110]}")

ids, cursor = [], None
while True:
    q = {"workflowId": WF1, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/executions", q)
    ids += (p or {}).get("data") or []
    cursor = (p or {}).get("nextCursor")
    if not cursor:
        break
runs = []
for e in ids:
    a, b = ts(e.get("startedAt")), ts(e.get("stoppedAt"))
    if a and b:
        runs.append({"id": e["id"], "a": a, "b": b, "status": e.get("status")})
runs.sort(key=lambda r: r["a"])
print(f"\nexecutions with both timestamps: {len(runs)} of {len(ids)}")

# overlap detection
for r in runs:
    r["overlaps"] = 0
for i, r in enumerate(runs):
    for s in runs[i + 1:]:
        if s["a"] >= r["b"]:
            break
        r["overlaps"] += 1
        s["overlaps"] += 1
overlapped = [r for r in runs if r["overlaps"] > 0]
print(f"executions that overlapped at least one other: {len(overlapped)} "
      f"({100 * len(overlapped) / max(1, len(runs)):.0f}%)")
if runs:
    durs = sorted((r["b"] - r["a"]).total_seconds() for r in runs)
    print(f"duration median {durs[len(durs) // 2]:.1f}s  max {durs[-1]:.1f}s")

# claim presence per execution
print("\nchecking claim presence per execution (this is the slow part)...")
res = []
for i, r in enumerate(runs, 1):
    if i % 100 == 0:
        print(f"   ...{i}/{len(runs)}", flush=True)
    det = n8n(f"/api/v1/executions/{r['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}

    def o(nm, k=None):
        try:
            j = rd[nm][0]["data"]["main"][0][0]["json"]
            return j if k is None else j.get(k)
        except Exception:
            return None

    dk = o("Dedupe", "__dedupe_key") or o("Dedupe", "key")
    slack = o("M7 Critical Slack") or {}
    akey = o("M7 Alert Gate", "__alert_key")
    expect_alert = slack.get("ok") is True and akey
    res.append({"id": r["id"], "ov": r["overlaps"], "status": r["status"],
                "dk": dk, "dk_present": (dk in seen_store) if dk else None,
                "akey": akey if expect_alert else None,
                "ak_present": (akey in alerted) if expect_alert else None})

def rate(rows, field):
    have = [x for x in rows if x[field] is not None]
    if not have:
        return None, 0
    lost = sum(1 for x in have if x[field] is False)
    return (100.0 * lost / len(have)), len(have)

for field, label in (("dk_present", "dedupe key"), ("ak_present", "alert claim")):
    ov = [x for x in res if x["ov"] > 0]
    no = [x for x in res if x["ov"] == 0]
    r_ov, n_ov = rate(ov, field)
    r_no, n_no = rate(no, field)
    print(f"\n{label} LOSS RATE")
    print(f"   overlapped   : {('%.0f%%' % r_ov) if r_ov is not None else 'n/a'}  (n={n_ov})")
    print(f"   non-overlapped: {('%.0f%%' % r_no) if r_no is not None else 'n/a'}  (n={n_no})")

print("\nNOTE: WF-1's dedupe store rotates, so old absences are expiry not loss - the SIGNAL is the")
print("difference between the two rates, not either number alone.")
json.dump(res, open(os.path.join(HERE, "wf1-release-evidence", "wf1_overlap_test.json"), "w",
                    encoding="utf-8"), indent=2, default=str)
