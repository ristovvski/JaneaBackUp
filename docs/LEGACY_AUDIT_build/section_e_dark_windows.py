#!/usr/bin/env python3
"""Legacy Audit — Section E: #lead-processing dark windows vs reply volume (READ-ONLY, local).

Reuses the existing full-history channel harvest from the earlier duplicate-forensics task
(DISCOVERY/lead_processing_harvest.jsonl, 1,641 messages, 2024-12-19 -> 2026-08-05) rather than
re-pulling the whole channel - same underlying data, no reason to hit Slack's API twice for it.

Finds gaps between consecutive channel messages exceeding a threshold ("dark windows" - stretches
with no team-visible alert at all), then cross-references each dark window against Section A's
reply timestamps (section_ab_raw_sweep.jsonl) to count replies that happened while the channel was
silent - i.e. replies the team had zero chance of seeing a notification for.
"""
import json, os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "evidence")
DISC = os.path.join(HERE, "..", "DISCOVERY")

DARK_HOURS = 24.0   # hard threshold: a full day with zero team-visible alert
SOFT_HOURS = 6.0    # softer threshold, reported separately


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main():
    msgs = load_jsonl(os.path.join(DISC, "lead_processing_harvest.jsonl"))
    msgs = [m for m in msgs if m.get("ts")]
    msgs.sort(key=lambda m: float(m["ts"]))
    print(f"channel harvest: {len(msgs)} messages, "
          f"{datetime.fromtimestamp(float(msgs[0]['ts']), tz=timezone.utc).isoformat()} -> "
          f"{datetime.fromtimestamp(float(msgs[-1]['ts']), tz=timezone.utc).isoformat()}")

    gaps = []
    for a, b in zip(msgs, msgs[1:]):
        t0, t1 = float(a["ts"]), float(b["ts"])
        hours = (t1 - t0) / 3600.0
        if hours >= SOFT_HOURS:
            gaps.append({"start_ts": t0, "end_ts": t1, "hours": round(hours, 1),
                         "start_iso": datetime.fromtimestamp(t0, tz=timezone.utc).isoformat(),
                         "end_iso": datetime.fromtimestamp(t1, tz=timezone.utc).isoformat(),
                         "dark": hours >= DARK_HOURS})

    dark = [g for g in gaps if g["dark"]]
    print(f"\ngaps >= {SOFT_HOURS}h: {len(gaps)}   of which >= {DARK_HOURS}h (dark): {len(dark)}")
    print(f"total dark-window hours: {sum(g['hours'] for g in dark):.0f}h "
          f"({sum(g['hours'] for g in dark)/24:.1f} days)")

    # cross-reference against Section A replies
    sweep = load_jsonl(os.path.join(EVID, "section_ab_raw_sweep.jsonl"))
    all_replies = []
    for c in sweep:
        for r in c.get("replies", []):
            if r.get("time"):
                try:
                    t = datetime.fromisoformat(r["time"].replace("Z", "+00:00")).timestamp()
                    all_replies.append({**r, "campaign_id": c["campaign_id"],
                                        "campaign_name": c["campaign_name"], "epoch": t})
                except Exception:
                    pass
    print(f"\nreply records with parseable timestamps: {len(all_replies)} / "
          f"{sum(len(c.get('replies',[])) for c in sweep)}")

    replies_in_dark = []
    for g in dark:
        hits = [r for r in all_replies if g["start_ts"] <= r["epoch"] <= g["end_ts"]]
        if hits:
            g["replies_during_window"] = [{"email": h["email"], "campaign": h["campaign_name"],
                                           "time": h["time"]} for h in hits]
            replies_in_dark.extend(hits)

    print(f"\n=== SECTION E — FIRST NUMBERS ===")
    print(f"dark windows (>= {DARK_HOURS}h, no team-visible message): {len(dark)}")
    print(f"replies that landed during a dark window: {len(replies_in_dark)}")
    if dark:
        top_dark = sorted(dark, key=lambda g: -g["hours"])[:10]
        print(f"\nlongest 10 dark windows:")
        for g in top_dark:
            n = len(g.get("replies_during_window", []))
            print(f"  {g['start_iso'][:16]} -> {g['end_iso'][:16]}  {g['hours']:>6.1f}h  "
                  f"replies_missed={n}")

    out = {
        "harvest_range": {"start": msgs[0]["ts"], "end": msgs[-1]["ts"]},
        "dark_threshold_hours": DARK_HOURS, "soft_threshold_hours": SOFT_HOURS,
        "dark_window_count": len(dark), "total_dark_hours": round(sum(g["hours"] for g in dark), 1),
        "replies_during_dark_windows": len(replies_in_dark),
        "dark_windows": dark,
        "caveat": "harvest covers 2024-12-19 -> 2026-08-05 (the pre-existing duplicate-forensics "
                  "pull); this week's window (2026-08-06 onward) checked separately as part of "
                  "Section F's 'after' baseline, not included in this dark-window count.",
    }
    with open(os.path.join(EVID, "section_e_first_numbers.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote evidence/section_e_first_numbers.json")


if __name__ == "__main__":
    main()
