#!/usr/bin/env python3
"""The 111 person_ids to backfill as sales_personal_outreach (Nik's 2026-09-15 GO, roster-owned =
protected, no source/lead check) -- hand-extracted from the full-audit evidence agent's report,
cross-checked: 44 Mario-EVT + 57 Noah-EVT + 10 Noah-SURFE = 111; 44+57=101 matches the agent's own
"101 EVT" total exactly; 10 matches "10 SURFE" exactly. The remaining 32 of the original 143 are
KNOWN (already reply_dnc) and deliberately excluded here, matching "not already covered by
reply_dnc" -- this also naturally excludes Person-8768306e (86369) and Person-b27663e9 (86071), both
already reply_dnc rows this session separately tombstoned as false positives, without needing any
special-case logic.
"""

MARIO_EVT = [
    86655, 86653, 86643, 86618, 86599, 86593, 86585, 86583, 86574, 86570,
    86562, 86556, 86551, 86546, 86536, 86518, 86516, 86488, 86487, 86486,
    86480, 86475, 86471, 86468, 86467, 86462, 86461, 86419, 86416, 86415,
    86409, 86408, 86405, 86404, 86398, 86397, 86396, 86388, 86347, 86343,
    86337, 86328, 86320, 86313,
]
NOAH_EVT = [
    86509, 86506, 86502, 86501, 86498, 86489, 86453, 86452, 86451, 86450,
    86445, 86444, 86437, 86429, 86425, 86423, 86389, 86384, 86376, 86367,
    86310, 86309, 86307, 86303, 86301, 86290, 86287, 86282, 86272, 86261,
    86257, 86255, 86253, 86250, 86247, 86239, 86227, 86225, 86212, 86202,
    86189, 86186, 86166, 86165, 86143, 86119, 86118, 86110, 86109, 86107,
    86104, 86102, 86101, 86088, 86087, 86035, 86024,
]
NOAH_SURFE = [86201, 86153, 86152, 86145, 86136, 86132, 86084, 86026, 86022, 86021]

assert len(MARIO_EVT) == 44
assert len(NOAH_EVT) == 57
assert len(NOAH_SURFE) == 10
assert len(MARIO_EVT) + len(NOAH_EVT) == 101, "must match the agent's own 101-EVT total"

BACKFILL = (
    [{"person_id": p, "owner": "Mario", "kind": "EVT"} for p in MARIO_EVT]
    + [{"person_id": p, "owner": "Noah", "kind": "EVT"} for p in NOAH_EVT]
    + [{"person_id": p, "owner": "Noah", "kind": "SURFE"} for p in NOAH_SURFE]
)
assert len(BACKFILL) == 111
assert len({b["person_id"] for b in BACKFILL}) == 111, "no duplicate person_ids"
