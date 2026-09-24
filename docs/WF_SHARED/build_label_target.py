# -*- coding: utf-8 -*-
"""Embeds WF_SHARED/label_target.js into WF-2's two label-body nodes, and adds the Disqualified
label id to WF-2's CONFIG.

The rule engine is not retyped here - label_target.js is read verbatim and embedded, so the two
nodes and test_label_target.js can never drift apart. That drift is exactly what produced the
2026-09-02 defect this replaces.

Usage:
  python build_label_target.py            # dry run: writes patched JSON, changes nothing live
  python build_label_target.py --apply    # PUT to n8n, with backup and readback
"""
import json, os, sys, copy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Desktop-----------\15a1459d-184a-4069-b4d9-110080844861\scratchpad")
import n8nlib

WF2 = "jp7rum9Z0YDJkQWv"
OUTDIR = os.path.join(os.path.dirname(HERE), "WAVE0_2026-09-02")
DISQUALIFIED = "98008920-e942-11ef-b360-57187fe024ea"   # Pipedrive lead label "Disqualified"

shared = open(os.path.join(HERE, "label_target.js"), encoding="utf-8").read()
shared = shared.split("if (typeof module !==")[0].rstrip()   # n8n has no module system

PREAMBLE = """
const CFG = $('CONFIG').item.json;
const F = CFG.fields;
// B16: prefer the enriched copy; fall back on paths where enrichment never ran.
const n = (() => {
  try { const e = $('Apply Enrich').item.json.__enriched; if (e && e.lead) return e; } catch (x) {}
  return $('Normalize').item.json;
})();
const omit = (o) => { for (const k of Object.keys(o)) { const v = o[k]; if (v === '' || v === null || v === undefined) delete o[k]; } return o; };

// B12: $json does NOT survive an HTTP node - after a write it is the API response and every
// __ field is gone. Recover context from the node that OWNS it, by name; $json is an override only.
const fromNode = (nm) => { try { return $(nm).item.json || {}; } catch (e) { return {}; } };
const ctx = (key, ...names) => {
  if ($json && $json[key] !== undefined && $json[key] !== null) return $json[key];
  for (const nm of names) { const v = fromNode(nm)[key]; if (v !== undefined && v !== null) return v; }
  return undefined;
};
const LABELS = { cold: CFG.labels.cold, connected: CFG.labels.connected,
                 responded: CFG.labels.responded, dnc: CFG.labels.dnc,
                 disqualified: CFG.labels.disqualified };
"""

REPLY_TAIL = """
// ---- the reply path -------------------------------------------------------------------------
// OOO-GATE: Smartlead's own reply_category, available from Normalize long before the alert
// decision and independent of our LLM, so an LLM outage cannot leak OOO alerts. FAIL-OPEN:
// unknown/missing category => treat as a REAL reply.
const __isOOO = (() => {
  try {
    const c = String(($('Normalize').item.json || {}).reply_category ?? '').trim().toLowerCase();
    if (!c) return false;
    const auto = ['out of office', 'ooo', 'auto reply', 'auto-reply', 'automatic reply',
                  'autoreply', 'vacation', 'away'];
    return auto.indexOf(c) !== -1;
  } catch (e) { return false; }
})();
const __isBounce = (() => { try { return $('Normalize').item.json.__is_bounce === true; }
                            catch (e) { return false; } })();
const __cat = (() => { try { const c = $('Classify Parse').item.json.__category;
                             return (c && c !== 'Uncategorized') ? c : null; } catch (e) { return null; } })();
const __isDnc = (ctx('__dnc_label', 'Mark DNC', 'U Mark DNC') === true)
             || (() => { try { return $('Classify Parse').item.json.__is_dnc === true; }
                         catch (e) { return false; } })();

const _lbl = ctx('__lead_labels', 'Mark DNC', 'Merge Reply Ctx', 'Lead Resolve', 'U Mark DNC', 'U Lead Select');
const existing = Array.isArray(_lbl) ? _lbl.slice() : [];
const LT = labelTargetV1({ event: 'REPLY', category: __cat, is_dnc: __isDnc,
                           is_bounce: __isBounce, is_ooo: __isOOO,
                           existing: existing, labels: LABELS });
const body = { label_ids: LT.union };
const _leadId = ctx('__lead_id', 'Mark DNC', 'Merge Reply Ctx', 'Lead Resolve', 'U Mark DNC', 'U Lead Select') ?? null;
return [{ json: { ...$json, __lead_id: _leadId, __body: body,
  // B13: no lead -> no PATCH. PATCH /v1/leads/undefined -> 400 killed the whole execution.
  __skip: !LT.changed || !_leadId, __label_union: LT.union,
  __label_case: LT['case'], __responded_written: LT.responded, __implied_label: LT.implied,
  __opted_out: existing.indexOf(LABELS.dnc) !== -1,
  __intended: { node: 'Lead Labels Union (shared: labelTargetV1)', method: 'PATCH',
                url: '/v1/leads/' + (_leadId ?? '{none}'), body } } }];
"""

