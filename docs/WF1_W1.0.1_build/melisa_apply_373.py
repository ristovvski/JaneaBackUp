#!/usr/bin/env python3
"""LIVE WRITE (WRITE_MODE=live required). Applies the 373-person dry-run computed in
DISCOVERY/melisa_dry_run_output.json: Hypothesis canonicalization + Event name backfill on
Pipedrive persons. John Mathew (lead 3756410, malformed bracket structure) is excluded -
manual-flagged, never touched by this script.

Safety:
  - Re-fetches each person's CURRENT custom_fields immediately before writing (avoids a stale-
    snapshot double-write if someone else already fixed it since the dry-run).
  - PATCH only, only the two target field keys - never touches any other field.
  - Per-row log: person_id, email, before, after, http status.
  - WRITE_MODE=shadow (default) prints what it WOULD do; WRITE_MODE=live performs the PATCH.
"""
import json, os, sys, time, ssl
import urllib.request, urllib.parse

WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DISC = os.path.join(HERE, "..", "DISCOVERY")

F_EVENT = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"

JOHN_MATHEW_LEAD_TITLE_FRAGMENT = "3756410 - [Events Visiting] AI4 2026 - Rune - John Mathew"


def pd(path, method="GET", body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path, data=data, method=method,
                                       headers={"x-api-token": PDT, "User-Agent": UA,
                                                **({"Content-Type": "application/json"} if data else {})})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return x.status, json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return e.code, b
    return 0, None


def main():
    live = WRITE_MODE == "live"
    print(f"WRITE_MODE={WRITE_MODE!r}  ({'LIVE - WILL WRITE' if live else 'dry run, no writes'})")

    d = json.load(open(os.path.join(DISC, "melisa_dry_run_output.json"), encoding="utf-8"))
    by_person = d["by_person"]
    print(f"input: {len(by_person)} persons with a computed intended write")

    # exclude John Mathew defensively even though he was never in by_person (belt + suspenders)
    excluded = [pid for pid, v in by_person.items() if "John Mathew" in v.get("sample_title", "")]
    for pid in excluded:
        print(f"  EXCLUDING (manual-flagged): person {pid} - {by_person[pid]['sample_title']}")
        del by_person[pid]

    results = []
    ok = skipped_already_fixed = failed = 0
    for pid, v in by_person.items():
        st, cur = pd(f"/v1/persons/{pid}")
        if st != 200 or not isinstance(cur, dict) or not cur.get("data"):
            print(f"  FAILED re-fetch person {pid}: {st}")
            failed += 1
            results.append({"person_id": pid, "status": "refetch_failed", "http": st})
            continue
        person = cur["data"]
        cur_event = person.get(F_EVENT)
        cur_hypo = person.get(F_HYPO)

        target_event = v["changes"].get("event_name", {}).get("to")
        target_hypo = v["changes"].get("hypothesis", {}).get("to")

        patch = {}
        if target_event and cur_event != target_event:
            patch[F_EVENT] = target_event
        if target_hypo and cur_hypo != target_hypo:
            patch[F_HYPO] = target_hypo

        if not patch:
            skipped_already_fixed += 1
            results.append({"person_id": pid, "email": v.get("email"), "status": "already_correct",
                             "current": {"event_name": cur_event, "hypothesis": cur_hypo}})
            print(f"  SKIP  {pid} ({v.get('email')}) - already correct since dry-run")
            continue

        row = {"person_id": pid, "email": v.get("email"), "before": {"event_name": cur_event, "hypothesis": cur_hypo},
               "intended": patch}
        if live:
            wst, wr = pd(f"/api/v2/persons/{pid}", "PATCH", {"custom_fields": patch})
            row["http"] = wst
            row["status"] = "written" if wst < 300 else "failed"
            if wst < 300:
                ok += 1
            else:
                failed += 1
                row["error"] = str(wr)[:200]
            print(f"  {'OK   ' if wst < 300 else 'FAIL '} {pid} ({v.get('email')}): {patch}  http={wst}")
            time.sleep(0.2)
        else:
            row["status"] = "would_write"
            ok += 1
            print(f"  WOULD_WRITE {pid} ({v.get('email')}): {patch}")
        results.append(row)

    print(f"\n{'written' if live else 'would_write'}: {ok}   already_correct(skipped): {skipped_already_fixed}   failed: {failed}")
    out_path = os.path.join(DISC, "melisa_apply_373_log.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"write_mode": WRITE_MODE, "ok": ok, "skipped_already_fixed": skipped_already_fixed,
                    "failed": failed, "excluded_manual": excluded, "rows": results}, f, indent=2, ensure_ascii=False)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
