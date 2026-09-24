# -*- coding: utf-8 -*-
"""WF-2 (three stores) + WF-1 (duplicate-lead guard) -> the atomic claims table.

Every edit is a TARGETED replacement with an assertion. If the live text has moved under us the
script refuses and writes nothing - it never patches blind and never leaves a partial state.
The staticData writes are all KEPT as the rollback copy; only the DECISIONS move to the table.
"""
import json, io, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(os.environ["S2LIB"], "lib.py"), encoding="utf-8").read())

TABLE = "euyostwJYfJefItC"
WF2_ID = "jp7rum9Z0YDJkQWv"
WF1_ID = "2jdjKM2NJr473GdA"
DRY = "--dry-run" in sys.argv


def js(name):
    return io.open(os.path.join(HERE, "nodes", name), encoding="utf-8").read().rstrip("\n")


def node_code(name, code, pos, nid):
    return {"parameters": {"jsCode": code, "mode": "runOnceForAllItems"},
            "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": pos, "id": nid, "name": name}


def node_get(name, conds, pos, nid, return_all=False):
    p = {"resource": "row", "operation": "get",
         "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
         "matchType": "anyCondition",
         "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq", "keyValue": c}
                                    for c in conds]},
         "options": {}}
    if return_all:
        p["returnAll"] = True
    return {"parameters": p, "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
            "position": pos, "id": nid, "name": name,
            "onError": "continueRegularOutput", "alwaysOutputData": True}


def node_upsert(name, key_expr, family, workflow, event_time, evidence, pos, nid):
    return {"parameters": {"resource": "row", "operation": "upsert",
                           "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
                           "matchType": "allConditions",
                           "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq",
                                                       "keyValue": key_expr}]},
                           "columns": {"mappingMode": "defineBelow", "value": {
                               "claim_key": key_expr, "family": family, "workflow": workflow,
                               "event_time": event_time,
                               "claimed_at": "={{ new Date().toISOString() }}",
                               "evidence": evidence}},
                           "options": {}},
            "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": pos, "id": nid,
            "name": name, "onError": "continueRegularOutput", "retryOnFail": True}


def node_if(name, expr, pos, nid):
    return {"parameters": {"conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "combinator": "and",
                "conditions": [{"id": nid + "-c", "leftValue": expr, "rightValue": True,
                                "operator": {"type": "boolean", "operation": "true",
                                             "singleValue": True}}]},
                "options": {}},
            "type": "n8n-nodes-base.if", "typeVersion": 2, "position": pos, "id": nid,
            "name": name}


class Patcher(object):
    def __init__(self, wf):
        self.wf = wf
        self.by = dict((n["name"], n) for n in wf["nodes"])
        self.log = []

    def code_replace(self, node, old, new, label):
        n = self.by[node]
        src = n["parameters"]["jsCode"]
        c = src.count(old)
        if c != 1:
            raise SystemExit("REFUSING: %s / %s - anchor found %d times, expected 1.\n"
                             "The live code has moved; re-read it before patching.\n---\n%s\n---"
                             % (node, label, c, old[:400]))
        n["parameters"]["jsCode"] = src.replace(old, new)
        self.log.append("  patched  %-26s %s" % (node, label))

    def rename(self, old, new):
        if new in self.by:
            raise SystemExit("REFUSING: a node called %r already exists" % new)
        n = self.by.pop(old)
        n["name"] = new
        self.by[new] = n
        conns = self.wf["connections"]
        if old in conns:
            conns[new] = conns.pop(old)
        for src in conns.values():
            for br in (src.get("main") or []):
                for t in (br or []):
                    if t["node"] == old:
                        t["node"] = new
        self.log.append("  renamed  %-26s -> %s" % (old, new))

    def add(self, node):
        if node["name"] in self.by:
            raise SystemExit("REFUSING: duplicate node name %r" % node["name"])
        self.wf["nodes"].append(node)
        self.by[node["name"]] = node
        self.log.append("  added    %-26s (%s)" % (node["name"], node["type"].split(".")[-1]))

    def connect(self, src, dst, out=0):
        c = self.wf["connections"].setdefault(src, {}).setdefault("main", [])
        while len(c) <= out:
            c.append([])
        if not any(t["node"] == dst for t in c[out]):
            c[out].append({"node": dst, "type": "main", "index": 0})

    def disconnect(self, src, dst, out=0):
        br = ((self.wf["connections"].get(src) or {}).get("main") or [])
        if out < len(br):
            before = len(br[out])
            br[out] = [t for t in br[out] if t["node"] != dst]
            if len(br[out]) != before:
                return True
        return False

    def reroute_inbound(self, old_target, new_target):
        moved = 0
        for src, v in self.wf["connections"].items():
            for br in (v.get("main") or []):
                for t in (br or []):
                    if t["node"] == old_target and src != new_target:
                        t["node"] = new_target
                        moved += 1
        self.log.append("  rewired  %d inbound edge(s) %s -> %s" % (moved, old_target, new_target))
        return moved


