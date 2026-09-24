# -*- coding: utf-8 -*-
"""Archive pass, 2026-09-03. Deactivate + rename with an ARCHIVE__ prefix. NEVER delete.

Every workflow's exact pre-change definition is written to backups/ first, so the rename and the
deactivation are both reversible from a file.

`WF-1-DO NOT USE` additionally has its webhook path neutralised: an inactive workflow serves no
production webhook, but changing the path means the old URL 404s even if somebody reactivates it.
The node itself is kept - other nodes reference it by name, and this is a preserved artifact.

Usage: python archive.py [--apply]
"""
import json, copy, os, sys

exec(open(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Desktop-----------\15a1459d-184a-4069-b4d9-110080844861\scratchpad\s2\lib.py", encoding="utf-8").read())

OUT = os.path.dirname(os.path.abspath(sys.argv[0]))
DEAD_PATH = "{{WEBHOOK_ARCHIVED_DO_NOT_USE_2026_09_03}}"

# id -> (current name, reason recorded in the docs)
PLAN = [
    ("XWtxUzBgNJuguJlg", "smartlead_observability_readonly",
     "never finished - its campaign id is still the literal placeholder text; superseded by WF-2S/WF-2R"),
    ("NNOVii5ImjFKDSM0", "WF-1-DO NOT USE",
     "previous generation of WF-1 (89 nodes); webhook path neutralised so it cannot be reached"),
    ("rnPaPoVQNe2SShkc", "HeyReach — Phase 0 Payload Capture",
     "pre-WF-1 scaffolding: acknowledge the webhook and record the payload shape"),
    ("K2M1Z0m1gKX6LdFI", "DNC__NormalizeIdentity__v1",
     "nothing calls it; the same logic is inlined in the ledger, the read-only twin and the gate"),
    ("fZl1vpRsQ6Fko3sB", "dnc_gate_queue_drainer",
     "the gate no longer queues anything - the queue path was removed 2026-09-02"),
    ("alpy9rsunqnFwQml", "dnc_expiry_job",
     "deliberately retired when time-based expiry was killed (2026-08-31)"),
    ("CUpl8PVOOYXMysVN", "dnc_expiry_null_oneshot",
     "one-shot: removed expires_at from every registry row on 2026-08-31"),
    ("hhdnug5xdFLAxrOg", "dnc_s4_event_populations",
     "one-shot: bulk campaign load, run once on 2026-08-14"),
    ("LQRfmEl4Wv0qpXsI", "dnc_label_reversal",
     "one-shot repair tool, last used 2026-08-14; dry-run by default"),
    ("1fpep0U4XC8KNzta", "dnc_s3_surfe_backfill",
     "one-shot historical backfill; never run"),
    ("8sT1XjDDVmrz05CA", "dnc_i04_daily_summary",
     "retired 2026-09-03 - I-04 became a change log (rulebook R-G)"),
    ("gjVZkkvm05jj8CNM", "dnc_i04_weekly_reconciliation",
     "retired 2026-09-03 - never ran once; its full-estate walk is the out-of-memory shape"),
]
KEEP = ["WF-0 - Discovery", "DNC__CheckLedger__v1", "dnc_check_service",
        "dnc_s1_responded_to_dnc", "dnc_s2_meeting_to_dnc", "dnc_projections_sweep"]


def main():
    apply = "--apply" in sys.argv
    os.makedirs(os.path.join(OUT, "backups"), exist_ok=True)
    live = {w["id"]: w for w in all_workflows()}

    # refuse to archive anything another workflow still points at
    for wid, name, _ in PLAN:
        for w in live.values():
            if w["id"] == wid:
                continue
            if wid in json.dumps(w.get("nodes"), ensure_ascii=False):
                raise SystemExit("REFUSING: %s is still referenced by %s" % (name, w["name"]))

    rows = []
    for wid, name, reason in PLAN:
        w = live.get(wid)
        assert w is not None, "missing " + name
        assert w["name"] == name, "name drifted: expected %r got %r" % (name, w["name"])
        json.dump(w, open(os.path.join(OUT, "backups", "%s__%s.json" % (
            name.replace(" ", "_").replace("/", "_"), wid)), "w", encoding="utf-8"),
            ensure_ascii=False, indent=1)

        wf = copy.deepcopy(w)
        newname = "ARCHIVE__" + name
        wf["name"] = newname
        pathnote = ""
        if wid == "NNOVii5ImjFKDSM0":
            for n in wf["nodes"]:
                if n["type"].endswith(".webhook"):
                    pathnote = "%s -> %s" % ((n.get("parameters") or {}).get("path"), DEAD_PATH)
                    n["parameters"]["path"] = DEAD_PATH
        rows.append((wid, name, newname, bool(w.get("active")), len(w["nodes"]), reason, pathnote))

        if apply:
            if w.get("active"):
                d = deactivate(wid)
                assert d.status_code < 300, "deactivate failed for %s: %s" % (name, d.text[:200])
            r, dropped = put_wf(wid, wf)
            assert r.status_code < 300, "PUT failed for %s: %s" % (name, r.text[:300])
            back = get_wf(wid)
            assert back["name"] == newname and back.get("active") is False, \
                "readback mismatch for %s: name=%r active=%r" % (name, back["name"], back.get("active"))

    print("%-8s %-36s -> %-46s %s" % ("was", "name", "archived as", "nodes"))
    for wid, old, new, wasactive, nodes, reason, pathnote in rows:
        print("%-8s %-36s -> %-46s %d%s" % ("ACTIVE" if wasactive else "off", old[:36], new[:46],
                                            nodes, "   [path " + pathnote + "]" if pathnote else ""))
    if apply:
        after = all_workflows()
        print("\nestate now: %d workflows, %d active" % (len(after), sum(1 for w in after if w.get("active"))))
        print("KEEP list untouched:")
        for k in KEEP:
            m = [w for w in after if w["name"] == k]
            print("   %-28s %s" % (k, ("present, " + ("ACTIVE" if m[0].get("active") else "inactive")) if m else "MISSING"))
        stray = [w["name"] for w in after if w["name"].startswith("ARCHIVE__")]
        print("archived total: %d" % len(stray))


if __name__ == "__main__":
    main()
