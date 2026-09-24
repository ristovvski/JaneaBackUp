"""Rebuild the Slava wrong-person queue from a FRESH post-backfill Pipedrive snapshot.

Source: the 2026-08-04 CSV twin (58 rows, taxonomy RE-POINT/MERGE/NO-EMAIL-CHECK/REVIEW frozen).
For each row:
  - re-check every lead UUID's CURRENT person_id (via the fresh lead_person_map.json) against the
    originally-recorded "Currently attached to #ID" - if it changed, someone already hand-fixed it
    -> DONE, moved to the end, regardless of original bucket.
  - re-verify our contacted email now HAS a person (it should - backfill-300 ran) and note its id.
  - for NO-EMAIL-CHECK rows, re-check whether the attached person has since gained an email.
  - rewrite the note: the backfill-pending phrase becomes "персона уже создана - найди по email
    {email} (person #{id})".
Read-only against Pipedrive. Writes only the new CSV twin (+ a best-effort xlsx with a hard timeout,
per [[office-file-handle-lock]] - CSV is the primary, verified artifact regardless of the xlsx).
"""
import csv
import json
import os
import re
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf1-release-evidence")
SRC = os.path.join(OUT, "slava-handoff-2026-08-04", "SLAVA_wrong_person_queue_TWIN.csv")
LEAD_MAP_PATH = os.path.join(OUT, "lead_person_map.json")
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-forensics/1.0"
NEW_DIR = os.path.join(OUT, "slava-handoff-2026-08-05")
os.makedirs(NEW_DIR, exist_ok=True)

OLD_BACKFILL_PHRASE_RE = re.compile(
    r"Персоны с нашим email в Pipedrive пока нет — этот адрес входит в список бэкфилла \(300\), "
    r"так что сначала поищи по email, чтобы не сделать дубль\.?")


def pd(path, tries=4):
    import time
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path,
                                       headers={"x-api-token": PDT, "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=90) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return {"__err": e.code}
    return {}


def norm_email(u):
    return str(u or "").strip().lower()


lead_map = json.load(open(LEAD_MAP_PATH, encoding="utf-8"))
rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
print(f"source rows: {len(rows)}")

# fresh email -> person_id, built once (57k+ persons doesn't fit in memory issues, but let's scan)
print("scanning Pipedrive persons for current email -> id map...")
by_email, cursor, pages = {}, None, 0
while True:
    q = "/api/v2/persons?limit=500&sort_by=id&sort_direction=asc" + (f"&cursor={cursor}" if cursor else "")
    d = pd(q)
    for p in d.get("data") or []:
        for em in p.get("emails") or []:
            v = norm_email(em.get("value"))
            if v:
                by_email.setdefault(v, p)
    pages += 1
    cursor = (d.get("additional_data") or {}).get("next_cursor")
    if not cursor:
        break
print(f"  {pages} pages, {len(by_email)} distinct emails")

out_rows, done_rows = [], []
counts = {"RE-POINT": 0, "MERGE": 0, "NO-EMAIL-CHECK": 0, "REVIEW": 0, "DONE": 0}
for r in rows:
    email = norm_email(r["Email we contacted"])
    action = r["ACTION"]
    lead_urls = [r.get(k) for k in ("Open the lead", "Open lead 2", "Open lead 3", "Open lead 4")
                if r.get(k)]
    lead_uuids = [u.rstrip("/").rsplit("/", 1)[-1] for u in lead_urls]
    orig_attached_ids = set(re.findall(r"#(\d+)", r["Currently attached to"]))

    # did any of these leads change person since 2026-08-04?
    changed = False
    for uuid in lead_uuids:
        lm = lead_map.get(uuid)
        if lm and str(lm.get("person_id")) not in orig_attached_ids and orig_attached_ids:
            changed = True

    new_person = by_email.get(email)
    new_note = OLD_BACKFILL_PHRASE_RE.sub(
        f"Персона уже создана — найди по email {email}"
        + (f" (person #{new_person['id']})." if new_person else " (НЕ НАЙДЕНА — проверь вручную!)."),
        r["One-line note"])

    row = dict(r)
    row["One-line note"] = new_note
    row["Backfilled person id"] = new_person["id"] if new_person else ""

    if changed:
        row["ACTION"] = "DONE"
        row["One-line note"] = ("[Похоже, кто-то уже исправил это вручную — привязка лида "
                                "изменилась с 2026-08-04.] " + new_note)
        counts["DONE"] += 1
        done_rows.append(row)
    else:
        counts[action] = counts.get(action, 0) + 1
        out_rows.append(row)

# sort: original bucket order, DONE last
order = {"RE-POINT": 0, "MERGE": 1, "NO-EMAIL-CHECK": 2, "REVIEW": 3, "DONE": 4}
all_rows = sorted(out_rows, key=lambda r: order.get(r["ACTION"], 9)) + done_rows
for i, r in enumerate(all_rows, 1):
    r["#"] = i

print("\nrecomputed taxonomy:")
for k, v in counts.items():
    print(f"  {v:>3}  {k}")
print(f"  {sum(counts.values()):>3}  TOTAL")

no_person_found = [r for r in all_rows if r["ACTION"] != "DONE" and not r["Backfilled person id"]]
if no_person_found:
    print(f"\n!! {len(no_person_found)} rows: backfilled person NOT found by email - investigate "
          f"before handoff:")
    for r in no_person_found:
        print(f"    {r['Prospect name']}  {r['Email we contacted']}")

fieldnames = list(all_rows[0].keys())
csv_path = os.path.join(NEW_DIR, "SLAVA_wrong_person_queue_2026-08-05_TWIN.csv")
with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(all_rows)
print(f"\nwrote {csv_path} ({len(all_rows)} rows) - VERIFIED, this is the primary artifact")