UNIFORM_CLAIMERS = ["NoOp Nurture SENT", "NoOp Repeat SENT", "NoOp Lead Exists", "Reply CRM Done",
                    "Claim SENT", "Claim Bounce", "Claim Unsub", "Claim Nurture"]
SD_WRITE = "(__sd.wf2_seen = __sd.wf2_seen || {})[__k] = Math.floor(Date.now() / 1000);"
MARKER = ("\n      __items.forEach(function (it) "
          "{ if (it && it.json) it.json.__wf2_claim = %s; });   // -> DT Claim Dedupe")


def patch_wf2(wf):
    p = Patcher(wf)

    # ---------------------------------------------------------------- bounce memory
    p.rename("Normalize", "Normalize Parse")
    p.code_replace("Normalize Parse",
        "let __bounce_signal = __sigA ? 'event_name' : (__sigB ? 'body_marker' : null);",
        "// PUBLISHED FOR THE FINAL `Normalize`, which re-decides this from the claims table.\n"
        "// Everything below stays exactly as it was and remains the rollback copy.\n"
        "const __event_pre_bounce = event;\n"
        "const __sig_base = __sigA ? 'event_name' : (__sigB ? 'body_marker' : null);\n"
        "let __bounce_signal = __sig_base;",
        "publish pre-bounce event + base signal")
    p.code_replace("Normalize Parse",
        "  __reconciled_by: b.__reconciled === true ? pick(b.__reconciled_by) : null,\n};",
        "  __reconciled_by: b.__reconciled === true ? pick(b.__reconciled_by) : null,\n"
        "  // ingredients for the final `Normalize` - the verdict itself is decided there\n"
        "  __bkey, __sig_base, __event_pre_bounce,\n};",
        "publish __bkey / __sig_base / __event_pre_bounce")

    p.add(node_get("DT Bounce Get", ["={{ $json.__bkey ? ('wf2_bounce|' + $json.__bkey)"
                                     " : '__wf2_no_key__' }}"], [-160, 620], "wf2-bget"))
    p.add(node_code("Normalize", js("normalize_final.js"), [-160, 780], "wf2-normfin"))
    p.add(node_if("IF Bounce Claim",
                  "={{ !!$json.__bounce_signal && !!$json.__bounce_claim_key }}",
                  [40, 900], "wf2-bifc"))
    p.add(node_upsert("DT Bounce Claim", "={{ $json.__bounce_claim_key }}", "wf2_bounce", "WF-2",
                      "={{ $json.timestamp || new Date().toISOString() }}",
                      "={{ 'exec:' + $execution.id + ' bounce-seen ' + ($json.__bounce_signal||'') }}",
                      [240, 900], "wf2-bclaim"))
    p.connect("Normalize Parse", "DT Bounce Get")
    p.connect("DT Bounce Get", "Normalize")
    p.connect("Normalize", "IF Bounce Claim")
    p.connect("IF Bounce Claim", "DT Bounce Claim")
    # the parser must no longer feed the old downstream directly
    p.disconnect("Normalize Parse", "Dedupe")
    p.disconnect("Normalize Parse", "Event Alias Watch")
    p.connect("Normalize", "Event Alias Watch")

    # ---------------------------------------------------------------- dedupe / wf2_seen
    p.add(node_code("Dedupe Key", js("dedupe_key.js"), [40, 620], "wf2-dkey"))
    p.add(node_get("DT Dedupe Get",
                   ["={{ $json.__lookup_dedupe }}", "={{ $json.__lookup_sent }}",
                    "={{ $json.__lookup_forward }}"], [240, 620], "wf2-dget", return_all=True))
    p.connect("Normalize", "Dedupe Key")
    p.connect("Dedupe Key", "DT Dedupe Get")
    p.connect("DT Dedupe Get", "Dedupe")

    p.code_replace("Dedupe",
        "const __ts = (() => { const p = Date.parse(n.timestamp ?? ''); return Number.isFinite(p)"
        " ? String(p) : String(n.timestamp ?? ''); })();\n"
        "const key = [n.event, n.campaign_id, n.sl_lead_id, __ts].map(v => String(v ?? ''))"
        ".join('|');\n"
        "const duplicate = Object.prototype.hasOwnProperty.call(store.wf2_seen, key);",
        "// W2.STATE - the key moved to `Dedupe Key` so the lookup can run before this decision;\n"
        "// the arithmetic is unchanged. The claims table is the source of truth now, and the\n"
        "// staticData store above is kept ONLY as the rollback copy.\n"
        "const dk = $('Dedupe Key').item.json;\n"
        "const key = dk.__dedupe_key;\n"
        "// `alwaysOutputData` emits ONE EMPTY item on a clean miss. Only a NON-empty item\n"
        "// that is not a row is the echo, and only that is an outage - calling an empty read\n"
        "// broken would pin this node to staticData for ever and rot as the copy ages out.\n"
        "const __raw = $input.all().map(i => i.json)\n"
        "  .filter(r => r && typeof r === 'object' && Object.keys(r).length > 0);\n"
        "const __rows = __raw.filter(r => r.family === 'wf2_seen' && r.claimed_at\n"
        "                                 && r.claim_key);\n"
        "const __lookupBroken = __raw.length > 0 && __rows.length === 0;\n"
        "const __has = (k) => __rows.some(r => r.claim_key === k);\n"
        "const duplicate = __lookupBroken\n"
        "  ? Object.prototype.hasOwnProperty.call(store.wf2_seen, key)\n"
        "  : __has(dk.__lookup_dedupe);",
        "dedupe verdict from the table")
    p.code_replace("Dedupe",
        "const sentKey = 'S|' + String(n.campaign_id ?? '') + '|' + String(n.sl_lead_id ?? '');\n"
        "const firstSentSeen = Object.prototype.hasOwnProperty.call(store.wf2_seen, sentKey);\n"
        "if (n.event === 'SENT' && !firstSentSeen) store.wf2_seen[sentKey] = nowSec;",
        "const sentKey = dk.__sent_key;\n"
        "const firstSentSeen = __lookupBroken\n"
        "  ? Object.prototype.hasOwnProperty.call(store.wf2_seen, sentKey)\n"
        "  : __has(dk.__lookup_sent);\n"
        "if (n.event === 'SENT' && !firstSentSeen) store.wf2_seen[sentKey] = nowSec;  // rollback copy",
        "first-SENT memo from the table")
    p.code_replace("Dedupe",
        "return [{ json: { ...n, __dedupe_key: key, __duplicate: duplicate,"
        " __first_sent: !firstSentSeen } }];",
        "return [{ json: { ...n, __dedupe_key: key, __duplicate: duplicate,\n"
        "  __first_sent: !firstSentSeen,\n"
        "  // prefetched here so `Body SL Forward Email` does not need its own read\n"
        "  __forward_claimed: __lookupBroken ? !!(store.wf2_seen || {})[dk.__forward_key]\n"
        "                                    : __has(dk.__lookup_forward),\n"
        "  __claim_sent_now: (n.event === 'SENT' && !firstSentSeen),\n"
        "  __sent_claim_key: dk.__lookup_sent,\n"
        "  __dedupe_backend: __lookupBroken ? 'staticData_fallback' : 'dataTable' } }];",
        "publish forward-claim + backend")

    p.add(node_if("IF First SENT", "={{ $json.__claim_sent_now === true }}", [640, 760], "wf2-ifs"))
    p.add(node_upsert("DT Claim First SENT", "={{ $json.__sent_claim_key }}", "wf2_seen", "WF-2",
                      "={{ $json.timestamp || new Date().toISOString() }}",
                      "={{ 'exec:' + $execution.id + ' first-sent memo' }}", [840, 760], "wf2-cfs"))
    p.connect("Dedupe", "IF First SENT")
    p.connect("IF First SENT", "DT Claim First SENT")
    return p


