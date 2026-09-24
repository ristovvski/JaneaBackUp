#!/usr/bin/env python3
"""READ-ONLY verification of two surprises before they get reported:

V1. Make's 'responded label' scenario 8557478 ran only 4x in 72h against 12 Smartlead replies,
    and NOT at all near the Ashwin reply. Before claiming 'Make missed it too', identify which
    lead each of those 4 runs actually processed (execution detail / bundles).

V2. My reply truth-set came from /leads-statistics history[]. Cross-check it against a fully
    independent source - /campaigns/{id}/statistics reply_time - so a truncated history[] can't
    silently shrink the truth set. Also explains the one Make run (08-04T22:01) with no matching
    reply in the v3 list.

V3. The 3 successful post-recovery WF-2 executions produced no Shadow Log rows at all - find out
    which nodes actually ran in them (were they real events, or probes/early-exits?).

No writes anywhere.
"""
import json, os, ssl, time
from datetime import datetime, timedelta, timezone
import urllib.error, urllib.parse, urllib.request

SLK = os.environ["SMARTLEAD_API_KEY"]
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
MAKE_TOKEN = os.environ["MAKE_API_TOKEN"]
MAKE_ZONE = os.environ.get("MAKE_ZONE", "eu2")
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(hours=72)
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

CAMPS_EMAIL = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
               3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}
RESP_SCEN = 8557478
RUNS = ["1785880875234_d85bd23d596d4c9db2b46d9fef5ca860",
        "1785870693261_2cd6d147ca19456cac40acef2ac38c0f",
        "1785862572325_1d4005aa7e744f868b2fde7566cb4a94",
        "1785776093555_68e4ce38a9dd457a8e51c6addaf465c6"]


def _get(url, headers, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code, "__body": body}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}
    return {}


def sl(path, params):
    q = dict(params); q["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}",
                {"User-Agent": UA})


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    return _get(f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}",
                {"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})


def mk(path, params=None):
    q = urllib.parse.urlencode(params or {}, doseq=True)
    return _get(f"https://{MAKE_ZONE}.make.com/api/v2{path}" + (f"?{q}" if q else ""),
                {"Authorization": f"Token {MAKE_TOKEN}", "User-Agent": UA})


def ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


print("=" * 104)
print("V1. Make scenario 8557478 - which lead did each of the 4 runs process?")
print("=" * 104)
for rid in RUNS:
    got = None
    for path in (f"/scenarios/{RESP_SCEN}/logs/{rid}",
                 f"/scenarios/{RESP_SCEN}/executions/{rid}"):
        d = mk(path)
        if not d.get("__err"):
            got = (path, d); break
    if not got:
        print(f"  {rid}: detail unavailable via /logs and /executions")
        continue
    path, d = got
    blob = json.dumps(d, default=str)
    print(f"\n  run {rid}  via {path}  ({len(blob)} bytes)")
    # pull any email-looking strings out of the detail, so we can name the lead
    import re
    emails = sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", blob)))
    print(f"     emails in detail: {emails[:12]}")
    for k in ("status", "operations", "transfer", "timestamp", "duration", "type"):
        if k in d:
            print(f"     {k}={d[k]}")

print("\n" + "=" * 104)
print("V2. independent reply truth-set: /campaigns/{id}/statistics reply_time (vs leads-statistics)")
print("=" * 104)
stat_replies = []
for cid, name in CAMPS_EMAIL.items():
    off = 0
    while True:
        st = sl(f"/campaigns/{cid}/statistics", {"offset": off, "limit": 100})
        if st.get("__err"):
            print(f"  [{cid}] ERROR {st['__err']}"); break
        rows = st.get("data") or []
        for r in rows:
            t = ts(r.get("reply_time"))
            if t and t >= SINCE:
                stat_replies.append({"campaign": name, "email": str(r.get("lead_email") or "").lower(),
                                     "reply_time": t.isoformat(),
                                     "category": r.get("lead_category"), "seq": r.get("sequence_number")})
        off += len(rows)
        if len(rows) < 100 or off >= int(st.get("total_stats") or 0):
            break
        time.sleep(0.15)
stat_replies.sort(key=lambda r: r["reply_time"])
print(f"replies via /statistics reply_time in 72h: {len(stat_replies)}")
for r in stat_replies:
    print(f"  {r['reply_time']}  {r['campaign']:<20} {str(r['category']):<22} {r['email']}")

hist_set = {("2026-08-03T16:54:19+00:00", "pii-0ddf11ef@example.invalid")}
print("\n  (v3 leads-statistics found 12; compare counts above - a mismatch means one source"
      " is incomplete and the truth-set must be the union)")

print("\n" + "=" * 104)
print("V3. post-recovery WF-2 successful executions - which nodes actually ran?")
print("=" * 104)
for eid in (13549, 13579, 13661):
    d = n8n(f"/api/v1/executions/{eid}", {"includeData": "true"})
    if d.get("__err"):
        print(f"  {eid}: {d}"); continue
    rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
    print(f"\n  exec {eid} startedAt={d.get('startedAt')} status={d.get('status')} "
          f"mode={d.get('mode')}")
    print(f"     nodes: {list(rd.keys())}")
    for nm in list(rd.keys())[:4]:
        try:
            j = rd[nm][0]["data"]["main"][0][0]["json"]
            print(f"     [{nm}] {json.dumps(j, ensure_ascii=False, default=str)[:400]}")
        except Exception:
            pass

with open(os.path.join(HERE, "wf1-release-evidence", "ashwin_verify_v4.json"), "w",
          encoding="utf-8") as f:
    json.dump({"stat_replies": stat_replies}, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/ashwin_verify_v4.json")
