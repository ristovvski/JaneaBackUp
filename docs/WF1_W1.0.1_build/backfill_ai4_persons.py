"""Backfill the Ai4 prospects Make never created in Pipedrive.  DRY-RUN BY DEFAULT.

Consumes exactly the reconciliation output (ai4_missing_persons.jsonl) so the reported number and
the backfill can never disagree.  Two independent work items:

  PART A  300 prospects emailed with no Pipedrive person -> create person (+ lead)
  PART B   58 leads attached to the WRONG person by Make's exact-NAME search -> re-point or flag

Bodies follow the WF-2 idiom proven by static B4: absent/empty values are OMITTED, never written as
empty strings.  Person resolution is by EMAIL (statics B27-3 / B27-11), never by name - matching by
name is what produced Part B in the first place.

WRITE_MODE=live is required for any write, mirroring the WF-2 gate.  Nothing here runs without it.
Owner action first: this is Marci/Melisa's call, and the un-require (if any) precedes it.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SLK = os.environ.get("SMARTLEAD_API_KEY", "")
UA = "Mozilla/5.0 janea-backfill/1.0"
MISSING = os.path.join(HERE, "wf1-release-evidence", "ai4_missing_persons.jsonl")

OWNER_BY_CAMPAIGN = {3686193: 25151686, 3686187: 25151686,      # Rune
                     3686184: 16029123, 3686181: 16029123}      # Mario
F = {"title_a": "0b72db8f36929631afc7c449de2914c3580df7ca",
     "company": "5a282f55e910cceeb960969460b8409b4c10d623",
     "source": "6070ae31f09228f95048b0f68982b1cd4d3a684a",
     "li_url": "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20",
     "campaign": "86157bb49563191c17b4dc62580525f84417524c",
     "hypothesis": "8bdae1a91272e92b335e9e99f668cde659b6daae",
     "event_name": "ab5540d2ca45905dfb1434c0fe4971cc5790de3f",
     "medium": "961698945b0329b367da11916a94f10ff7ba71fe",
     "position": "ab15ebd797c66ac010e47e543b7ec0226694d12b",
     "li_profile": "b59a7d0af178f3149381efd9a8476370b19ca3b5",
     "li_title": "f8edcb0113a9fe4082b4116a4b3d8e085b971eed"}
SOURCE_EMAIL = 446
MEDIUM_EMAIL = "eMail"
# 2026-08-06: campaign names on the 4 active email campaigns are single-bracket
# ("[Events Visiting] AI4 2026 - ...") and can never carry a second bracket for Event
# name - WF-2's own Normalize node documents the same two-bracket contract and hits the
# same wall (see melisa_wf2_normalize_check.py output). Hardcoded here deliberately: this
# script is a one-off backfill, not the permanent fix - that's the WF-2 CONFIG map proposal
# in MELISA_EVENT_NAME_REPORT.md. Values verified against ~2300 already-correct persons.
EVENT_HYPOTHESIS_BY_CAMPAIGN = {
    3686193: "Ai4 2026", 3686187: "Ai4 2026", 3686184: "Ai4 2026", 3686181: "Ai4 2026",
}
HYPOTHESIS_VALUE = "Events Visiting"


def req(url, hdr, body=None, method=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request(url, data=data, method=method,
                                       headers={**hdr, "User-Agent": UA,
                                                **({"Content-Type": "application/json"}
                                                   if data else {})})
            with urllib.request.urlopen(r, timeout=150) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1))
                continue
            return {"__err": e.code, "__body": b}
    return {}


def pd(path, body=None, method=None):
    return req("https://api.pipedrive.com" + path, {"x-api-token": PDT}, body, method)


def sl(path):
    if not SLK:
        return {}
    sep = "&" if "?" in path else "?"
    return req(f"https://server.smartlead.ai/api/v1{path}{sep}api_key={SLK}", {})


def put(cf, key, val):
    """The B4 idiom: omit absent/empty, never write an empty string."""
    if val is None:
        return
    s = val if isinstance(val, (int, float)) else str(val).strip()
    if s == "":
        return
    cf[key] = s


def build_person(row, enrich):
    cf = {}
    put(cf, F["campaign"], row.get("campaign"))
    put(cf, F["medium"], MEDIUM_EMAIL)
    # 2026-08-06 fix: this was the exact bug Melisa's dashboard caught - F["hypothesis"] was
    # declared above but never put() here, and event_name had no key at all. Both are now
    # set from the campaign_id, since the campaign NAME can't carry a second bracket (see note
    # on EVENT_HYPOTHESIS_BY_CAMPAIGN above).
    ev = EVENT_HYPOTHESIS_BY_CAMPAIGN.get(row.get("campaign_id"))
    if ev:
        put(cf, F["hypothesis"], HYPOTHESIS_VALUE)
        put(cf, F["event_name"], ev)
    cf[F["source"]] = SOURCE_EMAIL
    title = (enrich.get("custom_fields") or {}).get("Title")
    for k in ("title_a", "position", "li_title"):
        put(cf, F[k], title)
    put(cf, F["company"], enrich.get("company_name"))
    for k in ("li_url", "li_profile"):
        put(cf, F[k], enrich.get("linkedin_profile"))
    name = (row.get("name") or "").strip() or row["email"].split("@")[0]
    body = {"name": name,
            "emails": [{"value": row["email"], "primary": True, "label": "work"}],
            "owner_id": OWNER_BY_CAMPAIGN.get(row.get("campaign_id"), 16340280)}
    if cf:
        body["custom_fields"] = cf
    return body


def main():
    rows = [json.loads(l) for l in open(MISSING, encoding="utf-8")]
    print(f"WRITE_MODE = {WRITE_MODE!r}   ({'LIVE - WILL WRITE' if WRITE_MODE == 'live' else 'dry run, no writes'})")
    print(f"input      = {MISSING}  ({len(rows)} prospects)\n")

    print("=" * 96)
    print("PART A - create the missing persons")
    print("=" * 96)
    enriched = omitted_counts = 0
    made = []
    for i, row in enumerate(rows):
        # re-verify by EMAIL immediately before writing: the reconciliation may be stale, and a
        # duplicate created in the meantime must abort this row (never create a second record).
        term = urllib.parse.quote(row["email"])
        s = pd(f"/api/v2/persons/search?term={term}&fields=email&exact_match=true&limit=5")
        items = ((s.get("data") or {}).get("items") or []) if not s.get("__err") else []
        if items:
            print(f"  SKIP  {row['email']:<44} already present as person "
                  f"{(items[0].get('item') or {}).get('id')}")
            continue
        enrich = {}
        if SLK and row.get("campaign_id"):
            d = sl(f"/leads?email={urllib.parse.quote(row['email'])}")
            if isinstance(d, dict) and not d.get("__err"):
                enrich = d
                enriched += 1
        body = build_person(row, enrich)
        omitted_counts += 10 - len(body.get("custom_fields", {}))
        made.append((row, body))
        if i < 3:
            print(f"  BODY  {row['email']}")
            print("        " + json.dumps(body, ensure_ascii=False)[:400])
        if WRITE_MODE == "live":
            r = pd("/api/v2/persons", body=body, method="POST")
            if r.get("__err"):
                print(f"  FAIL  {row['email']} -> HTTP {r['__err']} {r['__body'][:150]}")
                continue
            pid = (r.get("data") or {}).get("id")
            print(f"  MADE  person {pid} {row['email']}")

    print(f"\n  would create : {len(made)}")
    print(f"  skipped      : {len(rows) - len(made)} (already present on re-verify)")
    print(f"  enriched from Smartlead: {enriched}")
    print(f"  custom fields omitted as empty (the B4 idiom): {omitted_counts}")

    print("\n" + "=" * 96)
    print("PART B - the 58 mis-attached leads (Make's exact-NAME match)")
    print("=" * 96)
    print("  NOT auto-repaired. Re-pointing a lead silently moves history between two real people;")
    print("  some of the 58 are the same human under a stale address and must be MERGED, not moved.")
    print("  Emitted as a review list for Melisa - a human decides merge vs re-point per row.")
    print("  (see mis_attached_leads.csv from the diagnosis)")

    if WRITE_MODE != "live":
        print("\nDRY RUN COMPLETE - nothing was written.")
        print("To run for real, after Marci/Melisa confirm: WRITE_MODE=live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
