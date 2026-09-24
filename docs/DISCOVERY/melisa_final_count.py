import os, json, ssl, re
import urllib.request, urllib.parse
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
F_EVENT = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"
def pd(path, params=None):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
    with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
        return json.load(x)

log = json.load(open("melisa_apply_373_log.json", encoding="utf-8"))
CANON = "Events Visiting"
still_bad = 0
for row in log["rows"]:
    pid = row["person_id"]
    p = (pd(f"/persons/{pid}") or {}).get("data") or {}
    if not p.get(F_EVENT) or p.get(F_HYPO) != CANON:
        still_bad += 1
        print("STILL BAD:", pid, p.get(F_EVENT), p.get(F_HYPO))
print(f"\nresidual bad out of {len(log['rows'])} written: {still_bad}")
print("(+ 1 permanently excluded: John Mathew, manual review)")
