import json, os, ssl, random
import urllib.request, urllib.parse

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-forensics/1.0"

def pd(path):
    q = urllib.parse.urlencode({"api_token": PDT})
    sep = "&" if "?" in path else "?"
    url = f"https://janeasystems.pipedrive.com/api/v1{path}{sep}{q}"
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
        return json.load(x)

d = json.load(open("WF1_W1.0.1_build/wf1-release-evidence/london_backfill_live_log.json", encoding="utf-8"))
rows = [r for r in d["rows"] if r.get("action") == "created"]
priority = [r for r in rows if r["treatment"] != "standard_cold_backfill"]
standard = [r for r in rows if r["treatment"] == "standard_cold_backfill"]
random.seed(20260811)
sample = priority + random.sample(standard, 6)
print(f"verifying {len(sample)} rows ({len(priority)} priority + 6 standard sample)\n")

ok = bad = 0
for r in sample:
    email, treatment = r["email"], r["treatment"]
    p = pd(f"/persons/{r['person_id']}").get("data") or {}
    l = pd(f"/leads/{r['lead_id']}").get("data") or {}
    p_email = (p.get("primary_email") or "").lower()
    labels = l.get("label_ids") or []
    row_ok = (p_email == email.lower()) and (l.get("title", "").endswith(email.split("@")[0]) or email.split("@")[0] in l.get("title",""))
    tag = "OK  " if row_ok else "MISMATCH"
    if row_ok: ok += 1
    else: bad += 1
    print(f"{tag} {email:<38} treatment={treatment:<45} person_email_match={p_email==email.lower()} labels={len(labels)}")
    if r.get("activity_id"):
        a = pd(f"/activities/{r['activity_id']}").get("data") or {}
        print(f"       activity: lead_id={a.get('lead_id')} done={a.get('done')} note_starts={str(a.get('note') or '')[:60]!r}")

print(f"\n{ok} ok / {bad} mismatch out of {len(sample)}")
