import os, json, ssl, random
import urllib.request, urllib.parse
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
F_EVENT = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"
def pd(path):
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?api_token={PDT}"
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
    with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
        return json.load(x)

log = json.load(open("melisa_apply_373_log.json", encoding="utf-8"))
written = [r for r in log["rows"] if r.get("status") == "written"]
print(f"total written rows in log: {len(written)}")
random.seed(42)
sample = random.sample(written, min(25, len(written)))
ok = mismatch = 0
for row in sample:
    pid = row["person_id"]
    p = (pd(f"/persons/{pid}") or {}).get("data") or {}
    actual_event = p.get(F_EVENT)
    actual_hypo = p.get(F_HYPO)
    exp = row["intended"]
    exp_event = exp.get(F_EVENT, row["before"]["event_name"])
    exp_hypo = exp.get(F_HYPO, row["before"]["hypothesis"])
    match = (actual_event == exp_event) and (actual_hypo == exp_hypo)
    print(f"  person {pid}: event={actual_event!r} (want {exp_event!r}) hypo={actual_hypo!r} (want {exp_hypo!r}) -> {'OK' if match else 'MISMATCH'}")
    ok += match
    mismatch += not match
print(f"\nread-back sample: {ok} OK / {mismatch} MISMATCH out of {len(sample)}")
