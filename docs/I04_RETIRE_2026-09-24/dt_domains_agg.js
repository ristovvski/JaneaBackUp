// Collapses the domains read to ONE item before the claims read. Two reasons: a Data Table read runs
// once per input item, so feeding it 1,373 domain rows would read the claims table 1,373 times; and a
// failed read can echo its INPUT items back with no error marker - with this node in between, an echo
// is this summary item, which has no claim_key and is therefore recognised as a failed read.
const prev = $('Sched Agg').first().json;
return [{ json: { ...prev, __dt_domains_marker: true } }];
