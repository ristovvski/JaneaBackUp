import csv, re
from collections import Counter

P_EMAIL = r"C:\Users\User\Downloads\People-Email-DNC-Default-view-export-1786102985813.csv"
P_LI = r"C:\Users\User\Downloads\People-DNC-Default-view-export-1786102964075.csv"
P_COMPANY = r"C:\Users\User\Downloads\Company-DNC-Copy-of-Default-view-export-1786102974783.csv"

def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        rows = list(r)
    return header, rows

def analyze(path):
    header, rows = load(path)
    print(f"\n=== {path.split(chr(92))[-1]} ===")
    print("header:", header)
    print("data rows:", len(rows))
    for i, col in enumerate(header):
        vals = [row[i] if i < len(row) else "" for row in rows]
        empty = sum(1 for v in vals if not v.strip())
        uniq = len(set(v.strip() for v in vals if v.strip()))
        print(f"  col[{i}] '{col}': empty={empty}, distinct_nonempty={uniq}")
    return header, rows

h1, r1 = analyze(P_EMAIL)
h2, r2 = analyze(P_LI)
h3, r3 = analyze(P_COMPANY)

print("\n--- Owner distribution (People-Email-DNC) ---")
print(Counter(row[1].strip() for row in r1 if len(row) > 1).most_common(10))
print("\n--- Owner distribution (People-DNC) ---")
print(Counter(row[0].strip() for row in r2 if len(row) > 0).most_common(10))

print("\n--- Source distribution (People-Email-DNC) ---")
print(Counter(row[2].strip() if len(row) > 2 else "" for row in r1).most_common(10))
print("\n--- Source distribution (People-DNC) ---")
print(Counter(row[2].strip() if len(row) > 2 else "" for row in r2).most_common(10))

email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
emails = [row[0].strip() for row in r1 if row]
bad_emails = [e for e in emails if not email_re.match(e)]
print(f"\nPeople-Email-DNC: {len(emails)} emails, {len(bad_emails)} fail basic shape check")
print("sample bad:", bad_emails[:10])

lc_emails = [e.lower() for e in emails]
dup_emails = [e for e, c in Counter(lc_emails).items() if c > 1]
print(f"duplicate emails (case-insensitive) within file: {len(dup_emails)}")
print("sample dup:", dup_emails[:5])

li_re = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)
urls = [row[1].strip() for row in r2 if len(row) > 1]
matchable = [u for u in urls if li_re.search(u)]
unmatchable = [u for u in urls if not li_re.search(u)]
print(f"\nPeople-DNC: {len(urls)} URLs, matchable(/in/)={len(matchable)}, unmatchable={len(unmatchable)}")
print("sample unmatchable:", unmatchable[:15])

def canon_li(u):
    m = li_re.search(u)
    if not m:
        return None
    slug = m.group(1).split("?")[0].split("#")[0].rstrip("/")
    return slug.lower()

slugs = [canon_li(u) for u in urls]
slugs_nonnull = [s for s in slugs if s]
dup_slugs = [s for s, c in Counter(slugs_nonnull).items() if c > 1]
print(f"duplicate LI slugs (canonicalized) within file: {len(dup_slugs)} (affecting {sum(c for s,c in Counter(slugs_nonnull).items() if c>1)} rows)")
print("sample dup slugs:", dup_slugs[:5])

empty_url_rows = sum(1 for row in r2 if len(row) < 2 or not row[1].strip())
print(f"rows with empty/missing LI URL: {empty_url_rows}")

domains = [row[0].strip() for row in r3 if row]
domain_re = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", re.IGNORECASE)
bad_domains = [d for d in domains if not domain_re.match(d)]
dup_domains = [d for d, c in Counter(d.lower() for d in domains).items() if c > 1]
print(f"\nCompany-DNC: {len(domains)} domains, malformed={len(bad_domains)}, duplicates={len(dup_domains)}")
print("sample malformed:", bad_domains[:10])
print("sample dup domains:", dup_domains[:10])
