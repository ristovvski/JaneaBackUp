#!/usr/bin/env python3
"""INCIDENT sweep - how many leads lost '3. Responded' to the +16-35s clobber signature?

METHOD (authoritative half): every retained WF-1 execution that ran `M7 Lead Patch` states, in its
own recorded output, the exact label set it wrote. Compare that against the lead's label set NOW.
If we patched Responded and Responded is gone, the label was removed by someone else - that is a
fact from our own execution record, not an inference.

TIMING: the lead's `update_time` versus our patch time gives the delta. The documented clobber
signature is +16-35s. A delta in that band with Responded missing is the ghost; a much larger delta
could be a human.

RETENTION BOUNDARY, stated not hidden: n8n retains ~250 WF-1 executions (currently back to
2026-08-05). Anything between 2026-07-17 and the retention edge cannot be checked this way, and is
reported as UNKNOWN rather than assumed clean.

READ-ONLY. Produces a repair list; repairs nothing.
"""
import json, os, ssl, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF1 = "2jdjKM2NJr473GdA"
HERE = os.path.dirname(os.path.abspath(__file__))
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
NAMES = {"a6d359b0-6a45-11ed-ab46-5b95b19fcb18": "1. Cold",
         "ca698a50-bdfb-11ef-8172-510383583b0e": "2. Connected",
         "c9d4b550-bcf3-11ef-a843-357f91e826ec": "3. Responded",
         "3198a520-d19e-11ef-b90a-f3c01a30f7ae": "4. Positive Reply",
         "35edf580-d19e-11ef-935e-7d712003f1b4": "5. Meeting"}


def _get(url, headers, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=150, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:120]}
    return {}


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    return _get(f"{BASE}{path}?{q}" if q else f"{BASE}{path}",
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def pd(path):
    return _get("https://api.pipedrive.com" + path,
                {"x-api-token": PDT, "User-Agent": "janea-incident/1.0"})


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def nm(ids):
    return [NAMES.get(x, x) for x in (ids or [])]


ex = n8n("/api/v1/executions", {"workflowId": WF1, "limit": 250})
rows = sorted([e for e in (ex.get("data") or []) if e.get("startedAt")],
              key=lambda r: r["startedAt"])
print(f"retained WF-1 executions: {len(rows)}")
print(f"retention window: {rows[0]['startedAt']} .. {rows[-1]['startedAt']}")
print("NOTE: anything between 2026-07-17 and the start of this window is UNKNOWN by this method\n")

patches = []
for e in rows:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    if "M7 Lead Patch" not in rd:
        continue
    try:
        resp = rd["M7 Lead Patch"][0]["data"]["main"][0][0]["json"].get("data") or {}
    except Exception:
        continue
    lead_id = resp.get("id")
    written = resp.get("label_ids") or []
    if not lead_id:
        continue
    try:
        lead = rd["Normalize"][0]["data"]["main"][0][0]["json"].get("lead") or {}
    except Exception:
        lead = {}
    patches.append({"exec": e["id"], "at": e["startedAt"], "lead_id": lead_id,
                    "written": written, "name": lead.get("full_name"),
                    "profile": lead.get("profile_url")})
    time.sleep(0.03)

print(f"executions that patched lead labels: {len(patches)}")

# keep only the LATEST patch per lead - an earlier patch superseded by our own later one is not a wipe
latest = {}
for p in patches:
    if p["lead_id"] not in latest or p["at"] > latest[p["lead_id"]]["at"]:
        latest[p["lead_id"]] = p
print(f"distinct leads we patched: {len(latest)}\n")

wiped, intact, other, unknown = [], [], [], []
for lead_id, p in sorted(latest.items(), key=lambda kv: kv[1]["at"]):
    L = (pd(f"/v1/leads/{lead_id}") or {}).get("data") or {}
    if not L:
        unknown.append({**p, "reason": "lead not readable"})
        continue
    now_labels = L.get("label_ids") or []
    wrote_resp = RESPONDED in p["written"]
    has_resp = RESPONDED in now_labels
    upd = ts(L.get("update_time"))
    ours = ts(p["at"])
    delta = round((upd - ours).total_seconds(), 1) if (upd and ours) else None
    rec = {**p, "now": now_labels, "delta_s": delta, "update_time": L.get("update_time"),
           "person_id": L.get("person_id"), "title": L.get("title")}
    if not wrote_resp:
        other.append(rec)
    elif has_resp:
        intact.append(rec)
    else:
        wiped.append(rec)
    time.sleep(0.05)

print("=" * 104)
print("LEADS WHERE WE WROTE '3. Responded' AND IT IS NOW GONE")
print("=" * 104)
for r in sorted(wiped, key=lambda x: x["at"]):
    band = ""
    if r["delta_s"] is not None:
        band = ("  <<< +16-35s CLOBBER SIGNATURE" if 10 <= r["delta_s"] <= 60
                else f"  (delta {r['delta_s']}s)")
    print(f"\n  {r['at']}  {r['name']}  lead {str(r['lead_id'])[:8]}")
    print(f"      we wrote : {nm(r['written'])}")
    print(f"      now      : {nm(r['now'])}")
    print(f"      lead updated {r['update_time']}  delta {r['delta_s']}s{band}")

print("\n" + "=" * 104)
print("SUMMARY")
print("=" * 104)
print(f"  leads we patched with Responded, still intact : {len(intact)}")
print(f"  leads we patched with Responded, now WIPED    : {len(wiped)}")
print(f"  leads we patched without Responded            : {len(other)}")
print(f"  unreadable                                    : {len(unknown)}")
band = [r for r in wiped if r["delta_s"] is not None and 10 <= r["delta_s"] <= 60]
print(f"\n  of the wiped, within the +16-35s signature band: {len(band)}")
print(f"  delta distribution (wiped): "
      f"{Counter('<=60s' if (r['delta_s'] or 0) <= 60 else '>60s' for r in wiped)}")
resulting = Counter(tuple(sorted(nm(r['now']))) for r in wiped)
print(f"  resulting label sets after the wipe: {dict(resulting)}")

out = {"retention": {"from": rows[0]["startedAt"], "to": rows[-1]["startedAt"]},
       "wiped": wiped, "intact": intact, "other": other, "unknown": unknown}
with open(os.path.join(HERE, "wf1-release-evidence", "t4_label_wiper_sweep.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/t4_label_wiper_sweep.json  (repair list = 'wiped')")
