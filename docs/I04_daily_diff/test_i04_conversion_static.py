"""Static (no network) regression test for i04_diff.classify_conversion -- the Check 1
deal-conversion arm added 2026-08-27. Fixtures are the REAL 13 "DELETED" departures from today's
run (audit-artifacts/i04_diff_2026-08-27.json), each paired with its real matching deal, verified
live 2026-08-27 via /v1/persons/{id}/deals (see the task-log for the fetch). 6 of the 13 also carry
the real delete-webhook timestamp already cross-referenced in that day's post; the other 7 fall
inside the 08-21->08-26 un-snapshotted gap and have no webhook record, so they exercise the
window-only fallback path -- both tiers get covered by real data, nothing synthetic.

USAGE   python test_i04_conversion_static.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i04_diff import classify_conversion

WINDOW_START = "2026-08-20T00:00:00Z"
WINDOW_END = "2026-08-27T23:59:59Z"

# lead, person, deal_add_time, delete_ts (None where the webhook record falls in the unsnapshotted gap)
REAL_13 = [
    ("00849590", 85482, "2026-08-27 03:33:22", "2026-08-27T03:33:23.419Z"),
    ("0c614b90", 84526, "2026-08-24 17:55:03", None),
    ("23d66bd0", 51673, "2026-08-27 03:35:13", "2026-08-27T03:35:15.012Z"),
    ("2e402210", 70481, "2026-08-26 11:09:00", "2026-08-26T11:09:01.368Z"),
    ("36874c90", 85052, "2026-08-24 17:51:50", None),
    ("4b2c6030", 84508, "2026-08-25 17:23:05", None),
    ("76002970", 85515, "2026-08-24 17:50:08", None),
    ("7653c850", 70479, "2026-08-26 11:06:14", "2026-08-26T11:06:15.025Z"),
    ("946339f0", 84069, "2026-08-24 17:58:35", None),
    ("9c558d50", 84747, "2026-08-27 03:36:40", "2026-08-27T03:36:42.025Z"),
    ("a179e760", 83033, "2026-08-24 17:56:33", None),
    ("a8215a00", 84949, "2026-08-27 03:31:36", "2026-08-27T03:31:38.751Z"),
    ("bce52e40", 84372, "2026-08-24 17:55:51", None),
]

failures = []


def check(cond, label):
    status = "ok" if cond else "FAIL"
    print("  %-4s - %s" % (status, label))
    if not cond:
        failures.append(label)


print("classify_conversion: today's real 13 must all classify CONVERTED")
timestamp_matches = 0
window_matches = 0
for lead, person, add_time, delete_ts in REAL_13:
    ev = classify_conversion(add_time, WINDOW_START, WINDOW_END, delete_ts_iso=delete_ts)
    check(ev is not None, "%s (p%s) must be CONVERTED, got %r" % (lead, person, ev))
    if ev and ev["match"] == "timestamp":
        timestamp_matches += 1
    elif ev and ev["match"] == "window":
        window_matches += 1

check(timestamp_matches == 6, "6 of 13 must resolve via the tight timestamp match (got %d)" % timestamp_matches)
check(window_matches == 7, "7 of 13 must resolve via the window fallback (got %d)" % window_matches)

print("\nclassify_conversion: the tight match must actually be tight, not just 'same day'")
# same day, but 90 minutes off -- must NOT satisfy the timestamp tier, only the (weaker) window tier
ev = classify_conversion("2026-08-26 12:36:14", WINDOW_START, WINDOW_END, delete_ts_iso="2026-08-26T11:06:15.025Z")
check(ev is not None and ev["match"] == "window", "90-minute-off deal must fall back to window match, not a false tight match")

print("\nclassify_conversion: a genuine loss (no deal at all) must NOT be classified converted")
ev = classify_conversion(None, WINDOW_START, WINDOW_END, delete_ts_iso="2026-08-26T11:06:15.025Z")
check(ev is None, "no deal_add_time at all must return None, never a false CONVERTED")

print("\nclassify_conversion: a deal outside the diff window entirely must NOT count")
ev = classify_conversion("2026-06-01 09:00:00", WINDOW_START, WINDOW_END, delete_ts_iso=None)
check(ev is None, "a deal from months before the window must not satisfy the window fallback")

print("\nclassify_conversion: boundary -- exactly at the tolerance must still match, one second over must not")
ev_in = classify_conversion("2026-08-26 11:07:15", WINDOW_START, WINDOW_END, delete_ts_iso="2026-08-26T11:06:15.000Z")
check(ev_in is not None and ev_in["match"] == "timestamp", "exactly 60s must still be a tight match")
ev_out = classify_conversion("2026-08-26 11:07:16", WINDOW_START, WINDOW_END, delete_ts_iso="2026-08-26T11:06:15.000Z")
check(ev_out is None or ev_out["match"] != "timestamp", "61s must NOT be a tight match (falls back to window instead)")

print()
if failures:
    print("%d FAILED:" % len(failures))
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