def patch_wf2_claims_and_alert(p):
    # ---------------------------------------------------------------- the ten claim terminals
    # All ten write the SAME dedupe key under their own guard, so they share ONE claim node rather
    # than getting ten of their own. Each keeps its staticData write (rollback) and additionally
    # publishes __wf2_claim on its output; the shared gate refuses anything without a key, so a
    # branch whose guard failed can never claim by accident.
    p.add(node_if("IF Claim Ready",
                  "={{ typeof $json.__wf2_claim === 'string' && $json.__wf2_claim.length > 0 }}",
                  [1240, 980], "wf2-ifcr"))
    p.add(node_upsert("DT Claim Dedupe", "={{ 'wf2_seen|' + $json.__wf2_claim }}", "wf2_seen",
                      "WF-2", "={{ $('Dedupe').item.json.timestamp || new Date().toISOString() }}",
                      "={{ 'exec:' + $execution.id + ' claim-after-success' }}",
                      [1440, 980], "wf2-cded"))
    p.connect("IF Claim Ready", "DT Claim Dedupe")
    for name in UNIFORM_CLAIMERS:
        p.code_replace(name, SD_WRITE, SD_WRITE + (MARKER % "__k"), "publish __wf2_claim")
        p.connect(name, "IF Claim Ready")
    # Body Lead Labels Union claims the FORWARD key, not the event key.
    fwd = "(__sd.wf2_seen = __sd.wf2_seen || {})['F|' + __k] = Math.floor(Date.now() / 1000);"
    p.code_replace("Body Lead Labels Union", fwd, fwd + (MARKER % "('F|' + __k)"),
                   "publish __wf2_claim (forward)")
    p.connect("Body Lead Labels Union", "IF Claim Ready")
    # ...and Body SL Forward Email READS it, now from the prefetch instead of workflow memory.
    p.code_replace("Body SL Forward Email",
        "const __already_forwarded = (() => {\n"
        "  try {\n"
        "    if (!__fkey) return false;\n"
        "    const sd = $getWorkflowStaticData('global');\n"
        "    return !!((sd.wf2_seen || {})[__fkey]);\n"
        "  } catch (e) { return false; }\n"
        "})();",
        "const __already_forwarded = (() => {\n"
        "  try {\n"
        "    if (!__fkey) return false;\n"
        "    // prefetched by `DT Dedupe Get`; staticData only if the table could not be read\n"
        "    const d = $('Dedupe').item.json;\n"
        "    if (d && d.__dedupe_backend === 'dataTable') return d.__forward_claimed === true;\n"
        "    const sd = $getWorkflowStaticData('global');\n"
        "    return !!((sd.wf2_seen || {})[__fkey]);\n"
        "  } catch (e) { return false; }\n"
        "})();",
        "forward-claim read from the table")

    # ---------------------------------------------------------------- alert registry
    p.add(node_code("Alert Key", js("alert_key.js"), [-160, 1140], "wf2-akey"))
    p.add(node_get("DT Alert Get", ["={{ $json.__lookup_alert }}",
                                    "={{ $json.__lookup_alert_legacy }}"],
                   [40, 1140], "wf2-aget"))
    p.reroute_inbound("First Reply Gate", "Alert Key")
    p.connect("Alert Key", "DT Alert Get")
    p.connect("DT Alert Get", "First Reply Gate")
    p.code_replace("First Reply Gate",
        "const key = String($json.__person_id ?? (n.lead && n.lead.email\n"
        "              ? String(n.lead.email).trim().toLowerCase() : null) ?? '');\n"
        "// legacy entries were keyed on the lead id - still honoured so this deploy re-announces"
        " nothing\n"
        "const legacyKey = $json.__lead_id ? String($json.__lead_id) : null;\n"
        "const already = (key && Object.prototype.hasOwnProperty.call(reg, key))\n"
        "             || (legacyKey && Object.prototype.hasOwnProperty.call(reg, legacyKey))"
        " || false;",
        "// W2.STATE - the key moved to `Alert Key` and the registry to the atomic claims table.\n"
        "// The staticData copy above is kept as the rollback and as the fallback when the table\n"
        "// cannot be read. Legacy lead-id entries are still honoured on READ, never written back.\n"
        "const ak = $('Alert Key').item.json;\n"
        "const key = ak.__alert_key || '';\n"
        "const legacyKey = ak.__legacy_alert_key;\n"
        "const __row = $json;\n"
        "const __isRow = !!(__row && __row.family === 'wf2_alert' && __row.claimed_at\n"
        "                   && __row.claim_key);\n"
        "const __lookupBroken = !!(__row && (__row.error || __row.__error))\n"
        "                    || (!!__row && Object.keys(__row).length > 0 && !__isRow);\n"
        "const __hit = __isRow && (__row.claim_key === ak.__lookup_alert\n"
        "                          || __row.claim_key === ak.__lookup_alert_legacy);\n"
        "// fail OPEN on an unreadable table: a duplicate alert is noise, a missed first reply is\n"
        "// lost revenue. The staticData copy is consulted first so a table outage is not a\n"
        "// regression to no suppression at all.\n"
        "const already = __lookupBroken\n"
        "  ? ((key && Object.prototype.hasOwnProperty.call(reg, key))\n"
        "     || (legacyKey && Object.prototype.hasOwnProperty.call(reg, legacyKey)) || false)\n"
        "  : __hit;",
        "alert suppression from the table")
    p.code_replace("First Reply Gate",
        "return [{ json: { ...$json, __should_alert: should, __alert_key: key,",
        "return [{ json: { ...$('Alert Key').item.json, __should_alert: should, __alert_key: key,\n"
        "  __alert_backend: __lookupBroken ? 'staticData_fallback' : 'dataTable',\n"
        "  __alert_claim_key: ak.__lookup_alert,",
        "carry the payload past the lookup")

    p.add(node_if("IF Alert Delivered",
                  "={{ (() => { try { return $('Reply Alert').item.json.ok === true"
                  " && !!$('First Reply Gate').item.json.__alert_key; }"
                  " catch (e) { return false; } })() }}", [1240, 1140], "wf2-ifad"))
    p.add(node_upsert("DT Alert Claim",
                      "={{ $('First Reply Gate').item.json.__alert_claim_key }}", "wf2_alert",
                      "WF-2", "={{ $('Normalize').item.json.timestamp"
                              " || new Date().toISOString() }}",
                      "={{ 'exec:' + $execution.id + ' alert-delivered' }}", [1440, 1140],
                      "wf2-aclaim"))
    p.connect("Classify Body", "IF Alert Delivered")
    p.connect("IF Alert Delivered", "DT Alert Claim")
    return p


