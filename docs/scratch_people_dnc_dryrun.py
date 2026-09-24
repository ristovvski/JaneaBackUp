import csv, re, json
from collections import Counter, defaultdict

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

# alias table scaffold (amendment 2) -- unconfirmed, applied at query time only, never rewrites rows
ALIAS_TABLE = [
    {"canonical_ref": None, "variants": ["Jim", "Jim Ash"], "status": "unconfirmed", "confirmed_by": None},
    {"canonical_ref": None, "variants": ["Mario", "Mario Stalder"], "status": "unconfirmed", "confirmed_by": None},
]
ALIAS_TOUCHED_REFS = {v for entry in ALIAS_TABLE for v in entry["variants"]}

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
        return "unknown", "2026-08-07(import date)"
    year = y.group(0)
    low = source.lower()
    month_found = next((m for m in MONTHS if m in low), None)
    if month_found:
        return "derived", f"{year}-{month_found}"
    return "derived", f"{year}-07-01(mid-year fallback)"

TTL_MONTHS = 6
IMPORT_DATE = (2026, 8, 7)

def add_months(y, m, d, months):
    total = (y * 12 + (m - 1)) + months
    ny, nm = divmod(total, 12)
    nm += 1
    return ny, nm, d

def compute_expires_at(reason, precision, added_at_year):
    # reason -> lifecycle policy
    if reason in ("client",):
        return None, "permanent (client, never-removable per amendment 1)"
    if reason == "manual_offboard_eligible":
        return None, "permanent_until_offboarding (owner_tag scoped)"
    if reason == "manual_sheet":
        return None, "permanent (manual default)"
    if reason == "reply_dnc":
        if precision != "derived":
            return None, "date_precision=unknown -> expires_at=null (asymmetric-cost rule)"
        # derived: mid-2025 + 6mo = ~early 2026, already past "today" 2026-08-07
        y = added_at_year
        ey, em, ed = add_months(y, 7, 1, TTL_MONTHS)
        expires = f"{ey}-{em:02d}-{ed:02d}"
        is_past = (ey, em) < (IMPORT_DATE[0], IMPORT_DATE[1])
        return expires, ("PAST-DATED at seed time -> seed status=active, flag batch, expiry sweep must SKIP" if is_past else "future, normal sweep applies")
    return None, "unclassified"

# --- pass 1: classify every row, canonicalize identity ---
classified = []
for row in rows:
    owner, url, source = get(row, 0), get(row, 1), get(row, 2)
    reason = classify_reason(owner, source)
    slug = canon_li(url)
    precision, added_at = date_precision_and_added_at(source)
    added_year = int(year_re.search(source).group(0)) if reason == "reply_dnc" and year_re.search(source) else None
    expires_at, expiry_note = compute_expires_at(reason, precision, added_year) if reason == "reply_dnc" else compute_expires_at(reason, precision, None)
    classified.append({
        "owner_verbatim": owner,
        "source_verbatim": source,
        "url_raw": url,
        "identity_key": slug,
        "resolvable": slug is not None,
        "reason": reason,
        "date_precision": precision,
        "added_at": added_at,
        "expires_at": expires_at,
        "expiry_note": expiry_note,
        "alias_touched": owner in ALIAS_TOUCHED_REFS,
    })

# --- needs-review bucket: unresolvable identity ---
needs_review = [c for c in classified if not c["resolvable"]]
resolvable = [c for c in classified if c["resolvable"]]

print(f"Total rows: {len(classified)}")
print(f"Needs-review (unresolvable LI identity, no email fallback in this file): {len(needs_review)}")
print(f"Resolvable (has identity_key): {len(resolvable)}")

print("\n=== reason breakdown (resolvable rows only) ===")
print(Counter(c["reason"] for c in resolvable))

print("\n=== reason breakdown (needs-review rows) ===")
print(Counter(c["reason"] for c in needs_review))

# --- in-file dedup / collision detection on resolvable rows ---
by_identity = defaultdict(list)
for c in resolvable:
    by_identity[c["identity_key"]].append(c)

dup_groups = {k: v for k, v in by_identity.items() if len(v) > 1}
print(f"\n=== In-file duplicate identity groups: {len(dup_groups)} (affecting {sum(len(v) for v in dup_groups.values())} rows) ===")

same_reason_dups = 0
mixed_reason_dups = 0
mixed_examples = []
client_vs_other_mixed = 0
for k, v in dup_groups.items():
    reasons = set(c["reason"] for c in v)
    if len(reasons) == 1:
        same_reason_dups += 1
    else:
        mixed_reason_dups += 1
        if "client" in reasons and len(reasons) > 1:
            client_vs_other_mixed += 1
        if len(mixed_examples) < 10:
            mixed_examples.append((k, [(c["owner_verbatim"], c["reason"], c["source_verbatim"]) for c in v]))

print(f"  same-reason duplicate groups (trivial collapse): {same_reason_dups}")
print(f"  MIXED-reason duplicate groups (need tie-break rule): {mixed_reason_dups}")
print(f"  of which involve 'client' colliding with another reason: {client_vs_other_mixed}")
print("\n  sample mixed-reason collisions:")
for k, entries in mixed_examples:
    print(f"    identity={k!r}")
    for e in entries:
        print(f"       owner={e[0]!r} reason={e[1]!r} source={e[2]!r}")

# --- unique persons after in-file dedup ---
unique_identities = len(by_identity)
print(f"\nUnique identities after in-file canonicalization: {unique_identities} (from {len(resolvable)} resolvable rows)")

# --- reply_dnc past-dated flag summary ---
reply_rows = [c for c in resolvable if c["reason"] == "reply_dnc"]
past_dated = [c for c in reply_rows if "PAST-DATED" in c["expiry_note"]]
print(f"\n=== reply_dnc batch flag ===")
print(f"  total reply_dnc (resolvable): {len(reply_rows)}")
print(f"  past-dated at seed time (business decision needed): {len(past_dated)}")
if reply_rows:
    print(f"  sample: added_at={reply_rows[0]['added_at']!r} expires_at={reply_rows[0]['expires_at']!r} note={reply_rows[0]['expiry_note']!r}")

# --- client bucket summary ---
client_rows = [c for c in resolvable if c["reason"] == "client"]
print(f"\n=== client bucket ===")
print(f"  total client rows: {len(client_rows)}")
print(f"  unique identities: {len(set(c['identity_key'] for c in client_rows))}")

# --- alias-touched summary ---
alias_rows = [c for c in resolvable if c["alias_touched"]]
print(f"\n=== alias-table-touched rows (Jim/Jim Ash, Mario/Mario Stalder) ===")
print(Counter(c["owner_verbatim"] for c in alias_rows))
print(f"  total rows touched by unconfirmed aliases: {len(alias_rows)}")
print(f"  ALIAS_TABLE scaffold: {json.dumps(ALIAS_TABLE, indent=2)}")

# --- final projected registry-row count (post in-file dedup, pre cross-source dedup against Pipedrive) ---
print(f"\n=== Projected outcome if seeded now (People-DNC only, no Pipedrive cross-check yet) ===")
print(f"  registry rows to create (unique identities): {unique_identities}")
print(f"  needs-review rows (parked, no auto-create): {len(needs_review)}")
print(f"  mixed-reason collisions requiring a tie-break rule before write: {mixed_reason_dups}")
