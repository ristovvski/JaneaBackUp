"""
Fast-follow (mandatory, per Nik 2026-08-14): reclassify the 116 reply_dnc rows using HeyReach's
own conversation data. For each of the 116 (identified by linkedin_url_norm), fetch their HeyReach
conversation (via /inbox/GetConversationsV2, which returns messages inline -- same
"verify shapes before fixtures" discipline, no separate per-lead message endpoint needed) and scan
CORRESPONDENT-sent messages for explicit "do not contact / stop / unsubscribe / remove me" language.

Read-only recon pass -- this script only CLASSIFIES and REPORTS. It does not write to the registry
or touch any Pipedrive label; that's a deliberate second step once the classification is reviewed.
"""
import os
import re
import json
import requests

HEADERS = None
BASE = "https://api.heyreach.io/api/public"

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                             "reply_dnc_116_pending_heyreach_reclassification.json")

EXPLICIT_OPT_OUT_PATTERNS = [
    r"\bdo\s*not\s*contact\b", r"\bdon.?t\s*contact\b", r"\bstop\s*(contacting|emailing|messaging)\b",
    r"\bunsubscribe\b", r"\bremove\s*me\b", r"\btake\s*me\s*off\b", r"\bno\s*longer\s*(wish|want)\b",
    r"\bplease\s*stop\b", r"\bnot\s*interested.{0,20}(stop|remove|contact)\b",
    r"\bblock(ed)?\s*me\b", r"\bopt.?out\b", r"\bdo\s*not\s*reach\s*out\b",
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


def fetch_all_conversations():
    conversations = []
    offset = 0
    limit = 100
    while True:
        r = requests.post(f"{BASE}/inbox/GetConversationsV2", headers=HEADERS,
                           json={"limit": limit, "offset": offset}, timeout=30)
        d = r.json()
        items = d.get("items", [])
        if not items:
            break
        conversations.extend(items)
        offset += limit
        if offset >= d.get("totalCount", 0):
            break
    return conversations


def norm_profile_url(url):
    if not url:
        return None
    u = url.strip().lower().rstrip("/")
    m = re.search(r"/in/([^/?#]+)", u)
    return f"https://www.linkedin.com/in/{m.group(1)}" if m else None


def classify_messages(messages):
    correspondent_texts = [m.get("body", "") or "" for m in messages if m.get("sender") == "CORRESPONDENT"]
    joined = "\n".join(correspondent_texts).lower()
    for pat in EXPLICIT_OPT_OUT_PATTERNS:
        if re.search(pat, joined, re.IGNORECASE):
            return True, pat, joined[:300]
    return False, None, joined[:300]


def main():
    load_env()
    global HEADERS
    HEADERS = {"X-API-KEY": os.environ["HEYREACH_API_KEY"], "Content-Type": "application/json"}

    with open(FIXTURE_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    print(f"Loaded {len(rows)} reply_dnc rows to reclassify.")

    print("Fetching all HeyReach conversations (paginated)...")
    conversations = fetch_all_conversations()
    print(f"  {len(conversations)} conversations fetched.")

    by_profile = {}
    for c in conversations:
        prof = norm_profile_url((c.get("correspondentProfile") or {}).get("profileUrl"))
        if prof:
            by_profile[prof] = c

    results = {"explicit_opt_out": [], "no_opt_out_language": [], "no_conversation_found": []}
    for row in rows:
        target = norm_profile_url(row.get("linkedin_url_norm"))
        conv = by_profile.get(target) if target else None
        if not conv:
            results["no_conversation_found"].append({
                "identity_key": row["identity_key"], "full_name": row["full_name"],
                "linkedin_url_norm": row.get("linkedin_url_norm"),
            })
            continue
        is_opt_out, pattern, sample = classify_messages(conv.get("messages", []))
        entry = {
            "identity_key": row["identity_key"], "full_name": row["full_name"],
            "pipedrive_person_id": row.get("pipedrive_person_id"),
            "conversation_id": conv["id"], "matched_pattern": pattern, "sample_text": sample,
        }
        (results["explicit_opt_out"] if is_opt_out else results["no_opt_out_language"]).append(entry)

    print(f"\n=== RESULTS ===")
    print(f"explicit_opt_out: {len(results['explicit_opt_out'])}")
    print(f"no_opt_out_language (has a HeyReach conversation, no opt-out phrasing found): "
          f"{len(results['no_opt_out_language'])}")
    print(f"no_conversation_found (no HeyReach conversation at all for this person): "
          f"{len(results['no_conversation_found'])}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                             "reply_dnc_116_heyreach_reclassification_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print(f"\nFull classification written to {out_path}")

    if results["explicit_opt_out"]:
        print("\nExplicit opt-out matches:")
        for e in results["explicit_opt_out"]:
            print(f"  - {e['full_name']} ({e['identity_key']}): matched /{e['matched_pattern']}/")
            print(f"      \"{e['sample_text'][:150]}\"")


if __name__ == "__main__":
    main()
