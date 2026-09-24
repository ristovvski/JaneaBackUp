#!/usr/bin/env python3
"""R3 - the delta digest.

The old digest counted replies from WF-2's own Shadow Log (c1_daily_reports.py:142). That measures
what WE PROCESSED, never what EXISTS - so on 2026-08-05 it printed `replies: 0` for a day that
contained a real Netflix reply, and was structurally incapable of noticing. A total outage and a
quiet day rendered identically.

This digest reports THREE numbers per campaign and makes the difference the alarm:

    Smartlead (truth)  |  WF-2 processed  |  DELTA

Design rules, each one paid for:
  * Smartlead truth comes from /campaigns/{id}/leads-statistics history[] type=="REPLY".
    NOT /campaigns/{id}/statistics.reply_time - measured 8 vs 12 (-33%) over 2026-08-03..06.
  * DELTA > 0 is an alarm, rendered as such.
  * 0 | 0 | 0 is NOT green. It is "no traffic - path unverified", because a silent pipe and a
    quiet day look identical and only one of them is fine.
  * "last real inbound webhook" excludes our own probes (Python-urllib et al). During the whole
    2026-08-05 recovery the only WF-2 executions were mine; a digest counting those would have
    reported a healthy pipe on a dead one.

READ-ONLY apart from the optional Slack post (--post).
"""
import argparse, json, os, ssl, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

SLK = os.environ["SMARTLEAD_API_KEY"]
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"
UA = "Mozilla/5.0 janea-r3-digest/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

CAMPS = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
         3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}
# a webhook whose UA looks like one of these is OURS, not Smartlead's
PROBE_UA = ("python-urllib", "python-requests", "curl/", "postman", "insomnia", "janea-")


def _get(url, headers):
    for i in range(3):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < 2:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code}
        except Exception as e:
            if i < 2:
                time.sleep(3); continue
            return {"__err": str(e)[:150]}
    return {}


def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}",
                {"User-Agent": UA})


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    return _get(f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}",
                {"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


ap = argparse.ArgumentParser()
ap.add_argument("--hours", type=int, default=24)
ap.add_argument("--post", action="store_true", help="post to the ops channel")
args = ap.parse_args()

NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(hours=args.hours)
print(f"window: {SINCE.isoformat()} .. {NOW.isoformat()}  ({args.hours}h)\n")

# ------------------------------------------------------- 1. Smartlead truth (the proven surface)
truth = {cid: [] for cid in CAMPS}
incomplete = []
for cid, label in CAMPS.items():
    skip, pages = 0, 0
    while pages < 30:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if page.get("__err"):
            incomplete.append(f"{label}: leads-statistics error {page['__err']}")
            break
        for row in (page.get("data") or []):
            for h in (row.get("history") or []):
                if str(h.get("type", "")).upper() != "REPLY":
                    continue
                t = ts(h.get("time"))
                if t and SINCE <= t <= NOW:
                    truth[cid].append({"email": row.get("to"), "time": t.isoformat(),
                                       "subject": h.get("subject")})
        pages += 1
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.15)
    else:
        incomplete.append(f"{label}: page walk hit the 30-page guard - count may be partial")

# ------------------------------------------------ 2. what WF-2 actually processed (same as before)
ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250})
execs = [e for e in (ex.get("data") or [])
         if ts(e.get("startedAt")) and ts(e["startedAt"]) >= SINCE]
processed = {cid: set() for cid in CAMPS}
last_real, last_real_ua, probe_count = None, None, 0
last_replay, last_replay_by = None, None
# widen the webhook scan past the digest window: "last real inbound" is only useful if it can
# reach back beyond a quiet day, which is exactly when it matters most
for e in (ex.get("data") or []):
    d = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
    hdrs = {}
    try:
        hdrs = rd["Webhook"][0]["data"]["main"][0][0]["json"].get("headers") or {}
    except Exception:
        pass
    ua = str(hdrs.get("user-agent") or "").lower()
    # A WF-2R replay is NOT a genuine Smartlead delivery, and it arrives over the same axios UA
    # that Smartlead itself uses - so user-agent alone cannot tell them apart. Without this check
    # the reconciler's own replays would keep "last real inbound webhook" permanently fresh while
    # Smartlead's delivery was completely dead: the exact blindness this line exists to remove.
    # Normalize stamps __reconciled/__reconciled_by for precisely this purpose.
    try:
        nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
        is_replay = nz.get("__reconciled") is True
        replay_by = nz.get("__reconciled_by")
    except Exception:
        is_replay, replay_by = False, None
    is_probe = any(p in ua for p in PROBE_UA) or is_replay
    st = ts(e.get("startedAt"))
    if is_replay and st and (last_replay is None or st > last_replay):
        last_replay, last_replay_by = st, replay_by
    if hdrs:
        if is_probe:
            probe_count += 1
        elif st and (last_real is None or st > last_real):
            last_real, last_real_ua = st, ua or "(no user-agent)"
    if st and st >= SINCE and not is_probe:
        for run in rd.get("Shadow Log") or []:
            try:
                items = run["data"]["main"][0]
            except Exception:
                continue
            for it in items or []:
                j = it.get("json") or {}
                if not str(j.get("event", "")).lower().startswith("repl"):
                    continue
                cid = j.get("campaign_id")
                if cid in processed:
                    processed[cid].add(str(j.get("lead_email") or e["id"]))
    time.sleep(0.03)

