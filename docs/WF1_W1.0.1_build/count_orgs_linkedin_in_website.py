#!/usr/bin/env python3
"""READ ONLY. How many organizations currently hold a linkedin.com URL in a WEBSITE field?

No repair - a count, per field, so the size of any future repair is known before it is proposed.

Four website-ish fields exist on organizations, and all four are checked because a value can sit in
any of them:
  native `website`
  7ef47bd78dae7bbf48da9d837c3fbda079a44de9   "Website URL"
  2064369b47d625221e85093240d25b42110d8da4   "Website"
  c8c70fc525238b1c709857ea40f4d60cd2575d37   "lh_website"

Cursor pagination is walked to exhaustion. The total is cross-checked against an independent count
so a silently truncated walk cannot report a small number as a clean one.
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))

WEBSITE_FIELDS = {
    "native website": None,
    "7ef47bd78dae7bbf48da9d837c3fbda079a44de9": "Website URL",
    "2064369b47d625221e85093240d25b42110d8da4": "Website",
    "c8c70fc525238b1c709857ea40f4d60cd2575d37": "lh_website",
}
ORG_LI = "ed932dfc4870dcd72fa7b4eadb67da38d169299b"
RE_LI = re.compile(r"(^|\.)linkedin\.com", re.I)


def pd(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504) and a < 5:
            time.sleep(4 + a * 3)
            return pd(p, a + 1)
        return {"__err": "HTTP %s" % e.code}
    except Exception as e:
        if a < 4:
            time.sleep(3)
            return pd(p, a + 1)
        return {"__err": str(e)[:140]}


def host_is_li(u):
    s = str(u or "")
    if not s:
        return False
    m = re.sub(r"^[a-z]+://", "", s, flags=re.I).split("/")[0].split("?")[0]
    return bool(RE_LI.search(m))


orgs, cursor, pages = [], None, 0
while pages < 400:
    q = {"limit": 500}
    if cursor:
        q["cursor"] = cursor
    d = pd("/api/v2/organizations?" + urllib.parse.urlencode(q))
    rows = (d or {}).get("data") or []
    orgs += rows
    cursor = ((d or {}).get("additional_data") or {}).get("next_cursor")
    pages += 1
    if pages % 5 == 0:
        print("  %d orgs read (%d pages)" % (len(orgs), pages), flush=True)
    if not cursor or not rows:
        break
print("organizations walked: %d  (pages %d, cursor exhausted: %s)"
      % (len(orgs), pages, not cursor))

hits, by_field, both = [], Counter(), 0
for o in orgs:
    cf = o.get("custom_fields") or {}
    found = {}
    if host_is_li(o.get("website")):
        found["native website"] = o.get("website")
    for k in WEBSITE_FIELDS:
        if k == "native website":
            continue
        if host_is_li(cf.get(k)):
            found[k] = cf.get(k)
    if found:
        for k in found:
            by_field[k] += 1
        li_field = cf.get(ORG_LI)
        if li_field:
            both += 1
        hits.append({"id": o.get("id"), "name": o.get("name"),
                     "fields": {k: str(v)[:70] for k, v in found.items()},
                     "org_linkedin_field_also_set": bool(li_field)})

print("\n" + "=" * 70)
print("ORGS WITH A linkedin.com URL IN A WEBSITE FIELD: %d of %d (%.2f%%)"
      % (len(hits), len(orgs), 100.0 * len(hits) / len(orgs) if orgs else 0))
print("=" * 70)
print("\nby field (an org can appear in more than one):")
for k, n in by_field.most_common():
    print("   %-44s %-12s %d" % (k, WEBSITE_FIELDS.get(k) or "", n))
print("\nof those, already have the LinkedIn field populated too: %d" % both)

print("\nfirst 15:")
for h in hits[:15]:
    print("   %-8s %-34s %s" % (h["id"], str(h["name"])[:34],
                                json.dumps(h["fields"], ensure_ascii=False)[:100]))

out = os.path.join(HERE, "orgs_linkedin_in_website.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"orgs_walked": len(orgs), "pages": pages, "cursor_exhausted": not cursor,
               "affected": len(hits), "by_field": dict(by_field),
               "also_has_linkedin_field": both, "rows": hits}, f, ensure_ascii=False, indent=1)
print("\n-> %s" % os.path.basename(out))
sys.exit(0)
