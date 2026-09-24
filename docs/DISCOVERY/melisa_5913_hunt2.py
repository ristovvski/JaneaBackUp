import json, sys
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")

persons = json.load(open("sprint_persons_fields.json", encoding="utf-8"))
vals = list(persons.values())


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def has(v, field):
    return v.get(field) not in (None, "", [])


CUTOFFS = {
    "since_2026-07-01": datetime(2026, 7, 1),
    "since_2026-07-15": datetime(2026, 7, 15),
    "since_2026-07-16": datetime(2026, 7, 16),
    "since_2026-07-18": datetime(2026, 7, 18),
    "since_2026-07-19": datetime(2026, 7, 19),
    "since_2026-06-01": datetime(2026, 6, 1),
    "since_2026-01-01": datetime(2026, 1, 1),
    "since_2025-01-01": datetime(2025, 1, 1),
}

for v in vals:
    v["_dt"] = parse_dt(v.get("add_time"))

MEDIUM_SET = ("eMail", "LinkedIn", "eMail ", "LinkedIn ", "Linkedin")


def medium_match(v):
    return v.get("medium") in MEDIUM_SET or has(v, "li_url")


print(f"{'cutoff':22s}  medium-match-since-cutoff")
for name, cut in CUTOFFS.items():
    n = sum(1 for v in vals if v["_dt"] and v["_dt"] >= cut and medium_match(v))
    flag = "  <<<< MATCH" if n == 5913 else (f"  <near diff={abs(n-5913)}>" if abs(n - 5913) <= 100 else "")
    print(f"  {name:20s} -> {n:6d}{flag}")

print()
print("narrower: medium in (eMail,LinkedIn) exact (no variants), since cutoff")
for name, cut in CUTOFFS.items():
    n = sum(1 for v in vals if v["_dt"] and v["_dt"] >= cut and v.get("medium") in ("eMail", "LinkedIn"))
    flag = "  <<<< MATCH" if n == 5913 else (f"  <near diff={abs(n-5913)}>" if abs(n - 5913) <= 100 else "")
    print(f"  {name:20s} -> {n:6d}{flag}")

print()
print("has campaign field set (any value), since cutoff")
for name, cut in CUTOFFS.items():
    n = sum(1 for v in vals if v["_dt"] and v["_dt"] >= cut and has(v, "campaign"))
    flag = "  <<<< MATCH" if n == 5913 else (f"  <near diff={abs(n-5913)}>" if abs(n - 5913) <= 100 else "")
    print(f"  {name:20s} -> {n:6d}{flag}")

print()
print("event_name = 'Ai4 2026' specifically, no date filter")
n = sum(1 for v in vals if v.get("event_name") == "Ai4 2026")
print(f"  event_name=='Ai4 2026' -> {n}")

print()
print("campaign field contains 'ai4' (any case), no date filter")
n = sum(1 for v in vals if v.get("campaign") and "ai4" in str(v.get("campaign")).lower())
print(f"  campaign contains ai4 -> {n}")
