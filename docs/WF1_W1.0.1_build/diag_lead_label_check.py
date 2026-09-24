#!/usr/bin/env python3
"""READ-ONLY: for each person from the unprocessed-reply check, find their Pipedrive lead(s) and
report CURRENT label_ids + whether a 'responded'-family label is present (case-insensitive name
match against /leadLabels, not a guessed id). This is the correct object for Make's forward+label
action (leads carry labels, not persons)."""
import os, json, ssl
import urllib.request, urllib.parse

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
HERE = os.path.dirname(os.path.abspath(__file__))


def pd(path, params):
    q = dict(params); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
    with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
        return json.load(x)


labels = pd("/leadLabels", {}).get("data") or []
label_name = {l["id"]: l["name"] for l in labels}
resp_label_ids = {l["id"] for l in labels if "respond" in (l["name"] or "").lower()}
print("Lead labels with 'respond' in the name:", [(l["id"], l["name"]) for l in labels if l["id"] in resp_label_ids])

d = json.load(open(os.path.join(HERE, "wf1-release-evidence", "ashwin_wf2_deadwindow_sweep_v2.json"), encoding="utf-8"))
for c in d["unprocessed_checked"]:
    pid = c.get("person_id")
    if not pid:
        continue
    leads = (pd("/leads", {"person_id": pid}) or {}).get("data") or []
    print(f"\n--- {c['email']} (person {pid}) | reply {c['reply_time']} --- leads: {len(leads)}")
    for ld in leads:
        lids = ld.get("label_ids") or []
        names = [label_name.get(i, i) for i in lids]
        has_responded = bool(resp_label_ids & set(lids))
        print(f"   lead {ld['id']} '{ld.get('title','')[:60]}' labels={names} "
              f"HAS_RESPONDED_LABEL={has_responded} archived={ld.get('is_archived')} "
              f"update_time={ld.get('update_time')}")
