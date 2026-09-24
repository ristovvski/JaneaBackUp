import csv, re, json, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

P_LI = r"C:\Users\User\Downloads\People-DNC-Default-view-export-1786102964075.csv"

with open(P_LI, encoding="utf-8-sig", newline="") as f:
    r = csv.reader(f)
    header = next(r)
    rows = list(r)

def get(row, i):
    return row[i].strip() if i < len(row) and row[i] else ""

REPLY_RE = re.compile(r"reply", re.IGNORECASE)
UNSUB_RE = re.compile(r"unsub|opt[\s\-]?out", re.IGNORECASE)
li_re = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)
year_re = re.compile(r"(19|20)\d{2}")
MONTHS = ["january","february","march","april","may","june","july","august","september","october","november","december"]

# collision hierarchy, per owner's explicit ruling
REASON_PRIORITY = {"client": 0, "unsubscribe": 1, "reply_dnc": 2, "manual_offboard_eligible": 3, "manual_sheet": 4}

def canon_li(url):
    m = li_re.search(url)
    if not m:
        return None
    slug = m.group(1).split("?")[0].split("#")[0].rstrip("/")
    return slug.lower()

def classify_reason(owner, source):
    if REPLY_RE.search(source):
        return "reply_dnc"
    if UNSUB_RE.search(source):
        return "unsubscribe"
    if owner == "Client List":
        return "client"
    if owner:
        return "manual_offboard_eligible"
    return "manual_sheet"

def date_precision_and_added_at(source):
    y = year_re.search(source)
    if not y:
        return "unknown", "2026-08-07(import date)", None
    year = int(y.group(0))
    low = source.lower()
    month_found = next((m for m in MONTHS if m in low), None)
    if month_found:
        return "derived", f"{year}-{month_found}", year
    return "derived", f"{year}-07-01(mid-year fallback)", year

classified = []
for row in rows:
    owner, url, source = get(row, 0), get(row, 1), get(row, 2)
    reason = classify_reason(owner, source)
    slug = canon_li(url)
    precision, added_at, added_year = date_precision_and_added_at(source)
    classified.append({
        "owner_verbatim": owner, "source_verbatim": source, "url_raw": url,
        "identity_key": slug, "resolvable": slug is not None,
        "reason": reason, "date_precision": precision, "added_at": added_at, "added_year": added_year,
    })

needs_review = [c for c in classified if not c["resolvable"]]
resolvable = [c for c in classified if c["resolvable"]]

by_identity = defaultdict(list)
for c in resolvable:
    by_identity[c["identity_key"]].append(c)

# --- merge with also_flagged, per owner's collision rule ---
merged_registry_rows = []
for identity, entries in by_identity.items():
    winner = min(entries, key=lambda c: REASON_PRIORITY[c["reason"]])
    losers = [e for e in entries if e is not winner]
    also_flagged = [{"reason": e["reason"], "source_ref": e["owner_verbatim"] or None, "source": e["source_verbatim"] or None} for e in losers]
    # de-dup also_flagged by (reason, source_ref)
    seen = set()
    dedup_flags = []
    for f in also_flagged:
        key = (f["reason"], f["source_ref"])
        if key not in seen:
            seen.add(key)
            dedup_flags.append(f)
    merged_registry_rows.append({
        "identity_key": identity,
        "reason": winner["reason"],
        "source_ref": winner["owner_verbatim"] or None,
        "source": winner["source_verbatim"] or None,
        "date_precision": winner["date_precision"],
        "added_at": winner["added_at"],
        "also_flagged": dedup_flags,
        "offboard_removable": winner["reason"] == "manual_offboard_eligible",
        "collision_group_size": len(entries),
    })

print(f"Total rows: {len(classified)}")
print(f"Needs-review: {len(needs_review)}")
print(f"Resolvable: {len(resolvable)}")
print(f"Final registry rows after merge: {len(merged_registry_rows)}")

print("\n=== Final reason breakdown (post-merge, winner-takes-reason) ===")
print(Counter(r["reason"] for r in merged_registry_rows))

print("\n=== Rows with also_flagged (real collisions, secondary evidence preserved) ===")
flagged = [r for r in merged_registry_rows if r["also_flagged"]]
print(f"count: {len(flagged)}")
for r in flagged:
    print(f"  identity={r['identity_key']!r} winning_reason={r['reason']!r} offboard_removable={r['offboard_removable']} also_flagged={r['also_flagged']}")

print("\n=== offboard_removable=False rows that nonetheless carry a manual_offboard_eligible also_flag ===")
protected_but_tracked = [r for r in merged_registry_rows if not r["offboard_removable"] and any(f["reason"]=="manual_offboard_eligible" for f in r["also_flagged"])]
print(f"count: {len(protected_but_tracked)} (these must NEVER be removed by offboard, even though they match a departing ref's also_flagged)")

print("\n=== client bucket sanity (must be 95, no collisions per earlier finding) ===")
client_final = [r for r in merged_registry_rows if r["reason"] == "client"]
print(f"count={len(client_final)}, any also_flagged={sum(1 for r in client_final if r['also_flagged'])}")

print("\n=== reply_dnc final (should still be 142 winners, now possibly +3 from collisions already counted in original 142) ===")
reply_final = [r for r in merged_registry_rows if r["reason"] == "reply_dnc"]
print(f"count={len(reply_final)}")

# Write the final merged seed preview to disk for inspection / next stage
out_path = r"C:\Users\User\Desktop\Нова папка\DNC_OBS_P1_build\fixtures\people_dnc_seed_preview.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "source_file": "People-DNC-Default-view-export-1786102964075.csv",
        "generated": "dry-run, no live writes",
        "needs_review_count": len(needs_review),
        "registry_rows": merged_registry_rows,
    }, f, indent=2)
print(f"\nWrote merged seed preview ({len(merged_registry_rows)} rows) to {out_path}")
