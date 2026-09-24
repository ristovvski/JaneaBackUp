#!/usr/bin/env python3
"""Watch BOTH live receivers: WF-2 (Smartlead SENT) and WF-1 (LinkedIn replies, campaigns resumed).

WF-2 / W1.0.18 wire proof - every SENT execution must show:
    __lead_candidates_read >= 1   and   __lead_read_errors == 0

WF-1 / gate twin wire proof - the delivery registry went 50 -> 0, so the next reply for any of those
leads must ALERT (not be suppressed), the post must land in the TEAM channel, and only then may the
registry claim it. Reports the permalink of the first team-channel WF-1 alert - described exactly as
"first WF-2/WF-1 reply alert in the team channel", never as the channel's first ever message.

n8n API only, and polled gently (90s): the same key is shared with the auditor and DNC sessions, and
n8n has been returning 401 on WF-2 WRITES while reads succeed. This watcher only reads.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF1 = "jp7rum9Z0YDJkQWv", "2jdjKM2NJr473GdA"
TEAM, OPS = "C07LTD8UT70", "C0B8GCVNR5W"
OUT = os.path.join(HERE, "wf1-release-evidence", "wave_watch.json")
LOG = os.path.join(HERE, "wf1-release-evidence", "wave_watch.log")
MINUTES = int(os.environ.get("WATCH_MIN", "240"))
START = datetime.now(timezone.utc)
DEADLINE = START + timedelta(minutes=MINUTES)


def say(m):
    line = f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        say(f"  read failed (NOT an empty result): {str(e)[:110]}")
        return None


def nd(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


say(f"=== wave watch {MINUTES} min from {START.isoformat()} (WF-2 + WF-1) ===")
seen, rows, reds = set(), [], []
first_team_permalink = None

while datetime.now(timezone.utc) < DEADLINE:
    for wid, tag in ((WF2, "WF-2"), (WF1, "WF-1")):
        ex = n8n("/api/v1/executions", {"workflowId": wid, "limit": 40})
        for e in (ex or {}).get("data") or []:
            if e["id"] in seen:
                continue
            try:
                t = datetime.fromisoformat(str(e.get("startedAt")).replace("Z", "+00:00"))
            except Exception:
                continue
            if t < START:
                seen.add(e["id"])
                continue
            det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
            if det is None:
                continue                    # retry next cycle, do not mark seen
            seen.add(e["id"])
            rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
            bad, r = [], {"wf": tag, "exec": e["id"], "at": e.get("startedAt"),
                          "status": e.get("status")}
            if e.get("status") != "success":
                bad.append(f"status={e.get('status')}")

            if tag == "WF-2":
                sel = next((s for s in ("Lead Select", "Lead Resolve", "B Lead Select",
                                        "U Lead Select") if s in rd), None)
                if not sel:
                    continue
                r.update(event=nd(rd, "Normalize", "event"), select=sel,
                         cands_read=nd(rd, sel, "__lead_candidates_read"),
                         read_errors=nd(rd, sel, "__lead_read_errors"),
                         saturated=nd(rd, sel, "__leads_page_saturated"),
                         lead_id=nd(rd, sel, "__lead_id"),
                         created=("Lead Create" in rd))
                if r["cands_read"] in (None, 0):
                    bad.append(f"cands_read={r['cands_read']}")
                if r["read_errors"]:
                    bad.append(f"read_errors={r['read_errors']}")
                if r["saturated"] is True:
                    bad.append("SATURATED")
                if r["created"] and (r["saturated"] is True or r["read_errors"]):
                    bad.append("CREATED A LEAD WHILE BLIND")
                say(f"  [{'RED ' if bad else 'ok  '}] {tag} {r['exec']} {r['event']} via {sel}: "
                    f"cands={r['cands_read']} errs={r['read_errors']} sat={r['saturated']} "
                    f"lead={str(r['lead_id'])[:8]} created={r['created']}"
                    + (f"  <- {', '.join(bad)}" if bad else ""))
            else:
                if "M7 Alert Gate" not in rd and "M7 Critical Slack" not in rd:
                    continue
                slack = rd.get("M7 Critical Slack")
                j = {}
                if slack:
                    try:
                        j = slack[0]["data"]["main"][0][0]["json"]
                    except Exception:
                        j = {}
                r.update(should=nd(rd, "M7 Alert Gate", "__should_alert"),
                         reason=nd(rd, "M7 Alert Gate", "__alert_reason"),
                         key=nd(rd, "M7 Alert Gate", "__alert_key"),
                         ok=j.get("ok"), channel=j.get("channel"),
                         ts=(j.get("message") or {}).get("ts"))
                if r["should"] is True and not slack:
                    bad.append("gate said alert but the Slack node never ran")
                if slack and r["ok"] is not True:
                    bad.append(f"post failed ok={r['ok']}")
                if r["ok"] is True and r["channel"] == OPS:
                    bad.append("alert went to OPS, not the team channel")
                if r["ok"] is True and r["channel"] == TEAM and r["ts"] and not first_team_permalink:
                    first_team_permalink = (f"https://janea.slack.com/archives/{TEAM}/"
                                            f"p{str(r['ts']).replace('.', '')}")
                    say(f"  >>> FIRST WF-1 REPLY ALERT IN THE TEAM CHANNEL: {first_team_permalink}")
                say(f"  [{'RED ' if bad else 'ok  '}] {tag} {r['exec']}: should={r['should']} "
                    f"reason={r['reason']!r} ok={r['ok']} ch={r['channel']} key={r['key']}"
                    + (f"  <- {', '.join(bad)}" if bad else ""))
            rows.append(r)
            if bad:
                reds.append({**r, "why": bad})
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump({"started": START.isoformat(), "rows": rows, "reds": reds,
                           "first_team_permalink": first_team_permalink,
                           "last_poll": datetime.now(timezone.utc).isoformat()},
                          f, indent=2, ensure_ascii=False, default=str)
    time.sleep(90)

sent = [r for r in rows if r.get("wf") == "WF-2" and r.get("event") == "SENT"]
wf1 = [r for r in rows if r.get("wf") == "WF-1"]
say("\n=== WATCH COMPLETE ===")
say(f"WF-2 rows {len([r for r in rows if r['wf'] == 'WF-2'])} (SENT {len(sent)})  "
    f"WF-1 rows {len(wf1)}  REDs {len(reds)}")
say(f"first team-channel WF-1 alert: {first_team_permalink or 'NONE OBSERVED'}")
if not rows:
    say("NO TRAFFIC AT ALL - not a pass; both fixes remain statics-only on the wire.")
elif reds:
    say("RED - see above")
else:
    say("PASS for everything observed (absence of traffic is never a pass)")
sys.exit(1 if (reds or not rows) else 0)
