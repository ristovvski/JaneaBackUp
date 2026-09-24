"""INVESTIGATION step 1b - full person changelog, hunting for the entry at the EXACT Slack-post
timestamp (2026-05-29, ~17:15-17:19 UTC / 20:15-20:19 IDT). The person's own update_time has since
been overwritten by later events (a June-1 cluster, some July touches) - the burst-time entry has to
be found by paging the changelog, not read off update_time.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-invest/1.0"

# person_id, name, exact Slack post unix ts (from the search results)
TARGETS = [
    (73743, "Person-333362aa", 1780074534.638509, "b2ecfa40-3e8a"),
    (68269, "Person-15c42271", 1780074930.374219, "13bdaaa0-180b"),
    (68412, "Person-b593f844", 1780074937.548329, "3fb836e0-1d81"),
    (64786, "Person-91310ef1", 1780075139.070549, "20473110-34ef"),
    (62675, "Person-a06e7c04", 1780075145.951219, "ecd18250-faea"),
    (64763, "Person-a9d19c0c", 1780075155.774389, "47f28490-0130"),
    (62679, "Ramanpreet Khinda", 1780075158.193239, "ad38e480-faef"),
]


def pd(path):
    r = urllib.request.Request("https://api.pipedrive.com" + path,
                               headers={"x-api-token": PDT, "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=90) as x:
            return 200, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


for pid, name, post_ts, prefix in TARGETS:
    post_time = datetime.fromtimestamp(post_ts, tz=timezone.utc)
    print("=" * 100)
    print(f"[{prefix}] person={pid} {name}   Slack post at {post_time.isoformat()}")
    print("=" * 100)
    entries, start = [], 0
    while True:
        st, d = pd(f"/v1/persons/{pid}/changelog?start={start}&limit=100")
        if st != 200:
            print(f"  changelog fetch failed: {st} {d}")
            break
        rows = d.get("data") or []
        entries.extend(rows)
        more = ((d.get("additional_data") or {}).get("pagination") or {})
        start += len(rows)
        if not rows or not more.get("more_items_in_collection"):
            break
    print(f"  changelog entries total: {len(entries)}")

    # sort by time, find closest to the post
    def parse(t):
        try:
            return datetime.fromisoformat(t.replace(" ", "T")).replace(tzinfo=timezone.utc)
        except Exception:
            return None
    dated = [(parse(e.get("time")), e) for e in entries]
    dated = [(t, e) for t, e in dated if t]
    dated.sort(key=lambda x: x[0])

    # entries within +/- 15 minutes of the post
    window = [(t, e) for t, e in dated if abs((t - post_time).total_seconds()) <= 900]
    print(f"  entries within +/-15min of the Slack post: {len(window)}")
    for t, e in window:
        print(f"    {t.isoformat()}  field={e.get('field_key')}  "
              f"source={e.get('change_source')}  bulk={e.get('is_bulk_update_flag')}")
        print(f"      old={str(e.get('old_value'))[:80]!r} -> new={str(e.get('new_value'))[:80]!r}")
        ua = e.get("change_source_user_agent")
        if ua:
            print(f"      user_agent={ua[:120]!r}")
        actor = e.get("actor_user_id") or e.get("user_id")
        if actor:
            print(f"      actor_user_id={actor}")

    if not window and dated:
        # show the nearest few regardless of window, for context
        dated_by_dist = sorted(dated, key=lambda x: abs((x[0] - post_time).total_seconds()))
        print("  no entry within 15min - nearest 3 entries overall:")
        for t, e in dated_by_dist[:3]:
            delta_h = (t - post_time).total_seconds() / 3600
            print(f"    {t.isoformat()}  ({delta_h:+.1f}h from post)  field={e.get('field_key')}  "
                  f"source={e.get('change_source')}")
    print()
