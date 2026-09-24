import json, sys
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open('melisa_gap_joined.json', encoding='utf-8'))
missing = d['buckets']['event_missing']


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None


# bucket by minute of lead_add_time to find batch-creation clusters
by_minute = defaultdict(list)
for r in missing:
    dt = parse_dt(r.get('lead_add_time'))
    if dt:
        key = dt.strftime("%Y-%m-%d %H:%M")
        by_minute[key].append(r)

clusters = sorted(by_minute.items(), key=lambda kv: -len(kv[1]))
print("Top 20 lead-creation-minute clusters within the event_missing bucket:")
for key, rows in clusters[:20]:
    print(f"  {key}  -> {len(rows)} leads   sample: {rows[0]['title'][:60]}")

# total across all clusters with >=3 leads in the same minute (likely batch jobs, not organic one-by-one)
batch_total = sum(len(rows) for _, rows in clusters if len(rows) >= 3)
print(f"\nTotal leads in any minute-cluster of size >=3: {batch_total}")
print(f"Total leads in any minute-cluster of size >=5: {sum(len(rows) for _, rows in clusters if len(rows) >= 5)}")
print(f"Total leads in any minute-cluster of size >=8: {sum(len(rows) for _, rows in clusters if len(rows) >= 8)}")

# Also: how many DISTINCT calendar days does event_missing span, and what does the daily count look like recently
by_day = defaultdict(int)
for r in missing:
    dt = parse_dt(r.get('lead_add_time'))
    if dt:
        by_day[dt.strftime("%Y-%m-%d")] += 1
print("\nRecent 15 days with missing-event lead creations:")
for day in sorted(by_day.keys())[-15:]:
    print(f"  {day}: {by_day[day]}")
