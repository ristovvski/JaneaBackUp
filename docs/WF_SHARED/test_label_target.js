// CLASS STATIC — "no automated event writes '3. Responded' without, in the SAME PATCH, the label
// its category implies."  (Nik, 2026-09-02)
//
// This is a behavioural static, not a regex one. It executes the single shared implementation
// against every case and asserts the exact label set. A textual rule can only ask whether a node
// mentions a gate; this asks what the node would actually write.
//
// Bought by: WF-2's `Body U Lead DNC Label`, which wrote cold+connected+Responded on an
// unsubscribe with no suppressing label at all, while its sibling twenty nodes away had three
// locks. Two copies of one idea, kept in step by memory.
//
// Run: node test_label_target.js

const { labelTargetV1 } = require('./label_target.js');

const L = {
  cold:        'a6d359b0-6a45-11ed-ab46-5b95b19fcb18',
  connected:   'ca698a50-bdfb-11ef-8172-510383583b0e',
  responded:   'c9d4b550-bcf3-11ef-a843-357f91e826ec',
  dnc:         '52a7c290-fc73-11f0-ad98-81d4703453f3',
  disqualified:'98008920-e942-11ef-b360-57187fe024ea',
};
const NAME = Object.fromEntries(Object.entries(L).map(([k, v]) => [v, k]));
const show = (ids) => ids.map(i => NAME[i] || i).join('+');

let pass = 0, fail = 0;
function check(title, input, expected) {
  const r = labelTargetV1({ labels: L, ...input });
  const got = r.target.map(i => NAME[i] || i).sort().join('+');
  const want = expected.slice().sort().join('+');
  const ok = got === want;
  // the invariant itself, asserted separately from the expected set: if Responded is written,
  // the implied suppressing label must be in the SAME target set.
  let invariant = true, note = '';
  if (r.responded && r.implied && r.target.indexOf(r.implied) === -1) {
    invariant = false; note = ' [IMPLIED LABEL MISSING FROM THE SAME PATCH]';
  }
  if (ok && invariant) { pass++; console.log('  PASS  ' + title.padEnd(52) + show(r.target)); }
  else { fail++; console.log('  FAIL  ' + title.padEnd(52) + 'got ' + got + '  want ' + want + note); }
}

console.log('\nNik\'s five cases');
check('explicit stop -> Responded + DO NOT CONTACT',
      { event: 'REPLY', category: 'Do Not Contact' },
      ['cold', 'connected', 'responded', 'dnc']);
check('negative reply -> Responded + Disqualified',
      { event: 'REPLY', category: 'Not Interested' },
      ['cold', 'connected', 'responded', 'disqualified']);
check('genuine interest -> Responded only',
      { event: 'REPLY', category: 'Interested' },
      ['cold', 'connected', 'responded']);
check('out of office -> NO Responded',
      { event: 'REPLY', category: 'Out Of Office' },
      ['cold', 'connected']);
check('bounce -> NO Responded, NO Connected',
      { event: 'BOUNCE' },
      ['cold']);

console.log('\nthe unsubscribe path (Nik: it is an explicit stop)');
check('UNSUB event -> Responded + DO NOT CONTACT',
      { event: 'UNSUB' },
      ['cold', 'connected', 'responded', 'dnc']);
check('UNSUB with no category still implies DO NOT CONTACT',
      { event: 'UNSUB', category: null },
      ['cold', 'connected', 'responded', 'dnc']);

console.log('\nthe other real categories, and how they are mapped');
check('Meeting Request -> interest',
      { event: 'REPLY', category: 'Meeting Request' }, ['cold', 'connected', 'responded']);
check('Information Request -> interest',
      { event: 'REPLY', category: 'Information Request' }, ['cold', 'connected', 'responded']);
check('Wrong Person -> Disqualified',
      { event: 'REPLY', category: 'Wrong Person' },
      ['cold', 'connected', 'responded', 'disqualified']);
check('No Longer Working There -> Disqualified',
      { event: 'REPLY', category: 'No Longer Working There' },
      ['cold', 'connected', 'responded', 'disqualified']);
