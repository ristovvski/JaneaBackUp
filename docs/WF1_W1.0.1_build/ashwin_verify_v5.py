#!/usr/bin/env python3
"""READ-ONLY. Final gaps before the report:

W1. Make 8557478 trigger type + FULL log span. '4 runs in 72h' only means 'Make missed replies'
    if the scenario is instant/webhook-triggered and the log list actually covers the window.
W2. Make incomplete-executions (DLQ) - a reply could be sitting queued rather than lost.
W3. Business impact, the real step-5 question: does Pipedrive hold ANY trace of the Ashwin reply
    (person by email, its labels, changelog, notes/activities) - by EMAIL, since the Smartlead
    lead name is 'Person-6f447c29', not 'Ashwin'.
W4. Same person-level check for the other 9 unprocessed replies, so business impact is quantified
    rather than assumed.

No writes anywhere.
"""
import json, os, re, ssl, time
from datetime import datetime, timedelta, timezone
import urllib.error, urllib.parse, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
MAKE_TOKEN = os.environ["MAKE_API_TOKEN"]
MAKE_ZONE = os.environ.get("MAKE_ZONE", "eu2")
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.now(timezone.utc)
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
RESP_SCEN = 8557478

# the 10 replies WF-2 never processed (union truth-set), oldest first
UNPROCESSED = [
    ("2026-08-04T15:10:03+00:00", "pii-67425a37@example.invalid", "Rune-Catch-alls", "Out Of Office"),
    ("2026-08-04T16:15:03+00:00", "pii-b02b50cf@example.invalid", "Mario-Valids", "Out Of Office"),
    ("2026-08-04T16:31:45+00:00", "pii-6f8f48e5@example.invalid", "Rune-Catch-alls", "(history-only)"),
    ("2026-08-04T16:38:45+00:00", "pii-135b4c7b@example.invalid", "Rune-Valids", "(history-only)"),
    ("2026-08-04T16:38:45+00:00", "pii-90ec4caf@example.invalid", "Mario-Catch-alls", "Out Of Office"),
    ("2026-08-04T16:55:41+00:00", "pii-567b1851@example.invalid", "Mario-Valids", "Interested"),
    ("2026-08-04T17:04:26+00:00", "pii-06275333@example.invalid", "Mario-Catch-alls", "Out Of Office"),
    ("2026-08-04T17:15:19+00:00", "pii-567b1851@example.invalid", "Mario-Valids", "(2nd reply)"),
    ("2026-08-04T19:10:59+00:00", "pii-7b1c0e1a@example.invalid", "Mario-Valids", "Not Interested"),
    ("2026-08-05T06:08:38+00:00", "pii-280f963f@example.invalid", "Rune-Catch-alls", "Wrong Person"),
]


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


def pd(path, params=None):
    q = dict(params or {}); q["api_token"] = PDT
    return _get(f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}",
                {"User-Agent": UA})


def mk(path, params=None):
    q = urllib.parse.urlencode(params or {}, doseq=True)
    return _get(f"https://{MAKE_ZONE}.make.com/api/v2{path}" + (f"?{q}" if q else ""),
                {"Authorization": f"Token {MAKE_TOKEN}", "User-Agent": UA})


def ts(s):
    """Pipedrive changelog returns naive UTC strings; Smartlead/Make return offset-aware.
    Normalise everything to aware-UTC so comparisons are valid."""
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


print("=" * 104)
print("W1. Make 8557478 - trigger type and full log span")
print("=" * 104)
sc = mk(f"/scenarios/{RESP_SCEN}")
s = (sc or {}).get("scenario") or {}
for k in ("id", "name", "isActive", "isPaused", "scheduling", "islinked", "usedPackages",
          "lastEdit", "hookId", "nextExec"):
    if k in s:
        print(f"  {k} = {json.dumps(s[k], default=str)[:200]}")

