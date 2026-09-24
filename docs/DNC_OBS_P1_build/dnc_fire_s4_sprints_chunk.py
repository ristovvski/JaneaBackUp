"""
Same driver as dnc_fire_s4_chunk.py, extended scope (Nik, 2026-08-14 ownership call): S4 covers the
7 Smartlead "Sales Sprint" campaigns too, same event_contacted shape, no HeyReach counterpart for
sprints. Reuses every function from the AI4 driver; only the CAMPAIGNS list differs.

Populations confirmed live before firing (campaign/leads total_leads field, same discipline as the
original AI4 sanity check): 1962 + 3145 + 259 + 45 + 362 + 23 + 466 = 6262.
"""
import dnc_fire_s4_chunk as base

base.CAMPAIGNS = [
    ("smartlead", 3565651, "[Sales Sprint] Sales Sprint 2026 - London - Catch-alls"),
    ("smartlead", 3565502, "[Sales Sprint] Sales Sprint 2026 - London - Valids"),
    ("smartlead", 3172719, "[Sales Sprint] Sales Sprint 2026 - Switzerland"),
    ("smartlead", 2958933, "[Sales Sprint] European Sales Sprint 2026 - Munich and Berlin"),
    ("smartlead", 2449716, "[Sales Sprint] European Sales Sprint 2025 - Catch-all"),
    ("smartlead", 2449693, "[Sales Sprint] European Sales Sprint 2025 - Valids"),
    ("smartlead", 2358474, "[Sales Sprint] Sales Sprint London"),
]

if __name__ == "__main__":
    base.main()
