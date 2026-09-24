import json, re, sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open('melisa_gap_joined.json', encoding='utf-8'))
all_recs = d['all']

def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

CUTOFF = parse_dt("2026-07-22T00:00:00+00:00")
CUTOFF2 = parse_dt("2026-07-22T12:00:00+00:00")

EMAIL_IDS = ("3686193", "3686187", "3686184", "3686181")
LI_IDS = ("512995", "513000")

def is_email(title):
    return any(c in title for c in EMAIL_IDS)

def is_li(title):
    return any(c in title for c in LI_IDS)

def is_2026(title):
    return bool(re.search(r'ai4\s*2026', title.lower()))

def empty(v):
    return v is None or str(v).strip() == ""

missing_event = [r for r in all_recs if r.get('person_found') and empty(r.get('event_name'))]
has_event = [r for r in all_recs if r.get('person_found') and not empty(r.get('event_name'))]

def count(filt, pool):
    return sum(1 for r in pool if filt(r))

print("=== LEAD-lens combos (filter on LEAD add_time) ===")
for chan_name, chan_f in [("both", lambda t: True), ("email", is_email), ("linkedin", is_li)]:
    for year_name, year_f in [("2026only", is_2026), ("any", lambda t: True)]:
        for cut_name, cut_f in [
            ("no_cutoff", lambda dt: True),
            ("lead_after_07-22", lambda dt: dt and dt > CUTOFF),
            ("lead_after_07-22_1200", lambda dt: dt and dt > CUTOFF2),
            ("lead_before_07-22", lambda dt: dt and dt <= CUTOFF),
        ]:
            n = count(lambda r: chan_f(r['title']) and year_f(r['title']) and cut_f(parse_dt(r.get('lead_add_time'))), missing_event)
            marker = "  <<<<< 372 MATCH" if n == 372 else ("  <near>" if abs(n - 372) <= 10 else "")
            print(f"  chan={chan_name:9s} year={year_name:9s} cutoff={cut_name:22s} -> {n:5d}{marker}")

print()
print("=== PERSON-lens combos (filter on PERSON add_time instead of lead add_time) ===")
CUTOFF_NAIVE = CUTOFF.replace(tzinfo=None)
CUTOFF2_NAIVE = CUTOFF2.replace(tzinfo=None)

def parse_dt_naive(s):
    dt = parse_dt(s)
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt

for chan_name, chan_f in [("both", lambda t: True), ("email", is_email), ("linkedin", is_li)]:
    for year_name, year_f in [("2026only", is_2026), ("any", lambda t: True)]:
        for cut_name, cut_f in [
            ("no_cutoff", lambda dt: True),
            ("person_after_07-22", lambda dt: dt and dt > CUTOFF_NAIVE),
            ("person_after_07-22_1200", lambda dt: dt and dt > CUTOFF2_NAIVE),
            ("person_before_07-22", lambda dt: dt and dt <= CUTOFF_NAIVE),
        ]:
            n = count(lambda r: chan_f(r['title']) and year_f(r['title']) and cut_f(parse_dt_naive(r.get('person_add_time'))), missing_event)
            marker = "  <<<<< 372 MATCH" if n == 372 else ("  <near>" if abs(n - 372) <= 10 else "")
            print(f"  chan={chan_name:9s} year={year_name:9s} cutoff={cut_name:22s} -> {n:5d}{marker}")

bf300 = set()
try:
    for l in open('../WF1_W1.0.1_build/wf1-release-evidence/ai4_missing_persons.jsonl', encoding='utf-8'):
        row = json.loads(l)
        bf300.add(row['email'].lower())
except Exception as e:
    print("bf300 load error:", e)
print(f"\nbackfill-300 source list size: {len(bf300)}")
in_missing_from_bf300 = [r for r in missing_event if (r.get('person_email') or '').lower() in bf300]
print(f"of backfill-300 emails, currently in event_missing bucket: {len(in_missing_from_bf300)}")

print(f"\nTotal missing_event (person_found only): {len(missing_event)}")
print(f"Total has_event (person_found only): {len(has_event)}")
