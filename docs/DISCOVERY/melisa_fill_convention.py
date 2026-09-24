'''Derive the correct Event name / Marketing Hypothesis values for a lead, mirroring WF-1's own
W1.0.13.1 two-bracket parser exactly (see wf1-system-reference.md #6b) so the backfill produces
byte-identical values to what WF-1/WF-2 would have written themselves. Pure function, no writes.'''
import re

MARKER_CANON = {"events visiting": "Events Visiting"}  # WF-1's own event_marker_canon map


def derive_event_hypothesis(text):
    """text = lead title or campaign-field string. Returns (hypothesis, event_name, ok, reason)."""
    if not text:
        return None, None, False, "no_campaign_text"
    brackets = re.findall(r"\[([^\]]+)\]", text)
    if len(brackets) < 2:
        return None, None, False, f"fewer_than_2_brackets({brackets})"
    g1 = brackets[0].strip().lower()
    g2 = brackets[1].strip()
    hyp = MARKER_CANON.get(g1)
    if hyp is None:
        return None, g2, False, f"unknown_marker({brackets[0]!r})"
    if not g2 or len(g2) > 60:
        return hyp, None, False, f"bad_event_name({g2!r})"
    return hyp, g2, True, "ok"


if __name__ == "__main__":
    tests = [
        "3686193 - [Events Visiting] AI4 2026 - Rune - Catch-alls - Lauren",
        "[Events Visiting] [Ai4 2026] - Rune - LinkedIn - Person-378ea30f",
        "2342830 - [Events Visiting] AI4 2025 - Valids - Person-bb2dd1de",
        "[Events Visiting] AI4 2026 - Mario - Catch-alls - Person-6c30f42a",  # single-bracket-ish? check
        "Ai4 2026",  # campaign-field value alone, no brackets at all
    ]
    for t in tests:
        print(t, "->", derive_event_hypothesis(t))
