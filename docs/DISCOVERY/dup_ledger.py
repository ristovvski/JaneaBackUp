#!/usr/bin/env python3
"""Local, read-only processing of the harvested #lead-processing JSONL. No network calls.
Builds the duplicate ledger (same lead identity + same template within window), scoped to the
requested reporting window (2026-06-05 -> 2026-08-05), and the Lilla Szabo duplicate check.
Identity = lead_uuid when present, else normalized lead_name (some old rows have no /leads/inbox/
link, e.g. very early Zap posts or malformed titles)."""
import json, os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
recs = [json.loads(l) for l in open(os.path.join(HERE, "lead_processing_harvest.jsonl"), encoding="utf-8")]

# Normalize poster: same bot, two display names historically (per harvest agent's own finding)
def norm_poster(r):
    if r["poster_id"] == "B025Y6BBBLJ":
        return "ZapierBot(B025Y6BBBLJ)"
    return r["poster_name"] + "(" + r["poster_id"] + ")"

WINDOW_START = datetime(2026, 6, 5, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 8, 6, tzinfo=timezone.utc)  # inclusive of today

for r in recs:
    r["ts_f"] = float(r["ts"])
    r["dt"] = datetime.fromtimestamp(r["ts_f"], tz=timezone.utc)
    r["poster_key"] = norm_poster(r)
    r["identity"] = r["lead_uuid"] or ("name:" + (r["lead_name"] or r["raw_text"][:60]).strip().lower())

recs.sort(key=lambda r: r["ts_f"])
in_window = [r for r in recs if WINDOW_START <= r["dt"] <= WINDOW_END]
print(f"total records: {len(recs)} | in reporting window (Jun5-Aug6): {len(in_window)}")
print(f"full harvest span: {recs[0]['dt'].isoformat()} .. {recs[-1]['dt'].isoformat()}")

KILL_TS = datetime(2026, 8, 5, 11, 28, 42, tzinfo=timezone.utc)

# --- group by (poster_key, template, identity) to find duplicate clusters ---
groups = {}
for r in in_window:
    if r["template"] == "other":
        continue
    key = (r["poster_key"], r["template"], r["identity"])
    groups.setdefault(key, []).append(r)

tight_pairs = []   # <=120s
near_pairs = []    # 120s .. 24h
same_day_far = []  # >24h (different-day repeats)

for key, items in groups.items():
    if len(items) < 2:
        continue
    items.sort(key=lambda r: r["ts_f"])
    for i in range(1, len(items)):
        a, b = items[i - 1], items[i]
        gap = b["ts_f"] - a["ts_f"]
        pair = {"poster": key[0], "template": key[1], "identity": key[2],
                "lead_name": b["lead_name"], "campaign": b["campaign"],
                "ts_a": a["dt"].isoformat(), "ts_b": b["dt"].isoformat(),
                "gap_seconds": round(gap, 3),
                "permalink_a": f"https://app.slack.com/client/T039YQN6E/C07LTD8UT70/p{a['ts'].replace('.', '')}",
                "permalink_b": f"https://app.slack.com/client/T039YQN6E/C07LTD8UT70/p{b['ts'].replace('.', '')}"}
        if gap <= 120:
            tight_pairs.append(pair)
        elif gap <= 86400:
            near_pairs.append(pair)
        else:
            same_day_far.append(pair)

print(f"\nTIGHT duplicates (<=120s): {len(tight_pairs)}")
print(f"NEAR pairs (2min-24h): {len(near_pairs)}")
print(f"FAR repeats (>24h, different-day): {len(same_day_far)}")

# post-kill check
post_kill_tight = [p for p in tight_pairs if datetime.fromisoformat(p["ts_b"]) > KILL_TS]
print(f"\nTIGHT duplicates with ts_b AFTER kill (2026-08-05T11:28:42Z): {len(post_kill_tight)}")
for p in post_kill_tight:
    print(" ", p["ts_a"], "->", p["ts_b"], p["poster"], p["lead_name"])

# gap distribution for tight pairs (to confirm the "zap-internal" signature: sub-second gaps)
subsec = sum(1 for p in tight_pairs if p["gap_seconds"] < 1)
print(f"\nof {len(tight_pairs)} tight pairs, {subsec} have gap < 1 second (zap-internal signature)")
gaps_1_120 = [p for p in tight_pairs if p["gap_seconds"] >= 1]
print(f"{len(gaps_1_120)} tight pairs have gap 1-120s (worth individual review):")
for p in gaps_1_120[:20]:
    print(" ", p["gap_seconds"], "s |", p["ts_b"], "|", p["poster"], "|", p["lead_name"])

# Lilla Szabo (Make-side) duplicate check across FULL harvest, not just window
lilla = [r for r in recs if r["poster_name"] == "Lilla Szabo" and r["template"] == "make_responded_label"]
lilla_groups = {}
for r in lilla:
    lilla_groups.setdefault(r["identity"], []).append(r)
lilla_dupe_clusters = {k: v for k, v in lilla_groups.items() if len(v) > 1}
print(f"\nLilla Szabo (Make) posts total: {len(lilla)}; distinct identities: {len(lilla_groups)}; "
      f"identities with >1 post: {len(lilla_dupe_clusters)}")
for k, v in list(lilla_dupe_clusters.items())[:10]:
    print("  ", k, [x["dt"].isoformat() for x in v])

# Dealbot (third source, pre-2025) — quick characterization
dealbot = [r for r in recs if r["poster_name"] == "Dealbot by Pipedrive"]
print(f"\nDealbot by Pipedrive posts: {len(dealbot)} | span: "
      f"{dealbot[0]['dt'].isoformat() if dealbot else 'n/a'} .. {dealbot[-1]['dt'].isoformat() if dealbot else 'n/a'}")

# weekly counts for the timeline (ZapierBot tight-dup events only, by week of ts_b)
from collections import Counter
def week_key(dt):
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"

weekly = Counter(week_key(datetime.fromisoformat(p["ts_b"])) for p in tight_pairs)
print("\nWeekly tight-duplicate counts (ZapierBot class), Jun5-Aug6 window:")
for wk in sorted(weekly):
    print(f"  {wk}: {weekly[wk]}")

# dump structured outputs for downstream (report writing + chart)
out = {
    "window": {"start": WINDOW_START.isoformat(), "end": WINDOW_END.isoformat()},
    "kill_ts": KILL_TS.isoformat(),
    "counts": {"total_records": len(recs), "in_window": len(in_window),
               "tight": len(tight_pairs), "near": len(near_pairs), "far": len(same_day_far),
               "post_kill_tight": len(post_kill_tight)},
    "weekly_tight": dict(weekly),
    "tight_pairs": tight_pairs,
    "near_pairs": near_pairs,
    "far_pairs": same_day_far,
    "lilla_total": len(lilla), "lilla_dupe_clusters": len(lilla_dupe_clusters),
    "dealbot_count": len(dealbot),
    "dealbot_span": [dealbot[0]["dt"].isoformat(), dealbot[-1]["dt"].isoformat()] if dealbot else None,
}
with open(os.path.join(HERE, "dup_ledger_output.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("\nwrote dup_ledger_output.json")

# distinct lead_uuids among tight pairs -> feed the Pipedrive changelog cross-check batch
uuids = sorted({p["identity"] for p in tight_pairs if p["identity"].count("-") == 4})
with open(os.path.join(HERE, "tight_pair_uuids.json"), "w", encoding="utf-8") as f:
    json.dump(uuids, f, indent=2)
print(f"distinct lead UUIDs among tight pairs (for changelog cross-check): {len(uuids)}")
