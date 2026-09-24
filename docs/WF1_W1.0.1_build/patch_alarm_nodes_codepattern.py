#!/usr/bin/env python3
"""Convert every remaining alarm node off the known-broken construct, in ONE deploy window.

TARGETS (1 proven broken + 5 never-run watchdogs):
  WF-2   Ops Warn Classify        <- Classify Parse        (PROVEN BROKEN, 4/4 invalid syntax)
  WF-2   Ops Warn Event Alias     <- Event Alias Watch     (never run)
  WF-2S  WF-2S Report             <- Summary               (never run)
  WF-2S  Ops Warn Mode Overdue    <- WF-2 Mode Eval        (never run)
  WF-2S  Ops Warn WF-2H Stale     <- WF-2H Watch Eval      (never run)
  WF-2R  Ops Warn WF-2S Stale     <- WF-2S Watch Eval      (never run)

METHOD - generic and non-destructive. Each upstream Code node keeps its existing logic verbatim;
it is wrapped in an IIFE so its own `return` is captured, then `alert_text` is appended to every
emitted item:

    const __items = (() => { <ORIGINAL CODE UNCHANGED> })();
    return __items.map(it => ({ json: { ...it.json, alert_text: <builder>(it.json) } }));

The Slack node then becomes `={{ $json.alert_text }}` - the shape WF-1 has always used and the
only one proven to survive the expression parser.

Nothing is rewritten by regex inside the original code, so a builder mistake cannot corrupt the
node's real logic - worst case alert_text is wrong while the workflow still behaves.
"""
import argparse, json, os, ssl, subprocess, sys, urllib.error, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
IDS = {"WF-2": "jp7rum9Z0YDJkQWv", "WF-2S": "6Y92ryBwYoy6z0Jx", "WF-2R": "U8Bb7Pdq7S6nzYPa"}

# builder bodies: plain JS, receive the item json as `j`, return a string
BUILDERS = {
    "Ops Warn Classify": r"""
  const esc = (v) => String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const n = (() => { try { return $('Normalize').item.json; } catch (e) { return {}; } })();
  const CFG = (() => { try { return $('CONFIG').item.json; } catch (e) { return {}; } })();
  const conf = (j.__confidence === undefined || j.__confidence === null) ? '?' : j.__confidence;
  const who = esc((n.lead || {}).email || '?');
  return '⚠️ WF-2: classifier fallback — routed to review ('
    + esc(CFG.forward_review_address) + ') for ' + who + ' · confidence ' + conf;
""",
    "Ops Warn Event Alias": r"""
  const esc = (v) => String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const n = (() => { try { return $('Normalize').item.json; } catch (e) { return {}; } })();
  return '⚠️ WF-2: unknown event alias ' + esc(n.event_alias || j.__alias || '?')
    + ' · normalised as ' + esc(n.event || '?') + ' · campaign ' + esc(n.campaign_name);
""",
    "WF-2S Report": r"""
  return '🔁 WF-2S replayed ' + (j.__batch ?? 0) + ' send(s)'
    + (j.__failed ? ' · ⚠️ ' + j.__failed + ' REJECTED' : '')
    + (j.__dropped ? ' · ⚠️ cap dropped ' + j.__dropped : '')
    + (j.__unverified ? ' · ' + j.__unverified + ' unverified id(s)' : '')
    + ' · considered ' + (j.__considered ?? 0) + ' · store ' + (j.__store_size ?? 0);
""",
    "Ops Warn Mode Overdue": r"""
  const CFG = (() => { try { return $('CONFIG').first().json; } catch (e) { return {}; } })();
  return '🚨 WF-2 has been in WRITE_MODE=live since ' + (j.__mode_live_since || '?')
    + ', longer than the ' + (CFG.write_mode_max_hours ?? '?')
    + 'h a live window is allowed to last. Revert to shadow or confirm the flip is permanent.';
""",
    "Ops Warn WF-2H Stale": r"""
  const CFG = (() => { try { return $('CONFIG').first().json; } catch (e) { return {}; } })();
  return '🚨 WF-2H has not succeeded for ' + (j.__wf2h_age_h ?? '?')
    + 'h (threshold ' + (CFG.wf2h_stale_hours ?? '?') + 'h). The daily digest is the only place '
    + 'some numbers surface — if it is dead, nobody is reading them.';
""",
    "Ops Warn WF-2S Stale": r"""
  const CFG = (() => { try { return $('CONFIG').first().json; } catch (e) { return {}; } })();
  return '🚨 WF-2S has not executed for ' + (j.__wf2s_age_min ?? '?')
    + ' min (threshold ' + (CFG.wf2s_stale_minutes ?? '?') + '). SENT reconciliation is the only '
    + 'source of SENT events — if it is dead, sends are going unobserved.';
""",
}
TARGETS = [
    ("WF-2", "Classify Parse", "Ops Warn Classify"),
    ("WF-2", "Event Alias Watch", "Ops Warn Event Alias"),
    ("WF-2S", "Summary", "WF-2S Report"),
    ("WF-2S", "WF-2 Mode Eval", "Ops Warn Mode Overdue"),
    ("WF-2S", "WF-2H Watch Eval", "Ops Warn WF-2H Stale"),
    ("WF-2R", "WF-2S Watch Eval", "Ops Warn WF-2S Stale"),
]


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
        raise


