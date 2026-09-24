"""WF-2 shadow diff harness (Phase D, item 4). Read-only.

Compares, for a time window:
  1. WHAT WF-2 INTENDED  - Shadow Log entries from WF-2's own executions (n8n API)
  2. WHAT MAKE ACTUALLY DID - Make scenario execution logs (eu2)
  3. PIPEDRIVE STATE     - the leads/persons involved
  4. SMARTLEAD CATEGORIES - the lead's category

ALIGNMENT IS BY LEAD, never by event type. Make's reply scenario triggers on
LEAD_CATEGORY_UPDATED while WF-2 triggers on raw EMAIL_REPLIED, so the same business fact arrives
as different events at different times. Aligning by event type would manufacture discrepancies.

Key: (campaign_id, lead_email) - present in both systems and stable across the two event shapes.

Lines whose outcome depends on the classifier are marked **DEGRADED**, not "discrepancy":
classify_enabled is false for the whole shadow phase (the Anthropic credential is deferred), so a
missing category writeback or a fail-open forward is EXPECTED, not a defect.

Usage:
  python wf2_diff_harness.py --hours 24 --out wf1-release-evidence/wf2-shadow-diff-<date>.md
Secrets come from the environment (never arguments):
  N8N_BASE_URL, N8N_API_KEY, PIPEDRIVE_API_TOKEN, SMARTLEAD_API_KEY, MAKE_API_TOKEN, MAKE_ZONE
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

WF2_NAME = "WF-2 Smartlead Receiver"
MAKE_SCENARIOS = {"8557031": "SENT -> create lead", "8557478": "REPLIED -> responded label"}
CLASSIFY_DEPENDENT = {"SL Category", "SL Forward Email", "SL Unsubscribe"}


def get(url, headers=None, timeout=90):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def try_get(url, headers=None):
    """Returns (data, error). A section that cannot be read is reported UNAVAILABLE, never faked."""
    try:
        return get(url, headers), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:                                        # noqa: BLE001
        return None, str(e)[:80]


# ---------------------------------------------------------------- 1. WF-2 intent
def wf2_executions(base, key, since):
    hdr = {"X-N8N-API-KEY": key}
    wfs = get(f"{base}/api/v1/workflows?limit=100", hdr)["data"]
    wf = next((w for w in wfs if w["name"] == WF2_NAME), None)
    if not wf:
        return None, [], "WF-2 is not deployed in this instance"
    out, cursor = [], None
    while True:
        u = f"{base}/api/v1/executions?workflowId={wf['id']}&limit=100&includeData=true"
        if cursor:
            u += f"&cursor={urllib.parse.quote(cursor)}"
        page = get(u, hdr)
        for ex in page.get("data", []):
            if (ex.get("startedAt") or "") < since:
                return wf, out, None
            out.append(ex)
        cursor = page.get("nextCursor")
        if not cursor:
            return wf, out, None


def intents_from(execs):
    """Shadow Log rows + per-execution facts, keyed by (campaign_id, email)."""
    rows, warns, classify_calls, links = defaultdict(list), Counter(), 0, []
    sources = {}          # F5: how each lead's category was decided
    for ex in execs:
        rd = ((ex.get("data") or {}).get("resultData") or {})
        run = rd.get("runData") or {}
        for name in run:
            if name.startswith("Ops Warn"):
                warns[name] += 1
            if name == "LLM Classify":
                classify_calls += 1
        for entry in run.get("Shadow Log", []):
            for block in (entry.get("data") or {}).get("main") or []:
                for item in block or []:
                    j = item.get("json") or {}
                    key = (str(j.get("campaign_id")), str(j.get("lead_email") or "").lower())
                    rows[key].append({"node": j.get("node"), "method": j.get("method"),
                                      "url": j.get("url_template"), "body": j.get("body"),
                                      "at": j.get("recorded_at"), "exec": ex.get("id")})
        # F5: capture how the category was decided, so classifier-dependent rows are only called
        # DEGRADED when they really are. With reply_category present the gating is REAL.
        for entry in run.get("Classify Parse", []):
            for block in (entry.get("data") or {}).get("main") or []:
                for item in block or []:
                    j = item.get("json") or {}
                    nz = None
                    for ne in run.get("Normalize", []):
                        for nb in (ne.get("data") or {}).get("main") or []:
                            for ni in nb or []:
                                nz = ni.get("json") or {}
                    key = (str((nz or {}).get("campaign_id")),
                           str(((nz or {}).get("lead") or {}).get("email") or "").lower())
                    sources[key] = {"source": j.get("__category_source"),
                                    "category": j.get("__category"),
                                    "ok": j.get("__classify_ok"),
                                    "native": (nz or {}).get("reply_category")}
        # link-form check: does the payload's own app_url match what we would construct?
        for entry in run.get("Normalize", []):
            for block in (entry.get("data") or {}).get("main") or []:
                for item in block or []:
                    j = item.get("json") or {}
                    if j.get("sl_app_url") or j.get("sl_lead_map_id"):
                        links.append({"given": j.get("sl_app_url"),
                                      "map_id": j.get("sl_lead_map_id"),
                                      "email": (j.get("lead") or {}).get("email")})
    return rows, warns, classify_calls, links, sources


# ---------------------------------------------------------------- 2. Make actual
def make_activity(zone, token, since):
    hdr = {"Authorization": f"Token {token}"}
    out, errors = {}, {}
    for sid, label in MAKE_SCENARIOS.items():
        # pg[limit] above ~10 returns empty on this tenant - paginate small
        data, err = try_get(f"https://{zone}.make.com/api/v2/scenarios/{sid}/logs?pg%5Blimit%5D=10", hdr)
        if err:
            errors[label] = err
            continue
        rows = [r for r in (data.get("scenarioLogs") or []) if (r.get("timestamp") or "") >= since]
        out[label] = rows
    return out, errors


# ---------------------------------------------------------------- 3/4. state
def pipedrive_lead_state(token, email):
    q = urllib.parse.quote(email)
    d, err = try_get("https://api.pipedrive.com/api/v2/persons/search"
                     f"?api_token={token}&term={q}&fields=email&exact_match=true&limit=5")
    if err or not d:
        return {"error": err or "no data"}
    items = ((d.get("data") or {}).get("items") or [])
    if not items:
        return {"person": None}
    pid = items[0]["item"]["id"]
    leads, err2 = try_get(f"https://api.pipedrive.com/v1/leads?api_token={token}"
                          f"&limit=100&archived_status=all&person_id={pid}")
    return {"person": pid,
            "leads": [{"id": x.get("id"), "title": x.get("title"), "labels": x.get("label_ids")}
                      for x in ((leads or {}).get("data") or [])]}


def sl_category(key, campaign_id, email):
    d, err = try_get(f"https://server.smartlead.ai/api/v1/leads?api_key={key}"
                     f"&email={urllib.parse.quote(email)}")
    if err or not d:
        return {"error": err or "no data"}
    for c in d.get("lead_campaign_data") or []:
        if str(c.get("campaign_id")) == str(campaign_id):
            return {"category": (c.get("category") or {}).get("name") if isinstance(c.get("category"), dict)
                    else c.get("category"), "status": c.get("status")}
    return {"category": None}


# ---------------------------------------------------------------- report
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    need = ["N8N_BASE_URL", "N8N_API_KEY", "PIPEDRIVE_API_TOKEN", "SMARTLEAD_API_KEY"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        print(f"missing env: {', '.join(missing)}", file=sys.stderr)
        return 2
    base = os.environ["N8N_BASE_URL"].rstrip("/")
    since = (datetime.now(timezone.utc) - timedelta(hours=a.hours)).isoformat()

    wf, execs, err = wf2_executions(base, os.environ["N8N_API_KEY"], since)
    L = [f"# WF-2 shadow diff - last {a.hours}h",
         f"\nWindow start (UTC): `{since}`\n"]
    if err:
        L += [f"**{err}** - nothing to diff yet.\n"]
        a.out.write_text("\n".join(L), encoding="utf-8")
        print("\n".join(L))
        return 0

    rows, warns, classify_calls, links, sources = intents_from(execs)
    L += [f"WF-2 executions in window: **{len(execs)}**",
          f"Leads with intended actions: **{len(rows)}**",
          f"LLM Classify invocations: **{classify_calls}** "
          f"({'expected 0 - classify_enabled=false' if classify_calls == 0 else 'UNEXPECTED while classify_enabled=false'})",
          ""]

    L += ["## Ops warnings", ""]
    if not warns:
        L += ["none", ""]
    else:
        L += ["| warn | count |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in sorted(warns.items(), key=lambda x: -x[1])]
        L += ["", "`Ops Warn Unknown Inbox` is the signal for the `from_email` question: a non-zero "
              "count means real replies are not carrying our sending inbox, and the campaign-based "
              "fallback resolver should be wired.", ""]

    L += ["## Smartlead link form (given vs constructed)", ""]
    if not links:
        L += ["no link data observed yet", ""]
    else:
        mism = [x for x in links
                if x["given"] and x["map_id"]
                and x["given"] != f"https://app.smartlead.ai/app/master-inbox?leadMap={x['map_id']}"]
        L += [f"observed: **{len(links)}** · payload-supplied links: "
              f"**{sum(1 for x in links if x['given'])}** · form mismatches: **{len(mism)}**", ""]
        for x in mism[:10]:
            L += [f"- `{x['email']}` given `{x['given']}` vs constructed leadMap=`{x['map_id']}`"]
        L += [""]

    mk, mk_err = ({}, {})
    if os.environ.get("MAKE_API_TOKEN"):
        mk, mk_err = make_activity(os.environ.get("MAKE_ZONE", "eu2"),
                                   os.environ["MAKE_API_TOKEN"], since)
    L += ["## Make (the incumbent) in the same window", ""]
    for label, rws in mk.items():
        L += [f"- {label}: **{len(rws)}** runs"]
    for label, e in mk_err.items():
        L += [f"- {label}: **UNAVAILABLE** ({e}) - not treated as zero activity"]
    if not mk and not mk_err:
        L += ["MAKE_API_TOKEN not set - section skipped"]
    L += [""]

    L += ["## Per-lead comparison", "",
          "| campaign | lead | WF-2 intended | Pipedrive now | SL category | gating |",
          "|---|---|---|---|---|---|"]
    pd_tok, sl_key = os.environ["PIPEDRIVE_API_TOKEN"], os.environ["SMARTLEAD_API_KEY"]
    for (camp, email), acts in sorted(rows.items()):
        if not email:
            continue
        state = pipedrive_lead_state(pd_tok, email)
        cat = sl_category(sl_key, camp, email)
        nodes = sorted({x["node"] or "?" for x in acts})
        dep = [n for n in nodes if any(n.startswith(c) for c in CLASSIFY_DEPENDENT)]
        src = sources.get((camp, email), {})
        if not dep:
            verdict = "compare"
        elif src.get("source") == "smartlead-native" and src.get("ok"):
            verdict = f"native-gated ({src.get('category')})"
        else:
            verdict = "**DEGRADED** (no category available)"
        leads = ", ".join(str(x["id"])[:8] for x in (state.get("leads") or [])) or "-"
        L += [f"| {camp} | {email} | {'; '.join(nodes)} | person={state.get('person')} leads={leads} "
              f"| {cat.get('category')} | {verdict} |"]
    L += ["", "`WF-2 intended` lists Shadow Log entries only: in shadow mode WF-2 writes NOTHING, so "
          "`Pipedrive now` reflects Make plus any cohabiting Zap - that is the baseline being compared, "
          "not WF-2's output.", ""]

    a.out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:40]))
    print(f"\n-> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
