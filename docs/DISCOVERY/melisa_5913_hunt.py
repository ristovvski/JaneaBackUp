import json, sys
sys.stdout.reconfigure(encoding="utf-8")

persons = json.load(open("sprint_persons_fields.json", encoding="utf-8"))
vals = list(persons.values())
print(f"total persons: {len(vals)}")


def has(v, field):
    return v.get(field) not in (None, "", [])


from collections import Counter
print("\nMedium value distribution:", Counter(v.get("medium") for v in vals).most_common(10))
print("\nSource value distribution:", Counter(v.get("source") for v in vals).most_common(10))

# candidate filters
li_or_email = [v for v in vals if v.get("medium") in ("LinkedIn", "eMail")]
print(f"\nmedium in (LinkedIn, eMail): {len(li_or_email)}")

has_li_url_or_email_medium = [v for v in vals if has(v, "li_url") or v.get("medium") == "eMail"]
print(f"has li_url OR medium=eMail: {len(has_li_url_or_email_medium)}")

has_campaign = [v for v in vals if has(v, "campaign")]
print(f"has any campaign field set: {len(has_campaign)}")

medium_li = [v for v in vals if v.get("medium") == "LinkedIn"]
medium_email = [v for v in vals if v.get("medium") == "eMail"]
print(f"medium=LinkedIn only: {len(medium_li)}")
print(f"medium=eMail only: {len(medium_email)}")
print(f"sum (may double count if a person has both... but medium is single-value so no overlap possible): {len(medium_li) + len(medium_email)}")

# has li_url (LinkedHelper-sourced signal) regardless of medium field
has_li_url = [v for v in vals if has(v, "li_url")]
print(f"\nhas li_url (any): {len(has_li_url)}")
has_li_url_no_medium_email = [v for v in vals if has(v, "li_url") and v.get("medium") != "eMail"]
print(f"has li_url AND medium != eMail: {len(has_li_url_no_medium_email)}")

# emails: how many persons have an email at all
has_email = [v for v in vals if v.get("email")]
print(f"\nhas an email address at all: {len(has_email)}")

# union: (medium=LinkedIn OR has li_url) OR medium=eMail  -- "contacts from email + linkedhelper"
union_v1 = [v for v in vals if v.get("medium") == "eMail" or v.get("medium") == "LinkedIn" or has(v, "li_url")]
print(f"\nunion(medium=eMail, medium=LinkedIn, has li_url): {len(union_v1)}")

for target in (5913,):
    print(f"\n--- combos near {target} ---")
    combos = {
        "medium=LinkedIn": len(medium_li),
        "medium=eMail": len(medium_email),
        "medium in (LinkedIn,eMail)": len(li_or_email),
        "has li_url": len(has_li_url),
        "has campaign field": len(has_campaign),
        "medium LI+eMail sum": len(medium_li) + len(medium_email),
        "has li_url + medium eMail sum": len(has_li_url) + len(medium_email),
        "union all 3": len(union_v1),
        "has email addr": len(has_email),
    }
    for name, n in combos.items():
        d = abs(n - target)
        flag = "  <<<< MATCH" if n == target else (f"  <near, diff={d}>" if d <= 50 else "")
        print(f"  {name:35s} -> {n:6d}{flag}")