# NOTE: pg[limit]=100 silently returns an EMPTY list on this endpoint; 50 works. Page instead.
entries = []
offset = 0
while offset < 400:
    page = mk(f"/scenarios/{RESP_SCEN}/logs",
              {"pg[limit]": 50, "pg[sortDir]": "desc", "pg[offset]": offset})
    batch = page.get("scenarioLogs") or []
    if not batch:
        break
    entries.extend(batch)
    offset += len(batch)
    if len(batch) < 50:
        break
    time.sleep(0.2)
print(f"\n  log entries returned: {len(entries)}")
if entries:
    tss = [e.get("timestamp") for e in entries if e.get("timestamp")]
    print(f"  log span: {min(tss)} .. {max(tss)}")
    print("  most recent 10:")
    for e in entries[:10]:
        print(f"     {e.get('timestamp')}  status={e.get('status')} type={e.get('type')} "
              f"ops={e.get('operations')}")

print("\n" + "=" * 104)
print("W2. Make incomplete executions (DLQ) - anything queued/stuck?")
print("=" * 104)
for path, params in ((f"/dlqs", {"organizationId": 2262681, "pg[limit]": 50}),
                     (f"/scenarios/{RESP_SCEN}/dlqs", {"pg[limit]": 50})):
    d = mk(path, params)
    if d.get("__err"):
        print(f"  {path}: err {d.get('__err')} {d.get('__body','')[:120]}")
        continue
    items = d.get("dlqs") or d.get("data") or []
    print(f"  {path}: {len(items)} item(s)")
    for it in items[:10]:
        print("    ", json.dumps(it, default=str)[:250])

print("\n" + "=" * 104)
print("W3/W4. Pipedrive business-impact check for each unprocessed reply (by EMAIL)")
print("=" * 104)
results = []
for rts, email, camp, cat in UNPROCESSED:
    srch = pd("/persons/search", {"term": email, "fields": "email", "exact_match": "true"})
    items = ((srch or {}).get("data") or {}).get("items") or []
    if not items:
        print(f"\n  {rts}  {email:<36} {camp:<18} -> PERSON NOT IN PIPEDRIVE")
        results.append({"reply_time": rts, "email": email, "campaign": camp, "category": cat,
                        "person": None, "post_reply_changes": [], "verdict": "NO_PERSON"})
        continue
    pid = items[0]["item"]["id"]
    cl = pd(f"/persons/{pid}/changelog", {"start": 0, "limit": 100})
    rows = (cl or {}).get("data") or []
    after = []
    rt = ts(rts)
    for r in rows:
        t = ts(r.get("time") or r.get("timestamp") or r.get("log_time"))
        if t and rt and t >= rt:
            after.append({"time": t.isoformat(), "field": r.get("field_key"),
                          "new": str(r.get("new_value"))[:60],
                          "src": r.get("change_source"),
                          "ua": str(r.get("change_source_user_agent"))[:40],
                          "actor": r.get("actor_user_id")})
    # leads for this person + their labels
    lds = pd("/leads", {"limit": 100, "person_id": pid, "archived_status": "all"})
    lead_rows = (lds or {}).get("data") or []
    verdict = "TOUCHED_AFTER_REPLY" if after else "NO_CHANGE_AFTER_REPLY"
    print(f"\n  {rts}  {email:<36} {camp:<18} -> person #{pid}, "
          f"leads={len(lead_rows)}, changes_after_reply={len(after)}  [{verdict}]")
    for a in after[:6]:
        print(f"       {a['time']}  {a['field']:<22} src={a['src']:<5} ua={a['ua']:<28} -> {a['new']}")
    results.append({"reply_time": rts, "email": email, "campaign": camp, "category": cat,
                    "person_id": pid, "leads": len(lead_rows),
                    "lead_labels": [L.get("label_ids") for L in lead_rows],
                    "post_reply_changes": after, "verdict": verdict})
    time.sleep(0.15)

print("\n" + "-" * 104)
from collections import Counter
print("  verdict tally:", dict(Counter(r["verdict"] for r in results)))

with open(os.path.join(HERE, "wf1-release-evidence", "ashwin_verify_v5.json"), "w",
          encoding="utf-8") as f:
    json.dump({"make_scenario": s, "make_log_span": [min(tss), max(tss)] if entries else None,
               "impact": results}, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/ashwin_verify_v5.json")