# --------------------------------------------------------------------------------- 3. render
# Compare at LEAD granularity, by set difference - not count-vs-count.
# First version compared 12 reply EVENTS against WF-2 executions deduped by email, so a lead who
# replied twice inflated the delta, and the alarm list printed every reply of an alarming campaign
# rather than the unmatched ones. It named richard.spitz as lost when execution 13143 had
# processed him. A digest that cries wolf on a handled reply is the mirror of the bug it replaces.
rows, total_t, total_p, alarms = [], 0, 0, []
for cid, label in CAMPS.items():
    t_emails = {str(r["email"]).lower() for r in truth[cid] if r.get("email")}
    p_emails = {str(e).lower() for e in processed[cid]}
    missing = sorted(t_emails - p_emails)
    tcount, pcount = len(t_emails), len(t_emails & p_emails)
    delta = len(missing)
    total_t += tcount
    total_p += pcount
    if delta:
        items = [r for r in truth[cid] if str(r.get("email", "")).lower() in set(missing)]
        alarms.append((label, delta, sorted(items, key=lambda r: r["time"])))
    rows.append((label, tcount, pcount, delta, len(truth[cid])))

hdr = f"{'campaign':<20} {'Smartlead':>10} {'WF-2':>8} {'DELTA':>8}"
print(hdr)
print("-" * len(hdr))
for label, tc, pc, d, ev in rows:
    flag = "  <<< ALARM" if d > 0 else ""
    print(f"{label:<20} {tc:>10} {pc:>8} {d:>8}{flag}   ({ev} reply events)")
print("-" * len(hdr))
print(f"{'TOTAL (leads)':<20} {total_t:>10} {total_p:>8} {total_t-total_p:>8}")
print(f"  raw reply events in Smartlead: {sum(r[4] for r in rows)}")

no_traffic = (total_t == 0 and total_p == 0)
age_min = int((NOW - last_real).total_seconds() / 60) if last_real else None
print(f"\nlast real (non-probe) inbound webhook: "
      f"{last_real.isoformat() if last_real else 'NONE in retained history'}"
      + (f"  ({age_min} min ago, UA {last_real_ua})" if last_real else ""))
print(f"last WF-2R reconciler replay: "
      f"{last_replay.isoformat() if last_replay else 'none'}"
      + (f"  (by {last_replay_by})" if last_replay else ""))
print(f"our own probe/replay executions excluded: {probe_count}")
if no_traffic:
    print("\nSTATUS: no traffic - path UNVERIFIED (this is not 'green')")
elif alarms:
    print(f"\nSTATUS: ALARM - {sum(a[1] for a in alarms)} reply(ies) exist in Smartlead that WF-2 "
          f"never processed")
else:
    print("\nSTATUS: matched - every Smartlead reply has a WF-2 execution behind it")
for w in incomplete:
    print("  INCOMPLETE SCAN:", w)

# --------------------------------------------------------------------------------- 4. slack
lines = [f"*Reply reconciliation — last {args.hours}h*  _(leads with ≥1 reply)_", "```",
         f"{'campaign':<20}{'Smartlead':>10}{'WF-2':>7}{'delta':>7}"]
for label, tc, pc, d, ev in rows:
    lines.append(f"{label:<20}{tc:>10}{pc:>7}{d:>7}" + ("   <<<" if d > 0 else ""))
lines.append(f"{'TOTAL':<20}{total_t:>10}{total_p:>7}{total_t-total_p:>7}")
lines.append("```")
if no_traffic:
    lines.append("⚪ *No traffic — reply path UNVERIFIED.* Zero replies reached Smartlead and zero "
                 "were processed. This is not a green light: a silent pipe and a quiet day look "
                 "identical from here.")
elif alarms:
    lines.append(f"🚨 *{sum(a[1] for a in alarms)} lead(s) replied in Smartlead with no WF-2 "
                 f"execution behind them.* The delta IS the alarm — these are lost unless "
                 f"recovered.")
    for label, d, items in alarms:
        for i in items[:5]:
            lines.append(f"  • {label} — {i['email']} at {i['time'][:16].replace('T', ' ')}Z")
else:
    lines.append("✅ Every reply Smartlead recorded has a WF-2 execution behind it.")
lines.append(f"_Last genuine Smartlead webhook delivery: "
             f"{last_real.strftime('%Y-%m-%d %H:%M') + 'Z' if last_real else 'none in retained '
                'history'}"
             + (f" — {age_min} min ago._" if last_real else "._"))
if last_replay:
    lines.append(f"_Last WF-2R reconciler replay: "
                 f"{last_replay.strftime('%Y-%m-%d %H:%M')}Z — counted separately, because a "
                 f"replay proves the reconciler works, not that Smartlead's webhook delivery does._")
if incomplete:
    lines.append("⚠️ _Incomplete scan: " + "; ".join(incomplete) + "_")
lines.append("_Truth counted from Smartlead `leads-statistics` history (not `statistics."
             "reply_time`, which under-reports by ~33%)._")
text = "\n".join(lines)

print("\n" + "=" * 78 + "\nSLACK TEXT\n" + "=" * 78)
print(text)
with open(os.path.join(HERE, "wf1-release-evidence", "r3_delta_digest.json"), "w",
          encoding="utf-8") as f:
    json.dump({"window_hours": args.hours, "rows": rows, "truth": truth,
               "processed": {k: sorted(v) for k, v in processed.items()},
               "last_real_webhook": last_real.isoformat() if last_real else None,
               "probe_executions": probe_count, "incomplete": incomplete,
               "slack_text": text}, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/r3_delta_digest.json")