def patch_wf1(wf):
    p = Patcher(wf)
    p.add(node_code("Lead Claim Key", js("wf1_lead_claim_key.js"), [-200, 1500], "wf1-lckey"))
    p.add(node_get("DT Lead Claim Get", ["={{ $json.__lookup_lead_claim }}"],
                   [0, 1500], "wf1-lcget"))
    p.add(node_code("Lead Claim Gate", js("wf1_lead_claim_gate.js"), [200, 1500], "wf1-lcgate"))
    p.add(node_if("IF Lead Claimed", "={{ $json.__lead_already_claimed === true }}",
                  [400, 1500], "wf1-lcif"))
    p.add(node_upsert("DT Lead Claim Set",
                      "={{ $('Lead Claim Key').item.json.__lead_claim_key }}", "lead_create",
                      "WF-1", "={{ new Date().toISOString() }}",
                      "={{ 'exec:' + $execution.id + ' lead ' + "
                      "(($json.data && $json.data.id) || '?') }}", [800, 1620], "wf1-lcset"))
    # Lead Create Gate[0] used to run straight into Create Lead; the claim now sits between them.
    if not p.disconnect("Lead Create Gate", "Create Lead", out=0):
        raise SystemExit("REFUSING: Lead Create Gate[0] -> Create Lead not found")
    p.connect("Lead Create Gate", "Lead Claim Key", out=0)
    p.connect("Lead Claim Key", "DT Lead Claim Get")
    p.connect("DT Lead Claim Get", "Lead Claim Gate")
    p.connect("Lead Claim Gate", "IF Lead Claimed")
    p.connect("IF Lead Claimed", "Select Existing Lead", out=0)   # someone else owns the create
    p.connect("IF Lead Claimed", "Create Lead", out=1)
    p.connect("Create Lead", "DT Lead Claim Set")                 # claim AFTER the create returns
    # Select Existing Lead now has two callers, so it must not depend on being handed the search
    # response as $json.
    p.code_replace("Select Existing Lead", "const lead = selectLead($json.data);",
        "// Two callers now (the gate's existing-lead output, and the duplicate-lead claim), so\n"
        "// read the search response by name rather than relying on what $json happens to be.\n"
        "// runOnceForEachItem: .first() needs no paired-item trail through the lookup.\n"
        "const lead = selectLead($('Lead Search').first().json.data);",
        "read Lead Search by name")
    return p


