// BuildActivity — the one activity a scoring run leaves on the organization.
//
// It writes the table's note VERBATIM.
//
// v6.0 rendered the note here: it took the structured classifier output and
// wrote prose in its own words, on a 900-character budget, dropping whole
// sentences in a fixed order to stay inside it. That is gone. The table now
// produces both the grade and the note, and a second author rewriting the
// first author's reasoning is how a rep ends up reading a summary of a summary.
// One author, one text, no budget, no trimming, no reflow.
//
// So this node is deliberately almost nothing: it is the place where the
// invariants live — one activity, marked done, addressed to the organization
// the event named — not a place where copy is produced. If it ever starts
// composing again, that is a contract change, not a tweak.

// CONFIG on Path A, CONFIG B on Path B. The two Set nodes hold the same JSON,
// but a Code node may only reference a node that is CONNECTED upstream of it:
// n8n raises a "no connection" expression error otherwise, and in the task
// runner that error's own constructor then throws
// `Cannot assign to read only property 'name'`, which hides the real message
// completely. A node that runs on both paths therefore has to ask for
// whichever CONFIG is upstream of it. Kept byte-identical across the nodes
// that need it; tests/static/workflow_review.test.mjs enforces that.
let cfg = null;
try { cfg = $('CONFIG').item.json; } catch (e) { cfg = null; }
if (cfg === null || cfg === undefined) {
  try { cfg = $('CONFIG B').item.json; } catch (e) { cfg = null; }
}
if (cfg === null || cfg === undefined) {
  throw new Error('ICP_NO_CONFIG: neither CONFIG nor CONFIG B is upstream of this node');
}

const parsed = $('ParseScored').item.json;

// ParseScored refuses an empty note, so reaching here with one means the
// boundary was changed. An activity with no body is worse than no activity:
// it looks like the workflow ran and had nothing to say.
const note = parsed.note;
if (typeof note !== 'string' || note.trim() === '') {
  const error = new Error(
    'ICP_EMPTY_NOTE: the event carried no note, and the note IS the activity — ' +
    'there is nothing for a rep to read'
  );
  error.name = 'IcpEmptyNote';
  throw error;
}

return [{
  json: {
    request_id: parsed.request_id,
    org_id: parsed.org_id,
    deal_id: parsed.deal_id,

    subject: cfg.activity_subject,
    type: cfg.activity_type,
    // Byte for byte what the table sent. The test suite asserts equality
    // against the event, not a resemblance to it.
    body: note,
    chars: note.length,
    verbatim: true,
  },
}];