def wrap(original, slack_name, builder):
    return (f"// alert_text moved OUT of the Slack node's expression (see reference doc 9c):\n"
            f"// code in an expression + onError:continueRegularOutput fails silently while the\n"
            f"// execution still reports success. Original logic below is UNCHANGED, only wrapped.\n"
            f"const __items = (() => {{\n{original}\n}})();\n"
            f"const __build = (j) => {{{builder}}};\n"
            f"return (__items || []).map((it) => ({{ json: {{ ...(it.json || {{}}),\n"
            f"  alert_text: (() => {{ try {{ return __build(it.json || {{}}); }}\n"
            f"                       catch (e) {{ return '{slack_name}: alert_text build failed - '\n"
            f"                                     + String(e && e.message ? e.message : e); }} }})() }} }}));")


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

# ---- local parse check of every wrapped body before anything is sent
print("--- local syntax check of each wrapped Code node ---")
for wfk, code_name, slack_name in TARGETS:
    probe = wrap("return [{ json: { __batch: 1 } }];", slack_name, BUILDERS[slack_name])
    stub = ("const $ = () => ({ item: { json: {} }, first: () => ({ json: {} }) });\n"
            + probe.replace("return (__items", "const __r = (__items")
            + "\nconsole.log(String(__r[0].json.alert_text).slice(0, 60));")
    # written as a UTF-8 FILE, not piped: this console's codepage (cp1251) cannot encode the
    # emoji in the alarm strings, and piping silently died on it
    tmp = os.path.join(HERE, "_alarmcheck.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(stub)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {wfk}/{slack_name}: "
              f"{(p.stderr or '').strip().splitlines()[-1][:140] if p.stderr else '?'}")
        sys.exit(1)
    print(f"  [ok] {wfk}/{slack_name}  -> {(p.stdout or '').strip()[:70]}")

changes = {}
for wfk in sorted({t[0] for t in TARGETS}):
    wf = n8n(f"/api/v1/workflows/{IDS[wfk]}")
    nodes = {n["name"]: n for n in wf["nodes"]}
    local = []
    for k, code_name, slack_name in TARGETS:
        if k != wfk:
            continue
        c, s = nodes.get(code_name), nodes.get(slack_name)
        if not c or not s:
            print(f"  REFUSING: {wfk} missing {code_name!r} or {slack_name!r}")
            sys.exit(2)
        cur = str((s.get("parameters") or {}).get("text") or "")
        if cur.strip() == "={{ $json.alert_text }}" and "alert_text" in c["parameters"]["jsCode"]:
            print(f"  {wfk}/{slack_name}: already converted")
            continue
        c["parameters"]["jsCode"] = wrap(c["parameters"]["jsCode"], slack_name,
                                         BUILDERS[slack_name])
        s["parameters"]["text"] = "={{ $json.alert_text }}"
        local.append(f"{slack_name} (was {len(cur)} chars) via {code_name}")
    if local:
        changes[wfk] = (wf, local)

print("\n--- planned ---")
for wfk, (wf, local) in changes.items():
    for c in local:
        print(f"  {wfk}: {c}")
if not changes:
    print("  (nothing to do)")
    sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
problems = []
for wfk, (wf, local) in changes.items():
    wid = IDS[wfk]
    open(os.path.join(HERE, f"{wfk.lower()}_backup_before_alarmfix_{stamp}.json"), "w",
         encoding="utf-8").write(json.dumps(n8n(f"/api/v1/workflows/{wid}"), indent=2,
                                            ensure_ascii=False))
    was = wf.get("active")
    if was:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    d = stripped_keys(wf)
    if d:
        print(f"  {wfk}: stripping {d}")
    n8n(f"/api/v1/workflows/{wid}", "PUT", put_body(wf))
    if was:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    after = n8n(f"/api/v1/workflows/{wid}")
    an = {x["name"]: x for x in after["nodes"]}
    for k, code_name, slack_name in TARGETS:
        if k != wfk:
            continue
        if str(an[slack_name]["parameters"].get("text")).strip() != "={{ $json.alert_text }}":
            problems.append(f"{wfk}/{slack_name} text not converted")
        if "alert_text" not in an[code_name]["parameters"]["jsCode"]:
            problems.append(f"{wfk}/{code_name} does not emit alert_text")
    if after.get("active") is not was:
        problems.append(f"{wfk} active={after.get('active')} (was {was})")
    if len(after["nodes"]) != len(wf["nodes"]):
        problems.append(f"{wfk} node count changed")
    print(f"  {wfk}: active={after.get('active')} versionId={after.get('versionId')} "
          f"nodes={len(after['nodes'])}")

print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
