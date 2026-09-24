import csv, re
from collections import Counter, defaultdict

P_LI = r"C:\Users\User\Downloads\People-DNC-Default-view-export-1786102964075.csv"

with open(P_LI, encoding="utf-8-sig", newline="") as f:
    r = csv.reader(f)
    header = next(r)
    rows = list(r)

def get(row, i):
    return row[i].strip() if i < len(row) and row[i] else ""

# full owner distribution
owners = Counter(get(row, 0) for row in rows)
print("=== Full Owner distribution ===")
for o, c in owners.most_common():
    print(f"  {o!r}: {c}")

print("\n=== Full Source distribution ===")
sources = Counter(get(row, 2) for row in rows)
for s, c in sources.most_common():
    print(f"  {s!r}: {c}")

print("\n=== Owner x Source cross-tab ===")
cross = Counter((get(row, 0), get(row, 2)) for row in rows)
for (o, s), c in sorted(cross.items(), key=lambda kv: -kv[1]):
    print(f"  owner={o!r:20s} source={s!r:25s} count={c}")

# --- reason mapping rule ---
REPLY_RE = re.compile(r"reply", re.IGNORECASE)
UNSUB_RE = re.compile(r"unsub|opt[\s\-]?out", re.IGNORECASE)

def classify(owner, source):
    if REPLY_RE.search(source):
        return "reply_dnc"
    if UNSUB_RE.search(source):
        return "unsubscribe"
    if owner:
        return "manual_offboard_eligible"
    return "manual_sheet"

bucket_counts = Counter()
bucket_examples = defaultdict(list)
for row in rows:
    owner, url, source = get(row, 0), get(row, 1), get(row, 2)
    reason = classify(owner, source)
    bucket_counts[reason] += 1
    if len(bucket_examples[reason]) < 3:
        bucket_examples[reason].append((owner, url, source))

print("\n=== Reason mapping result (by rule) ===")
for reason, count in bucket_counts.most_common():
    print(f"  {reason}: {count}")
    for ex in bucket_examples[reason]:
        print(f"     e.g. owner={ex[0]!r} source={ex[2]!r} url={ex[1][:60]!r}")

# breakdown of manual_offboard_eligible by owner (source_ref)
print("\n=== manual_offboard_eligible breakdown by owner (source_ref) ===")
moe_owners = Counter(get(row, 0) for row in rows if classify(get(row,0), get(row,2)) == "manual_offboard_eligible")
for o, c in moe_owners.most_common():
    print(f"  {o!r}: {c}")

# breakdown of reply_dnc by exact source string (to check for other event tags we might've missed)
print("\n=== reply_dnc rows by exact source string ===")
reply_sources = Counter(get(row, 2) for row in rows if classify(get(row,0), get(row,2)) == "reply_dnc")
for s, c in reply_sources.most_common():
    print(f"  {s!r}: {c}")

# date_precision for reply_dnc bucket: can we derive anything beyond "Amsterdam 2025"?
print("\n=== date_precision assignment for reply_dnc bucket ===")
# rule: if source string contains a 4-digit year -> derived (mid-year fallback unless a month token is found); else unknown
MONTHS = ["january","february","march","april","may","june","july","august","september","october","november","december",
          "jan","feb","mar","apr","jun","jul","aug","sep","sept","oct","nov","dec"]
year_re = re.compile(r"(19|20)\d{2}")

def date_precision_and_added_at(source):
    y = year_re.search(source)
    if not y:
        return "unknown", None
    year = y.group(0)
    month_found = None
    low = source.lower()
    for m in MONTHS:
        if m in low:
            month_found = m
            break
    if month_found:
        return "derived", f"{year}-{month_found}(named)"
    return "derived", f"{year}-07-01(mid-year fallback)"

precision_counts = Counter()
for row in rows:
    owner, url, source = get(row, 0), get(row, 1), get(row, 2)
    if classify(owner, source) != "reply_dnc":
        continue
    prec, added_at = date_precision_and_added_at(source)
    precision_counts[(prec, added_at)] += 1

for (prec, added_at), c in precision_counts.most_common():
    print(f"  precision={prec:10s} added_at={added_at!r}: {c} rows")

# Sanity: any malformed/empty-URL rows inside reply_dnc or manual_offboard_eligible buckets? (needs-review overlap)
li_re = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)
print("\n=== URL resolvability x reason bucket (needs-review overlap check) ===")
overlap = Counter()
for row in rows:
    owner, url, source = get(row, 0), get(row, 1), get(row, 2)
    reason = classify(owner, source)
    resolvable = bool(url) and bool(li_re.search(url))
    overlap[(reason, resolvable)] += 1
for (reason, resolvable), c in sorted(overlap.items()):
    print(f"  reason={reason:28s} url_resolvable={resolvable}: {c}")
