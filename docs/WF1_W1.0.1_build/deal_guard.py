"""Shared open-deal guard for REPAIR SCRIPTS — the third no-lead->create path.

Person-7267ff83, 2026-08-14: my repair asked "does this person have leads?", got a truthful 0, and
created one. She had an open deal since April with 8 activities. A person converted to a deal ALWAYS
has zero leads, so the emptiest answer arrives from the most advanced state.

Import this and call `assert_safe_to_create_lead(pd, person_id)` before ANY lead POST in a repair.
It raises rather than returning a flag, because the failure mode being prevented is a human (me)
reading a soft warning and proceeding anyway.

Fails CLOSED: an unreadable deals response blocks creation. Creating a duplicate reaches Melisa's
queue and spawns a Handover; not creating is recoverable. Same direction as the deployed gates.
"""


class DealGuardBlocked(Exception):
    """Raised when a person is already represented and a lead must NOT be created."""


def open_deals(pd, person_id):
    """pd: a callable taking a Pipedrive path and returning parsed JSON.

    Returns (deals, failed). `failed` True means UNKNOWN, which is not the same as none.
    """
    r = pd(f"/api/v2/deals?person_id={person_id}&status=open&limit=50") or {}
    if r.get("__err") or r.get("success") is False:
        return [], True
    data = r.get("data")
    if not isinstance(data, list):
        return [], True
    return [d for d in data if str((d or {}).get("status") or "") == "open"], False


def assert_safe_to_create_lead(pd, person_id):
    """Raise DealGuardBlocked unless creating a lead for this person is actually correct."""
    deals, failed = open_deals(pd, person_id)
    if failed:
        raise DealGuardBlocked(
            f"person {person_id}: open-deal check FAILED (unknown, not 'none'). Refusing to create "
            f"a lead - unknown must not create. Re-run when Pipedrive answers.")
    if deals:
        d = deals[0]
        raise DealGuardBlocked(
            f"person {person_id} is already represented by OPEN DEAL {d.get('id')} "
            f"({str(d.get('title'))[:60]!r}). Do NOT create a lead - put the activity on the deal "
            f"via deal_id, with participants=[{{person_id, primary:true}}] "
            f"(person_id is read-only on /api/v2/activities).")
    return True


def activity_target(pd, person_id, lead_id=None):
    """Where should a repair write an activity? Returns (kind, body_fragment).

    Mirrors the deployed Body Reply Activity: an existing lead wins, otherwise an open deal, and
    if neither exists the caller must decide deliberately rather than defaulting to lead creation.
    """
    if lead_id:
        return "lead", {"lead_id": lead_id}
    deals, failed = open_deals(pd, person_id)
    if failed:
        raise DealGuardBlocked(f"person {person_id}: deal state unknown - refusing to guess a home")
    if deals:
        return "deal", {"deal_id": deals[0]["id"],
                        "participants": [{"person_id": person_id, "primary": True}]}
    return "none", {}
