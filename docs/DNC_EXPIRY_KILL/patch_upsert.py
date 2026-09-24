# -*- coding: utf-8 -*-
"""STEP 3: neuter computeExpiry in DNC__UpsertLedger__v1 / Decide.

Every entry_type now returns null. Rationale, for the rulebook:

  Melisa's 2026-08-26 ruling replaced time-based expiry with REASON-based retention - the registry
  keeps replies, meetings, sales-created/Surfe, employee connections and explicit opt-outs, and
  retires everything whose only reason was contact. A TTL applied to exactly the rows that
  represent a response contradicts that ruling: it says the response stops mattering after six
  months, which is the opposite of "only a RESPONSE creates a relationship worth protecting".

  All three call sites are left in place and keep calling computeExpiry. Only the policy inside it
  changes, so the shape of `record`/`merged` is untouched and Amendment 3's
  reasonExpiryOverride (reply_dnc + date_precision 'unknown' -> null) still runs and still agrees.
"""
import json, sys

SRC, DST = sys.argv[1], sys.argv[2]
w = json.load(open(SRC, encoding="utf-8"))
node = [n for n in w["nodes"] if n["name"] == "Decide"][0]
c = node["parameters"]["jsCode"]

OLD = """function computeExpiry(entry_type, added_at, ttlMonths) {
  if (DNC_PERMANENT_TYPES[entry_type]) return null;         // explicit_opt_out / employee_connection
  if (entry_type === 'replied' || entry_type === 'negative_reply') return dncAddMonths(added_at, ttlMonths);
  return null; // manual: permanent unless caller supplied an explicit expires_at (handled upstream)
}"""

NEW = """function computeExpiry(entry_type, added_at, ttlMonths) {
  // EXPIRY IS DEAD (Nik, 2026-08-31). Every entry_type is permanent; this function returns null
  // for all of them and is kept only so the three call sites and the record shape stay untouched.
  //
  // Why: Melisa's 2026-08-26 ruling replaced TIME-based expiry with REASON-based retention. The
  // registry keeps replies, meetings, sales-created/Surfe, employee connections and explicit
  // opt-outs, and retires rows whose only reason was contact. A six-month TTL on 'replied' and
  // 'negative_reply' applied to precisely the rows that represent a response - it said the
  // response stops mattering, which is the opposite of "only a RESPONSE creates a relationship
  // worth protecting".
  //
  // The TTL had produced 1,353 active rows carrying an expires_at (45 already past, 1,308 on a
  // rolling timer). All 1,353 were nulled the same day; dnc_expiry_job - the only consumer that
  // would ever have acted on the field - is deactivated and preserved.
  //
  // ttlMonths is now unused. It is left in the signature so the call sites do not change.
  return null;
}"""

assert OLD in c, "computeExpiry not found verbatim - refusing to guess"
c = c.replace(OLD, NEW)
assert "return dncAddMonths(added_at, ttlMonths)" not in c, "a TTL path survived the patch"
node["parameters"]["jsCode"] = c

json.dump({"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
           "settings": w.get("settings", {})},
          open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("patched Decide; nodes", len(w["nodes"]))
