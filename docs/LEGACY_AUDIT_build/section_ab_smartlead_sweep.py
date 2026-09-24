#!/usr/bin/env python3
"""Legacy Audit — Section A+B combined Smartlead-side sweep (READ-ONLY).
One walk across all 117 historical campaigns (Smartlead is the long-memory source, Sep-2024-today).

Per campaign, pages /campaigns/{id}/leads-statistics (offset param, NOT "skip" - verified: "skip" is
rejected 400, "offset" is the real param and actually advances the page - confirmed live this run).

Produces, per campaign:
  - contacted: leads with >=1 SENT-type history entry (actual contact, not just enrollment)
  - replied:   leads with >=1 REPLY-type history entry, with full reply records for Section A's
               CRM-trace matching pass (which runs separately against a bulk Pipedrive pull)

Crash-safe: writes one JSON line per completed campaign to evidence/section_ab_raw_sweep.jsonl
immediately, and skips campaigns already present in that file on restart (idempotent re-run).
"""
import json, os, ssl, sys, time
import urllib.request, urllib.parse

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-audit/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "evidence")
OUT_PATH = os.path.join(EVID, "section_ab_raw_sweep.jsonl")


def sl(path, params=None, tries=5):
    q = dict(params or {}); q["api_key"] = SLK
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code, "__body": b}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def sweep_campaign(cid, cname):
    contacted = set()
    replies = []  # {email, time, subject, body200, history_type}
    offset = 0
    pages = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"offset": offset, "limit": 100})
        if page.get("__err"):
            return {"error": page, "pages": pages}
        data = page.get("data") or []
        pages += 1
        for row in data:
            email = (row.get("to") or "").lower()
            hist = row.get("history") or []
            if any(h.get("type") == "SENT" for h in hist):
                contacted.add(email)
            for h in hist:
                if h.get("type") == "REPLY":
                    replies.append({
                        "email": email,
                        "time": h.get("time"),
                        "subject": h.get("subject"),
                        "body200": (h.get("email_body") or "")[:200],
                    })
        if not page.get("hasMore") or not data:
            break
        offset += 100
        if pages > 500:  # safety valve, no known campaign should need this many pages
            break
    return {"contacted_count": len(contacted), "contacted_emails": sorted(contacted),
            "replies": replies, "pages": pages}


def main():
    campaigns = json.load(open(os.path.join(EVID, "step0_retention_recon.json"),
                               encoding="utf-8"))["smartlead"]["campaigns"]
    print(f"total campaigns to sweep: {len(campaigns)}")

    done_ids = set()
    if os.path.exists(OUT_PATH):
        for line in open(OUT_PATH, encoding="utf-8"):
            try:
                done_ids.add(json.loads(line)["campaign_id"])
            except Exception:
                pass
    print(f"already done (resuming, skipping): {len(done_ids)}")

    with open(OUT_PATH, "a", encoding="utf-8") as out:
        for i, c in enumerate(campaigns):
            cid = c["id"]
            if cid in done_ids:
                continue
            t0 = time.time()
            result = sweep_campaign(cid, c["name"])
            elapsed = time.time() - t0
            row = {"campaign_id": cid, "campaign_name": c["name"], "created_at": c.get("created_at"),
                   "status": c.get("status"), **result}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            n_replies = len(result.get("replies", []))
            print(f"[{i+1}/{len(campaigns)}] {cid} {c['name'][:55]:<55} "
                  f"contacted={result.get('contacted_count','?'):>5} replies={n_replies:>4} "
                  f"pages={result.get('pages','?'):>3} ({elapsed:.1f}s)", flush=True)

    print("\nSWEEP COMPLETE.")


if __name__ == "__main__":
    main()
