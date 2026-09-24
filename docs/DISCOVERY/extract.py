#!/usr/bin/env python3
import json, os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discovery_raw.json")
d = json.load(open(P, encoding="utf-8"))

# patch verified email total (limit fix) — records hold SMTP/IMAP creds, NOT persisted
d["smartlead"]["email_accounts_total"] = {"call": {"ok": True, "status": 200}, "count": 415,
    "note": "limit=500; records include SMTP/IMAP passwords — deliberately NOT persisted"}
d["smartlead"]["webhooks_verified_empty"] = True
json.dump(d, open(P, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=str)

sl = d["smartlead"]; pd = d["pipedrive"]
asn = sl.get("email_account_assignment", [])
tot = sum(a.get("email_account_count", 0) for a in asn)
active = [c for c in sl["campaigns"] if c.get("status") == "ACTIVE"]
print("SMARTLEAD: campaigns=%d (active=%d) ; email_accounts=415 ; native_webhooks=0 (verified)"
      % (len(sl["campaigns"]), len(active)))
from collections import Counter
print("  campaign status:", dict(Counter(c.get("status") for c in sl["campaigns"])))
print("  per-campaign EA count: min=%s max=%s sum_over_campaigns=%s (accounts are shared/reused)"
      % (min((a["email_account_count"] for a in asn), default=0),
         max((a["email_account_count"] for a in asn), default=0), tot))
print("  categories:", [(c["name"], c["sentiment_type"]) for c in sl["categories"]])

def fields(ent):
    return pd["fields"][ent]["list"], pd["sampling"][ent]["usage"], pd["sampling"][ent]["sampled"]

print("\nPIPEDRIVE field usage (custom fields = 40-hex keys):")
for ent in ("person", "organization", "deal", "lead"):
    fl, use, n = fields(ent)
    custom = [f for f in fl if f.get("key") and len(f["key"]) >= 30]
    used = sorted([(use.get(f["key"], 0), f["name"], f["field_type"]) for f in custom], reverse=True)
    zero = [f for f in custom if use.get(f["key"], 0) == 0.0]
    print("\n== %s == total=%d custom=%d sampled=%d" % (ent, len(fl), len(custom), n))
    print("  TOP custom by usage:")
    for pct, name, ft in used[:14]:
        print("    %5.1f%%  %-38s %s" % (pct, (name or "")[:38], ft))
    print("  ZERO-usage custom (%d): %s" % (len(zero), ", ".join((f["name"] or "?")[:24] for f in zero[:22])))

print("\nPIPEDRIVE users=%d filters=%d lead_labels=%d webhooks=%d"
      % (pd["users"]["count"], len(pd["filters"]), len(pd["lead_labels"]),
         len(pd["webhooks"]["list"])))
print("  webhook dest:", [w["url"] for w in pd["webhooks"]["list"]])
print("  lead_labels:", [l["name"] for l in pd["lead_labels"]])