UNSUB_TAIL = """
// ---- the unsubscribe path -------------------------------------------------------------------
// An unsubscribe IS an explicit stop request and a deliberate human act, so it earns
// '3. Responded' AND 'DO NOT CONTACT' - in this one PATCH. Handover is suppressed by the
// DO NOT CONTACT label, not by withholding the truth about whether they answered us.
const _lbl = ctx('__lead_labels', 'Mark DNC', 'Merge Reply Ctx', 'Lead Resolve', 'U Mark DNC', 'U Lead Select');
const existing = Array.isArray(_lbl) ? _lbl.slice() : [];
const LT = labelTargetV1({ event: 'UNSUB', existing: existing, labels: LABELS });
const body = { label_ids: LT.union };
const _leadId = ctx('__lead_id', 'Mark DNC', 'Merge Reply Ctx', 'Lead Resolve', 'U Mark DNC', 'U Lead Select') ?? null;
return [{ json: { ...$json, __lead_id: _leadId, __body: body,
  __skip: !LT.changed || !_leadId, __label_union: LT.union,
  __label_case: LT['case'], __responded_written: LT.responded, __implied_label: LT.implied,
  __intended: { node: 'U Lead DNC Label (shared: labelTargetV1)', method: 'PATCH',
                url: '/v1/leads/' + (_leadId ?? '{none}'), body } } }];
"""

FORWARD_CLAIM = """
// FORWARD-CLAIM: record that the email actually WENT. Reached from four paths - only the one
// through `SL Forward Email` may claim, and the lookup throws on the others, which is what
// distinguishes them. `ok !== true` must NOT claim, or a failed send becomes unrepeatable.
try {
  const __f = $('SL Forward Email').item.json;
  if (__f && __f.ok === true) {
    const __k = $('Dedupe').item.json.__dedupe_key;
    if (__k) {
      const __sd = $getWorkflowStaticData('global');
      (__sd.wf2_seen = __sd.wf2_seen || {})['F|' + __k] = Math.floor(Date.now() / 1000);
    }
  }
} catch (e) { /* forward did not run on this path */ }
"""

HEADER = ("// GENERATED - embedded from WF_SHARED/label_target.js by build_label_target.py.\n"
          "// Do not edit here: edit the shared file and rebuild, or the two label paths drift\n"
          "// apart again (that drift is what wrote '3. Responded' onto opt-outs).\n")

REPLY_BODY = ("const __items = (() => {\n" + HEADER + PREAMBLE + shared + REPLY_TAIL
              + "\n})();\n" + FORWARD_CLAIM + "\nreturn __items;\n")
UNSUB_BODY = HEADER + PREAMBLE + shared + UNSUB_TAIL


def main():
    apply = "--apply" in sys.argv
    live = n8nlib.get_wf(WF2)
    os.makedirs(os.path.join(OUTDIR, "backups"), exist_ok=True)
    os.makedirs(os.path.join(OUTDIR, "patched"), exist_ok=True)
    json.dump(live, open(os.path.join(OUTDIR, "backups", "WF-2__pre_label_target.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    wf = copy.deepcopy(live)

    def node(nm):
        for x in wf["nodes"]:
            if x["name"] == nm:
                return x
        raise KeyError(nm)

    cfgn = node("CONFIG")
    cfg = json.loads(cfgn["parameters"]["jsonOutput"])
    before = dict(cfg["labels"])
    cfg["labels"]["disqualified"] = DISQUALIFIED
    cfgn["parameters"]["jsonOutput"] = json.dumps(cfg, ensure_ascii=False, indent=2)

    node("Body Lead Labels Union")["parameters"]["jsCode"] = REPLY_BODY
    node("Body U Lead DNC Label")["parameters"]["jsCode"] = UNSUB_BODY

    # the invariant this whole exercise is about: exactly one lead-label PATCH per branch
    patches = [x["name"] for x in wf["nodes"]
               if x["type"].endswith(".httpRequest")
               and str((x.get("parameters") or {}).get("method", "")).upper() == "PATCH"
               and "/v1/leads/" in str((x.get("parameters") or {}).get("url", ""))]
    assert sorted(patches) == ["Lead Labels Union", "U Lead DNC Label"], \
        "unexpected set of lead-label PATCH nodes: " + str(patches)
    conns = wf["connections"]
    for a, b in (("Lead Labels Union", "U Lead DNC Label"), ("U Lead DNC Label", "Lead Labels Union")):
        downstream = set()
        stack = [a]
        while stack:
            cur = stack.pop()
            for br in ((conns.get(cur) or {}).get("main") or []):
                for t in (br or []):
                    if t["node"] not in downstream:
                        downstream.add(t["node"]); stack.append(t["node"])
        assert b not in downstream, "SEQUENTIAL PATCH: %s can reach %s" % (a, b)

    json.dump(wf, open(os.path.join(OUTDIR, "patched", "WF-2__label_target.json"), "w",
                       encoding="utf-8"), ensure_ascii=False, indent=1)
    print("labels before: %s" % json.dumps(before))
    print("labels after : %s" % json.dumps(cfg["labels"]))
    print("shared engine embedded: %d chars into 2 nodes" % len(shared))
    print("single-PATCH invariant: OK (2 lead-label PATCH nodes, neither reachable from the other)")
    if apply:
        r, dropped = n8nlib.put_wf(WF2, wf)
        print("PUT %s  settings-stripped=%s" % (r.status_code, dropped))
        if r.status_code >= 300:
            print(r.text[:500]); sys.exit(1)
        back = n8nlib.get_wf(WF2)
        print("readback: active=%s nodes=%d versionId=%s"
              % (back.get("active"), len(back["nodes"]), back.get("versionId")))


if __name__ == "__main__":
    main()
