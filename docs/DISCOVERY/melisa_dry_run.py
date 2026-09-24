import json, re, sys
sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open('melisa_gap_joined.json', encoding='utf-8'))
all_recs = d['all']

def empty(v):
    return v is None or str(v).strip() == ""

def is_2026(t):
    return bool(re.search(r'ai4\s*2026', t.lower()))

CANON_HYPO = "Events Visiting"

# the derived population: Ai4-2026 leads where event_name is empty OR hypothesis is non-canonical
target = [r for r in all_recs if r.get('person_found') and is_2026(r['title']) and
          (empty(r.get('event_name')) or empty(r.get('hypothesis')) or r.get('hypothesis') != CANON_HYPO)]

# backfill-300 emails
bf300 = set()
for l in open('../WF1_W1.0.1_build/wf1-release-evidence/ai4_missing_persons.jsonl', encoding='utf-8'):
    bf300.add(json.loads(l)['email'].lower())

target_emails = set((r.get('person_email') or '').lower() for r in target)
overlap = target_emails & bf300
print(f"Target population (Ai4-2026, gap): {len(target)} leads / {len(set(r['person_id'] for r in target))} persons")
print(f"backfill-300 source list: {len(bf300)} emails")
print(f"Overlap (backfill-300 emails already IN target): {len(overlap)}")
print(f"backfill-300 emails NOT in target (need separate check - maybe not Ai4-2026-titled, or already fixed): {len(bf300 - target_emails)}")

# EMAIL CAMPAIGN -> known values (since single-bracket, can't derive event_name via regex; CONFIG map)
EMAIL_CAMPAIGN_MAP = {
    "3686193": ("Events Visiting", "Ai4 2026"),  # Rune Catch-alls
    "3686187": ("Events Visiting", "Ai4 2026"),  # Rune Valids
    "3686184": ("Events Visiting", "Ai4 2026"),  # Mario Catch-alls
    "3686181": ("Events Visiting", "Ai4 2026"),  # Mario Valids
}

def derive_two_bracket(text):
    brackets = re.findall(r"\[([^\]]+)\]", text or "")
    if len(brackets) >= 2:
        g1 = brackets[0].strip().lower()
        g2 = brackets[1].strip()
        if g1 == "events visiting" and g2 and len(g2) <= 60:
            return ("Events Visiting", g2)
    return (None, None)

def intended_values(rec):
    # try two-bracket parse first (covers LinkedIn titles)
    hyp, ev = derive_two_bracket(rec['title'])
    if hyp and ev:
        return hyp, ev, "two_bracket_parse"
    # fall back to CONFIG campaign-id map (covers single-bracket email campaigns)
    for cid, (h, e) in EMAIL_CAMPAIGN_MAP.items():
        if cid in rec['title']:
            return h, e, f"config_map[{cid}]"
    return None, None, "NO_RULE_MATCHED"

print("\n=== Dry-run: intended writes (NO WRITES PERFORMED) ===")
by_person = {}
no_rule = []
for r in target:
    hyp, ev, rule = intended_values(r)
    pid = r['person_id']
    if rule == "NO_RULE_MATCHED":
        no_rule.append(r)
        continue
    cur_ev = r.get('event_name')
    cur_hyp = r.get('hypothesis')
    changes = {}
    if empty(cur_ev) or cur_ev != ev:
        changes['event_name'] = {"from": cur_ev, "to": ev}
    if empty(cur_hyp) or cur_hyp != hyp:
        changes['hypothesis'] = {"from": cur_hyp, "to": hyp}
    if changes:
        by_person[pid] = {"person_id": pid, "email": r.get('person_email'), "rule": rule,
                           "sample_title": r['title'][:70], "changes": changes}

print(f"Persons with a computed intended write: {len(by_person)}")
print(f"Records where NO rule matched (need manual review): {len(no_rule)}")
for r in no_rule[:10]:
    print("  NO_RULE:", r['title'][:80])

# breakdown of change types
only_event = sum(1 for v in by_person.values() if 'event_name' in v['changes'] and 'hypothesis' not in v['changes'])
only_hyp = sum(1 for v in by_person.values() if 'hypothesis' in v['changes'] and 'event_name' not in v['changes'])
both = sum(1 for v in by_person.values() if 'event_name' in v['changes'] and 'hypothesis' in v['changes'])
print(f"\n  event_name only: {only_event}  |  hypothesis only (typo-fix): {only_hyp}  |  both: {both}")

with open('melisa_dry_run_output.json', 'w', encoding='utf-8') as f:
    json.dump({"by_person": by_person, "no_rule_matched": [r['title'] for r in no_rule]}, f, indent=2, ensure_ascii=False)
print("\nwrote melisa_dry_run_output.json")

print("\n=== SAMPLE dry-run rows (first 15) ===")
for pid, v in list(by_person.items())[:15]:
    print(f"  person {pid} ({v['email']}) [{v['rule']}]: {v['sample_title']}")
    for field, ch in v['changes'].items():
        print(f"      {field}: {ch['from']!r} -> {ch['to']!r}")
