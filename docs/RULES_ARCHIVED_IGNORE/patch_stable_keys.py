# -*- coding: utf-8 -*-
"""Suppression keys derive from STABLE identity, never from lead visibility.

The Person-b093030e regression, precisely:
  08-28 18:23  lead live      -> key 'L8694ea30-a30b-11f1-8297-bb888c95b31f|572715'  first_alert
  08-31 10:39  lead ARCHIVED  (by a human or an external automation)
  08-31 14:27  second message -> key 'P85903|572715'                                 first_alert
The key moved because it was built from lead_id, and archiving made the lead invisible. The
delivery registry had no record of the new key, so a second genuine message was announced as a
first alert - against the gate's own documented intent ("ONE alert per lead, suppressed on
DELIVERY").

Both gates now key on person id first, canonical provider identity second, never the lead. Each
ALSO reads the legacy lead-keyed entry, so already-delivered alerts stay suppressed and there is
no one-time re-alert wave on deploy. Only the new key is ever written.
"""
import json, sys

SRC1, DST1, SRC2, DST2 = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

# ------------------------------------------------------------------ WF-1
w = json.load(open(SRC1, encoding="utf-8"))
node = [n for n in w["nodes"] if n["name"] == "M7 Alert Gate"][0]
c = node["parameters"]["jsCode"]

OLD1 = """const who = b.lead_id ? ('L' + b.lead_id)
          : (b.person_id ? ('P' + b.person_id)
          : (li ? ('M' + li) : null));
const key = who ? (who + '|' + camp) : null;"""
assert OLD1 in c, "WF-1 M7 Alert Gate key block not found verbatim"

NEW1 = """// STABLE KEY (Nik, 2026-08-31). The key must NOT depend on whether the lead is visible.
// It used to prefer 'L' + lead_id, so archiving Person-b093030e's lead moved his key from
// 'L8694ea30-a30b-11f1-8297-bb888c95b31f|572715' to 'P85903|572715'; the registry had no record
// of the new key and his SECOND message was announced as a first alert. Lead visibility is
// mutable state - a human archiving a lead must never reset that lead's alert suppression.
// Order: pipedrive person id -> canonical provider identity -> nothing (then fail open).
const who = b.person_id ? ('P' + b.person_id)
          : (li ? ('K' + String(li).toLowerCase()) : null);
const key = who ? (who + '|' + camp) : null;
// MIGRATION, not a rewrite of history: entries already delivered under the old lead-keyed form
// are still honoured, so deploying this does not re-announce everything that was keyed 'L...'.
// Only `key` is ever written back.
const legacyKey = b.lead_id ? ('L' + b.lead_id + '|' + camp) : null;"""
c = c.replace(OLD1, NEW1)

OLD1B = "} else if (reg[key]) {\n  should = false; reason = 'already_delivered';"
assert OLD1B in c, "WF-1 already_delivered branch not found"
c = c.replace(OLD1B,
              "} else if (reg[key] || (legacyKey && reg[legacyKey])) {\n"
              "  should = false;\n"
              "  reason = reg[key] ? 'already_delivered' : 'already_delivered_legacy_lead_key';")
node["parameters"]["jsCode"] = c
assert "'L' + b.lead_id)\n" not in c, "a lead-first key path survived"
json.dump({"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
           "settings": w.get("settings", {})}, open(DST1, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("WF-1 M7 Alert Gate patched")

# ------------------------------------------------------------------ WF-2
w2 = json.load(open(SRC2, encoding="utf-8"))
n2 = [n for n in w2["nodes"] if n["name"] == "First Reply Gate"][0]
c2 = n2["parameters"]["jsCode"]

OLD2 = "const key = String($json.__lead_id ?? $json.__person_id ?? (n.lead && n.lead.email) ?? '');"
assert OLD2 in c2, "WF-2 First Reply Gate key line not found verbatim"

NEW2 = """// STABLE KEY (Nik, 2026-08-31). Same defect as WF-1's: keying on __lead_id first means a lead
// that is archived, converted to a deal, or pushed past a read horizon silently resets its own
// suppression, and the next reply is treated as a first reply. Person id first, then the lead's
// canonical email; never the lead id.
const key = String($json.__person_id ?? (n.lead && n.lead.email
              ? String(n.lead.email).trim().toLowerCase() : null) ?? '');
// legacy entries were keyed on the lead id - still honoured so this deploy re-announces nothing
const legacyKey = $json.__lead_id ? String($json.__lead_id) : null;"""
c2 = c2.replace(OLD2, NEW2)

OLD2B = "const already = key ? Object.prototype.hasOwnProperty.call(reg, key) : false;"
assert OLD2B in c2, "WF-2 already flag not found"
c2 = c2.replace(OLD2B,
    "const already = (key && Object.prototype.hasOwnProperty.call(reg, key))\n"
    "             || (legacyKey && Object.prototype.hasOwnProperty.call(reg, legacyKey)) || false;")
n2["parameters"]["jsCode"] = c2
assert "$json.__lead_id ?? $json.__person_id" not in c2, "a lead-first key path survived in WF-2"
json.dump({"name": w2["name"], "nodes": w2["nodes"], "connections": w2["connections"],
           "settings": w2.get("settings", {})}, open(DST2, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("WF-2 First Reply Gate patched")