check('Sender Originated Bounce category -> bounce',
      { event: 'REPLY', category: 'Sender Originated Bounce' }, ['cold']);
check('Uncategorizable by Ai -> Responded only (goes to review)',
      { event: 'REPLY', category: 'Uncategorizable by Ai' }, ['cold', 'connected', 'responded']);
check('classifier did not run -> Responded only',
      { event: 'REPLY', category: null }, ['cold', 'connected', 'responded']);

console.log('\nprecedence: a bounce or an OOO beats any category');
check('bounce event beats an Interested category',
      { event: 'REPLY', is_bounce: true, category: 'Interested' }, ['cold']);
check('OOO flag beats an Interested category',
      { event: 'REPLY', is_ooo: true, category: 'Interested' }, ['cold', 'connected']);
check('bounce beats OOO',
      { event: 'REPLY', is_bounce: true, is_ooo: true }, ['cold']);
check('classifier is_dnc beats a benign category',
      { event: 'REPLY', is_dnc: true, category: 'Interested' },
      ['cold', 'connected', 'responded', 'dnc']);

console.log('\nunion semantics: existing labels are never removed');
{
  const r = labelTargetV1({ labels: L, event: 'REPLY', category: 'Not Interested',
                            existing: [L.cold, L.responded, '4. Positive Reply-id'] });
  const ok = r.union.includes('4. Positive Reply-id') && r.union.includes(L.disqualified)
             && r.union.includes(L.cold) && r.union.includes(L.responded);
  ok ? (pass++, console.log('  PASS  a foreign label survives the union'))
     : (fail++, console.log('  FAIL  a foreign label survives the union -> ' + show(r.union)));
  const r2 = labelTargetV1({ labels: L, event: 'REPLY', category: 'Interested',
                             existing: [L.cold, L.connected, L.responded] });
  r2.changed === false ? (pass++, console.log('  PASS  no change reports changed=false'))
                       : (fail++, console.log('  FAIL  no change reports changed=false'));
  // A lead already carrying DO NOT CONTACT that now replies with genuine interest: Responded is
  // truthful, and the existing DNC keeps suppressing handover. The old opt-out lock that stripped
  // Responded here is obsolete under the new automation condition.
  const r3 = labelTargetV1({ labels: L, event: 'REPLY', category: 'Interested',
                             existing: [L.cold, L.dnc] });
  (r3.union.includes(L.responded) && r3.union.includes(L.dnc))
    ? (pass++, console.log('  PASS  DNC lead replying with interest keeps both labels'))
    : (fail++, console.log('  FAIL  DNC lead replying with interest keeps both labels'));
}

console.log('\nTHE INVARIANT, over every case at once');
{
  const cats = [null, 'Do Not Contact', 'Not Interested', 'Interested', 'Meeting Request',
                'Information Request', 'Out Of Office', 'Wrong Person', 'No Longer Working There',
                'Sender Originated Bounce', 'Uncategorizable by Ai', 'Something New We Never Saw'];
  const events = ['REPLY', 'UNSUB', 'BOUNCE'];
  let bad = 0, n = 0;
  for (const e of events) for (const c of cats) for (const b of [false, true])
    for (const o of [false, true]) for (const d of [false, true]) {
      n++;
      const r = labelTargetV1({ labels: L, event: e, category: c, is_bounce: b, is_ooo: o, is_dnc: d });
      // 1. Responded never appears without its implied label in the SAME target set
      if (r.responded && r.implied && r.target.indexOf(r.implied) === -1) bad++;
      // 2. a bounce or an OOO never produces Responded
      if ((b || e === 'BOUNCE' || c === 'Sender Originated Bounce' || o) && r.responded) bad++;
      // 3. a bounce never produces Connected
      if ((b || e === 'BOUNCE' || c === 'Sender Originated Bounce') && !o
          && r.target.indexOf(L.connected) !== -1) bad++;
    }
  bad === 0 ? (pass++, console.log('  PASS  ' + n + ' combinations, invariant holds in all'))
            : (fail++, console.log('  FAIL  ' + bad + ' of ' + n + ' combinations violate it'));
}

console.log('\n==== ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
