"""
116 Amsterdam, rescoped (Nik, 2026-08-18): for the 41 reply_dnc rows with an email, probe
SMARTLEAD (not HeyReach -- these are email-sourced) for their reply threads. Explicit opt-out
language -> candidate for label re-add + entry_type upgrade to explicit_opt_out.

Read-only recon. Produces an artifact of the proposed re-add set FIRST (per Nik's Section 9f.2
pre-fire-post convention) -- this script does NOT write to the registry or touch any Pipedrive
label. That's a deliberate second step once the artifact is reviewed.

Shape chain verified live 2026-08-18:
  GET /leads?email=X (global) -> {id, lead_campaign_data: [{campaign_id, last_reply_at, ...}]}
  GET /campaigns/{cid}/leads/{lead_id}/message-history -> {history: [{type, email_body, ...}]}
"""
import os
import re
import json
import time
import requests

BASE = "https://server.smartlead.ai/api/v1"
UA = {"User-Agent": "Mozilla/5.0 janea-recon/1.0"}
FIXTURE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                             "reply_dnc_116_pending_heyreach_reclassification.json")

EXPLICIT_OPT_OUT_PATTERNS = [
    r"\bdo\s*not\s*contact\b", r"\bdon.?t\s*contact\b", r"\bstop\s*(contacting|emailing|messaging)\b",
    r"\bunsubscribe\b", r"\bremove\s*me\b", r"\btake\s*me\s*off\b", r"\bno\s*longer\s*(wish|want)\b",
    r"\bplease\s*stop\b", r"\bblock(ed)?\s*me\b", r"\bopt.?out\b", r"\bdo\s*not\s*(email|reach\s*out)\b",
]


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def classify_history(history):
    correspondent_texts = [h.get("email_body", "") or "" for h in history if h.get("type") == "REPLY"]
    joined = re.sub(r"<[^>]+>", " ", "\n".join(correspondent_texts)).lower()
    for pat in EXPLICIT_OPT_OUT_PATTERNS:
        if re.search(pat, joined, re.IGNORECASE):
            return True, pat, joined[:400]
    return False, None, joined[:400]


def main():
    load_env()
    key = os.environ["SMARTLEAD_API_KEY"]

    with open(FIXTURE_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    targets = [r for r in rows if r.get("email_lc")]
    print(f"{len(targets)} rows with an email to probe.")

    results = {"explicit_opt_out": [], "no_opt_out_found": [], "no_smartlead_lead": [], "no_reply_recorded": []}
    for row in targets:
        email = row["email_lc"]
        r = requests.get(f"{BASE}/leads", params={"api_key": key, "email": email}, headers=UA, timeout=30)
        lead = r.json()
        if not lead or not lead.get("id"):
            results["no_smartlead_lead"].append({"identity_key": row["identity_key"], "full_name": row["full_name"], "email": email})
            time.sleep(0.3)
            continue

        campaigns = lead.get("lead_campaign_data") or []
        found_reply = False
        opt_out_hit = None
        for camp in campaigns:
            if not camp.get("last_reply_at"):
                continue
            found_reply = True
            cid = camp["campaign_id"]
            rh = requests.get(f"{BASE}/campaigns/{cid}/leads/{lead['id']}/message-history",
                               params={"api_key": key}, headers=UA, timeout=30)
            if rh.status_code != 200:
                continue
            history = rh.json().get("history", [])
            is_opt_out, pattern, sample = classify_history(history)
            if is_opt_out:
                opt_out_hit = {"identity_key": row["identity_key"], "full_name": row["full_name"],
                                "pipedrive_person_id": row.get("pipedrive_person_id"), "email": email,
                                "campaign_id": cid, "campaign_name": camp.get("campaign_name"),
                                "matched_pattern": pattern, "sample_text": sample}
                break
            time.sleep(0.3)

        if opt_out_hit:
            results["explicit_opt_out"].append(opt_out_hit)
        elif found_reply:
            results["no_opt_out_found"].append({"identity_key": row["identity_key"], "full_name": row["full_name"], "email": email})
        else:
            results["no_reply_recorded"].append({"identity_key": row["identity_key"], "full_name": row["full_name"],
                                                    "email": email, "campaigns": [c.get("campaign_name") for c in campaigns]})
        time.sleep(0.3)

    print(f"\n=== RESULTS (of {len(targets)}) ===")
    print(f"explicit_opt_out (RE-ADD candidates): {len(results['explicit_opt_out'])}")
    print(f"no_opt_out_found (has a recorded reply, no opt-out language): {len(results['no_opt_out_found'])}")
    print(f"no_reply_recorded (has a Smartlead lead, but no reply recorded on any campaign): {len(results['no_reply_recorded'])}")
    print(f"no_smartlead_lead (email not found in Smartlead at all): {len(results['no_smartlead_lead'])}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                             "amsterdam_41_smartlead_reclassification_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print(f"\nFull result written to {out_path}")

    if results["explicit_opt_out"]:
        print("\nRE-ADD candidates:")
        for e in results["explicit_opt_out"]:
            print(f"  - {e['full_name']} ({e['identity_key']}): /{e['matched_pattern']}/ in \"{e['campaign_name']}\"")
            print(f"      \"{e['sample_text'][:150]}\"")


if __name__ == "__main__":
    main()