def summarise(tag, before, after, log):
    print("\n" + "=" * 78 + "\n%s\n" % tag + "=" * 78)
    print("  nodes %d -> %d" % (len(before["nodes"]), len(after["nodes"])))
    for line in log:
        print(line)


def main():
    os.path.isdir(os.path.join(HERE, "backups")) or os.makedirs(os.path.join(HERE, "backups"))
    out = {}
    for tag, wid in (("WF-2", WF2_ID), ("WF-1", WF1_ID)):
        live = get("/api/v1/workflows/%s" % wid)
        io.open(os.path.join(HERE, "backups", "%s__pre_state_port.json" % tag), "w",
                encoding="utf-8").write(json.dumps(live, ensure_ascii=False, indent=1))
        before = json.loads(json.dumps(live))
        if tag == "WF-2":
            p = patch_wf2(live)
            p = patch_wf2_claims_and_alert(p)
        else:
            p = patch_wf1(live)
        summarise(tag + "  (live versionId " + str(before.get("versionId")) + ")",
                  before, live, p.log)
        names = [n["name"] for n in live["nodes"]]
        if len(names) != len(set(names)):
            dup = sorted(set(n for n in names if names.count(n) > 1))
            raise SystemExit("REFUSING: duplicate node names after patch: %s" % dup)
        ids = [n["id"] for n in live["nodes"]]
        if len(ids) != len(set(ids)):
            raise SystemExit("REFUSING: duplicate node ids after patch")
        for src, v in live["connections"].items():
            for br in (v.get("main") or []):
                for t in (br or []):
                    if t["node"] not in names:
                        raise SystemExit("REFUSING: %s -> %s targets a node that does not exist"
                                         % (src, t["node"]))
        out[tag] = (wid, live)
    if DRY:
        print("\nDRY RUN - nothing deployed.")
        for tag, (wid, wf) in out.items():
            io.open(os.path.join(HERE, "patched_%s.json" % tag), "w", encoding="utf-8").write(
                json.dumps(wf, ensure_ascii=False, indent=1))
        print("patched definitions written to patched_WF-*.json")
        return
    for tag, (wid, wf) in out.items():
        resp, dropped = put_wf(wid, wf)
        print("\nDEPLOY %s -> HTTP %s  dropped keys: %s" % (tag, resp.status_code, dropped))
        if resp.status_code >= 300:
            raise SystemExit("DEPLOY FAILED for %s: %s" % (tag, resp.text[:500]))
        back = get("/api/v1/workflows/%s" % wid)
        print("   versionId %s  nodes %d  active %s"
              % (back.get("versionId"), len(back["nodes"]), back.get("active")))


if __name__ == "__main__":
    main()
