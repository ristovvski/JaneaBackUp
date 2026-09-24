// Kill-test for the 2026-08-27 rebuilt idle_guard_js (daily_summary): must scream within the hour
// of a missed 05:30 UTC slot, using real timestamps, not the old once/day date-string compare.
const assert = require('assert');

function runIdleGuard(staticData, nowIso) {
  const sd = staticData;
  const IDLE_GUARD_JS = `
    const now = new Date(NOW_ISO);
    const today = now.toISOString().slice(0, 10);
    const slot = new Date(today + 'T05:30:00.000Z');
    const graceMs = 45 * 60 * 1000;
    const pastGrace = now.getTime() > (slot.getTime() + graceMs);
    const postedToday = sd.lastPostedDate === today;
    const missed = pastGrace && !postedToday;
    return { missed_today: missed, last_posted_date: sd.lastPostedDate || null,
      last_success_at: sd.lastSuccessAt || null, today, checked_at: now.toISOString() };
  `.replace('NOW_ISO', JSON.stringify(nowIso));
  const fn = new Function('sd', IDLE_GUARD_JS);
  return fn(sd);
}

let failures = 0;
function check(cond, label) {
  console.log('  ' + (cond ? 'ok  ' : 'FAIL') + ' - ' + label);
  if (!cond) failures++;
}

console.log('Scenario 1: exec 34078 replay -- crashed at 05:30, no post since 08-26, checked at 06:10 (40min after slot)');
let r = runIdleGuard({ lastPostedDate: '2026-08-26', lastSuccessAt: '2026-08-26T05:30:05.000Z' }, '2026-08-27T06:10:00.000Z');
check(r.missed_today === false, 'still inside the 1h grace window -- must NOT scream yet (' + JSON.stringify(r) + ')');

console.log('\nScenario 2: same crash, now checked at 06:35 (65min after slot -- past grace)');
r = runIdleGuard({ lastPostedDate: '2026-08-26', lastSuccessAt: '2026-08-26T05:30:05.000Z' }, '2026-08-27T06:35:00.000Z');
check(r.missed_today === true, 'past the 1h grace with no post today -- MUST scream (' + JSON.stringify(r) + ')');

console.log('\nScenario 3: healthy day -- posted today already, checked at 20:00');
r = runIdleGuard({ lastPostedDate: '2026-08-27', lastSuccessAt: '2026-08-27T05:30:04.000Z' }, '2026-08-27T20:00:00.000Z');
check(r.missed_today === false, 'already posted today -- must stay quiet (' + JSON.stringify(r) + ')');

console.log('\nScenario 4: brand-new workflow, static data never initialized (undefined lastPostedDate)');
r = runIdleGuard({}, '2026-08-27T07:00:00.000Z');
check(r.missed_today === true, 'unset static data must read as missed, never silently healthy (' + JSON.stringify(r) + ')');

console.log('\nScenario 5: re-arm -- yesterday alerted correctly, a NEW successful run today must go quiet again without manual reset');
r = runIdleGuard({ lastPostedDate: '2026-08-27', lastSuccessAt: '2026-08-27T05:30:02.000Z' }, '2026-08-27T09:00:00.000Z');
check(r.missed_today === false, 'auto re-arms via date comparison, no sticky flag needed (' + JSON.stringify(r) + ')');

console.log('\nScenario 6: cadence check -- with a 15-minute tick, how many ticks until scream after the slot passes?');
const ticksToScream = [];
for (let mins = 0; mins <= 90; mins += 15) {
  const t = new Date('2026-08-27T05:30:00.000Z').getTime() + mins * 60000;
  const rr = runIdleGuard({ lastPostedDate: '2026-08-26' }, new Date(t).toISOString());
  ticksToScream.push({ mins_after_slot: mins, missed: rr.missed_today });
}
console.log('  ' + JSON.stringify(ticksToScream));
const firstScream = ticksToScream.find((x) => x.missed);
check(firstScream && firstScream.mins_after_slot <= 60, 'first scream must land within the hour of the missed slot, no slack (got ' + (firstScream ? firstScream.mins_after_slot : 'never') + 'min)');

console.log();
if (failures) { console.log(failures + ' FAILED'); process.exit(1); }
console.log('all kill-test scenarios passed -- idle guard screams within the hour, stays quiet when healthy, re-arms automatically');
