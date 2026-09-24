// n8n estate linter — the accumulated traps, as executable rules.
//
// ONE source of truth: this exact text is embedded into the `dnc_wf_linter` workflow's Code node
// by build_linter.py, and required directly by the statics. There is no second implementation.
//
// Every rule here was paid for by a real incident. The comment on each says which, because a rule
// whose reason is forgotten is a rule someone will delete.
//
// Input : the array from GET /api/v1/workflows?limit=250 (carries nodes + connections)
// Output: [{rule, severity, workflow, workflow_id, node, evidence, detail}]

// item-preserving nodes: they pass $json through untouched, so a field written upstream of them
// still exists downstream. These are exactly what made B12 invisible - the writer and the reader
// looked adjacent on the canvas with only an IF between them.
var PASS_THROUGH = ['n8n-nodes-base.if', 'n8n-nodes-base.switch', 'n8n-nodes-base.noOp',
                    'n8n-nodes-base.filter'];
// nodes whose output $json is a NEW object: anything a `__field` cannot survive
var REPLACING = ['n8n-nodes-base.httpRequest', 'n8n-nodes-base.dataTable', 'n8n-nodes-base.slack',
                 'n8n-nodes-base.pipedrive', 'n8n-nodes-base.openAi',
                 'n8n-nodes-base.executeWorkflow', 'n8n-nodes-base.respondToWebhook',
                 'n8n-nodes-base.emailSend', 'n8n-nodes-base.googleSheets'];

// Rules must judge what code DOES, not what its comments say. A comment quoting a channel id, a
// removed node's $('name'), or `label_ids` produced false findings; a comment containing `null`
// or `typeof` silently satisfied R05/R04. Strings, template literals and regex literals are kept
// verbatim (a '//' inside 'https://...' is not a comment); line breaks are preserved.
var REGEX_AFTER_WORD = ['return', 'typeof', 'case', 'in', 'of', 'delete', 'void', 'throw', 'new',
                        'else', 'do', 'instanceof', 'yield', 'await'];
function stripJsComments(src) {
  src = String(src || '');
  var out = '', i = 0, n = src.length, prevSig = '', word = '';
  var regexCanStart = function () {
    if (prevSig === '') return true;
    if (/[A-Za-z0-9_$]/.test(prevSig)) return REGEX_AFTER_WORD.indexOf(word) !== -1;
    return ')]}'.indexOf(prevSig) === -1;
  };
  var copyQuoted = function (start, q) {
    var j = start + 1;
    while (j < n && src[j] !== q) { if (src[j] === '\\') j++; j++; }
    return j + 1;
  };
  while (i < n) {
    var ch = src[i], nx = src[i + 1];
    if (ch === '/' && nx === '/') {
      while (i < n && src[i] !== '\n') i++;
      continue;
    }
    if (ch === '/' && nx === '*') {
      var end = src.indexOf('*/', i + 2);
      var chunk = end === -1 ? src.slice(i) : src.slice(i, end + 2);
      out += chunk.replace(/[^\n]/g, ' ');
      i += chunk.length;
      continue;
    }
    var j = undefined;   // explicit: a bare `var j;` keeps the previous iteration's value
    if (ch === '"' || ch === "'" || ch === '`') {
      j = copyQuoted(i, ch);
    } else if (ch === '/' && regexCanStart()) {
      j = i + 1;
      var inClass = false;
      while (j < n && src[j] !== '\n' && (inClass || src[j] !== '/')) {
        if (src[j] === '\\') j++;
        else if (src[j] === '[') inClass = true;
        else if (src[j] === ']') inClass = false;
        j++;
      }
      j++;
      while (j < n && /[a-z]/i.test(src[j])) j++;
    }
    if (j !== undefined) {
      out += src.slice(i, j); i = j; prevSig = ch; word = '';
      continue;
    }
    out += ch;
    if (/[A-Za-z0-9_$]/.test(ch)) { word = /[A-Za-z0-9_$]/.test(prevSig) ? word + ch : ch; prevSig = ch; }
    else if (!/\s/.test(ch)) { prevSig = ch; word = ''; }
    i++;
  }
  return out;
}

// parameters with comments removed from the code fields only; every other value is untouched
function codeStrippedParams(params) {
  var p = params || {};
  if (typeof p.jsCode !== 'string' && typeof p.functionCode !== 'string') return p;
  var copy = {};
  Object.keys(p).forEach(function (k) {
    copy[k] = (k === 'jsCode' || k === 'functionCode') && typeof p[k] === 'string' ? stripJsComments(p[k]) : p[k];
  });
  return copy;
}

function lintAll(workflows) {
  var out = [];

  workflows.forEach(function (wf) {
    var nodes = wf.nodes || [];
    var conns = wf.connections || {};
    var byName = {};
    nodes.forEach(function (n) { byName[n.name] = n; });
    var blob = function (n) { return JSON.stringify(codeStrippedParams(n.parameters)); };
    var code = function (n) { return stripJsComments((n.parameters || {}).jsCode); };

    // reverse graph: target -> [{src, outIndex, inIndex}]
    var rev = {};
    Object.keys(conns).forEach(function (src) {
      ((conns[src] || {}).main || []).forEach(function (branch, oi) {
        (branch || []).forEach(function (t) {
          (rev[t.node] = rev[t.node] || []).push(
            { src: src, outIndex: oi, inIndex: t.index || 0 });
        });
      });
    });

    var add = function (rule, severity, node, evidence, detail) {
      out.push({ rule: rule, severity: severity, workflow: wf.name, workflow_id: wf.id,
                 active: wf.active === true, node: node, evidence: String(evidence).slice(0, 220),
                 detail: detail });
    };

    // Which IF/switch branches a node sits on. Two producers that descend from DIFFERENT outputs
    // of the same IF can never both fire, so their meeting is the ordinary diamond merge, not a
    // race. Without this the linter reports 76 findings on the estate and every one is the
    // gate/skip pattern the codebase uses deliberately.
    var branchTags = function (name) {
      var tags = {}, seen = {}, q = [name];
      while (q.length) {
        var cur = q.shift();
        (rev[cur] || []).forEach(function (e) {
          var st = (byName[e.src] || {}).type;
          if (st === 'n8n-nodes-base.if' || st === 'n8n-nodes-base.switch') {
            (tags[e.src] = tags[e.src] || {})[e.outIndex] = true;
          }
          var k = e.src + '|' + cur;
          if (seen[k]) return;
          seen[k] = true;
          q.push(e.src);
        });
      }
      return tags;
    };
    // Pairwise, because real graphs nest gates: Person Id Final is fed by
    // Person Patch / Person Create / Skip Person Patch / Skip Person Create, which no SINGLE if
    // separates - but every pair is separated by one of two.
    var separated = function (ta, tb) {
      return Object.keys(ta).some(function (g) {
        if (!tb[g]) return false;
        var a = Object.keys(ta[g]), b = Object.keys(tb[g]);
        if (a.length !== 1 || b.length !== 1) return false;   // reachable from both sides
        return a[0] !== b[0];
      });
    };
    var mutuallyExclusive = function (srcs) {
      var tagged = srcs.map(branchTags);
      for (var i = 0; i < tagged.length; i++) {
        for (var j = i + 1; j < tagged.length; j++) {
          if (!separated(tagged[i], tagged[j])) return false;
        }
      }
      return true;
    };

    // nearest ancestors that are not pass-throughs
    var nearestReal = function (name, depth) {
      var seen = {}, queue = [[name, 0]], found = [];
      while (queue.length) {
        var cur = queue.shift(), nm = cur[0], d = cur[1];
        if (d > (depth || 8)) continue;
        (rev[nm] || []).forEach(function (e) {
          if (seen[e.src]) return;
          seen[e.src] = true;
          var t = (byName[e.src] || {}).type;
          if (PASS_THROUGH.indexOf(t) !== -1) queue.push([e.src, d + 1]);
          else found.push({ name: e.src, type: t, hops: d + 1 });
        });
      }
      return found;
    };

    nodes.forEach(function (n) {
      var b = blob(n), c = code(n), t = n.type;

      // ---- R01 B12: a __field read whose writer cannot have survived the hop -------------
      // Cost: 53 of 55 Finovate leads created ORPHANED because Body Lead Create read
      // $json.__person_id after a lead-list HTTP node. Recurs whenever anyone inserts an HTTP or
      // dataTable node into a gap that used to be adjacent.
      var reads = (b.match(/\$json\.__[A-Za-z0-9_]+/g) || [])
        .filter(function (v, i, a) { return a.indexOf(v) === i; });
      if (reads.length) {
        var anc = nearestReal(n.name);
        anc.forEach(function (a) {
          if (REPLACING.indexOf(a.type) === -1) return;
          var writes = reads.filter(function (r) {
            var f = r.replace('$json.', '');
            return blob(byName[a.name] || {}).indexOf(f) === -1;
          });
          if (!writes.length) return;
          add('R01_b12_field_after_replacing_node', a.hops === 1 ? 'high' : 'medium', n.name,
              writes.join(' '),
              'reads ' + writes.join(', ') + ' but the nearest non-pass-through producer is "'
              + a.name + '" (' + a.type.split('.').pop() + ', ' + a.hops + ' hop'
              + (a.hops > 1 ? 's' : '') + ') whose output replaces $json. Read the owning node BY NAME.');
        });
      }

      // ---- R04 dataTable failure read as absence -----------------------------------------
      // Cost: dnc_gate_queue read back as depth 0 for ~500 false alerts. On error some ops return
      // {error}, others echo the ORIGINAL input with no marker at all - so a negative test cannot
      // work. Only a positive check for the real row shape can.
      if (t === 'n8n-nodes-base.code') {
        // only a `get` can be misread as "no rows", and only by a node that actually consumes the
        // items - a Send Guard downstream of an upsert is reading nothing and is not at risk.
        var consumes = /\$input\.(all|first)\(\)|\$json\.data/.test(c);
        var dtAnc = nearestReal(n.name).filter(function (a) {
          return a.type === 'n8n-nodes-base.dataTable'
              && String(((byName[a.name] || {}).parameters || {}).operation || 'get') === 'get'; });
        if (dtAnc.length && consumes && c.indexOf('typeof') === -1) {
          add('R04_datatable_error_read_as_absence', 'medium', n.name,
              dtAnc.map(function (a) { return a.name; }).join(', '),
              'consumes dataTable output but has no positive row-shape check (no typeof). '
              + 'A failed read echoes the input items with no marker and will read as "no rows".');
        }
      }

      // ---- R05 missing read as zero -------------------------------------------------------
      // Cost: the I-04 686 delta and the queue depth. A count derived from an unverified read must
      // be null, never 0 - "missing" and "zero" are different findings.
      if (t === 'n8n-nodes-base.code') {
        var srcAnc = nearestReal(n.name).filter(function (a) {
          return a.type === 'n8n-nodes-base.httpRequest' || a.type === 'n8n-nodes-base.dataTable'; });
        if (srcAnc.length && /\.length/.test(c) && c.indexOf('null') === -1) {
          add('R05_missing_read_as_zero', 'medium', n.name,
              srcAnc.map(function (a) { return a.name; }).join(', '),
              'derives a count with .length from an unverified provider read and never yields '
              + 'null - an unreadable source will be reported as 0.');
        }
      }

      // ---- R06 channel id outside CONFIG --------------------------------------------------
      if (n.name !== 'CONFIG' && t !== 'n8n-nodes-base.stickyNote') {
        var ids = (b.match(/C0[A-Z0-9]{8,}/g) || [])
          .filter(function (v, i, a) { return a.indexOf(v) === i; });
        if (ids.length) {
          add('R06_hardcoded_channel_id', 'medium', n.name, ids.join(' '),
              'carries a literal Slack channel id. Routing must be one CONFIG edit, not a hunt '
              + 'through nodes.');
        }
      }

      // ---- R08 Set node silently dropping carried fields ----------------------------------
      if (t === 'n8n-nodes-base.set') {
        var p = n.parameters || {};
        if (p.mode !== 'raw' && p.includeOtherFields !== true) {
          add('R08_set_drops_carried_fields', 'medium', n.name, 'includeOtherFields not true',
              'a manual-mode Set node without includeOtherFields DROPS every field it does not '
              + 'list; downstream reads of carried context then silently see undefined.');
        }
      }

      // ---- R09 /v1/leads list read without an explicit sort --------------------------------
      // Cost: an unsorted page starts in 2023. Counting off it reports zero new leads on a day
      // with fifty.
      if (t === 'n8n-nodes-base.httpRequest') {
        var url = String((n.parameters || {}).url || '');
        var method = String((n.parameters || {}).method || 'GET').toUpperCase();
        var isLeadList = method === 'GET'    // a POST /v1/leads is a CREATE, not a list read
          && /\/v1\/leads(\?|$|\'|"|\s|\}\})/.test(url) && url.indexOf('/search') === -1;
        if (isLeadList && b.indexOf('sort') === -1) {
          // a person_id-scoped read returns a handful of rows, so ordering rarely decides the
          // answer; an unscoped one is the counting trap that returns the 2023 page.
          var scoped = /person_id=/.test(url);
          add('R09_v1_leads_without_sort', scoped ? 'medium' : 'high', n.name, url,
              'lists /v1/leads with no sort'
              + (scoped ? ' (person-scoped, so the risk is the 500-row horizon rather than the '
                          + 'page order)'
                        : '. Without sort=add_time DESC the endpoint returns the OLDEST page, so '
                          + 'any count taken off it is wrong.'));
        }
        // ---- R10 limit >= 500 ------------------------------------------------------------
        var lims = (b.match(/"limit"\s*,?\s*"?value"?\s*:\s*"?(\d{3,})/g) || [])
          .concat(b.match(/limit=(\d{3,})/g) || []);
        lims.forEach(function (m) {
          var v = Number((m.match(/(\d{3,})/) || [])[1]);
          if (v >= 500) {
            add('R10_limit_over_cap', 'high', n.name, m,
                'limit=' + v + '. Pipedrive search silently returns ZERO items above 100 - the '
                + 'call looks successful and reports "nothing found".');
          }
        });
        // ---- R12 /executions read without status ------------------------------------------
        if (url.indexOf('/executions') !== -1 && b.indexOf('status') === -1) {
          add('R12_executions_without_status', 'medium', n.name, url,
              'reads /executions unfiltered. That list omits crashed executions and under-returns '
              + 'successes (4 reported vs 172 real) - use status=error, or a per-workflow walk.');
        }
      }

      // ---- R13 dataTable referenced by NAME -----------------------------------------------
      // Cost: mode:"name" failed live on two confirmed-real tables in one day. Only the real id
      // from the table URL is trustworthy.
      if (t === 'n8n-nodes-base.dataTable') {
        var rl = (n.parameters || {}).dataTableId || {};
        if (rl.mode === 'name') {
          add('R13_datatable_by_name', 'high', n.name, String(rl.value),
              'references the table by NAME. mode:"name" has failed live on tables that certainly '
              + 'existed; use mode:"id" with the id from the table URL.');
        }
      }

      // ---- R14 a Responded writer with no engagement gate ----------------------------------
      // '3. Responded' is Marci's Handover trigger: writing it hands a human a lead as warm. Only
      // a human reply may set it. Found the bounce path on 2026-08-31, and then the UNSUB path -
      // which sets it unconditionally while its own sibling node deliberately withholds it for
      // opted-out leads. Class rule: no automated event sets Responded without an engagement gate.
      // must be a WRITER, not a reader: a digest counting `l.label_ids` is not applying anything.
      // Widened 2026-09-02: the previous test missed `M7 Labels Compute` in WF-1, a live writer
      // that emits the label through the shorthand property `label_ids,` and `targetSet.push(...)`.
      // A rule that cannot see a writer reports a clean estate, which is the failure this whole
      // file exists to prevent. `__body` alone was dropped - it matched this very rule's own text.
      var writesLabels = /label_ids\s*[:,=]/.test(b) || /[Tt]arget[A-Za-z_$]*\.push\(/.test(b);
      if (/c9d4b550-bcf3-11ef-a843-357f91e826ec|labels\.responded/.test(b) && writesLabels
          && !(t === 'n8n-nodes-base.set' && (n.parameters || {}).mode === 'raw')) {
        var gated = /__is_bounce|__isBounce|is_bounced|__isOOO|__opted_out|reply_class|__should_alert|stageRank|effectiveRank/.test(b);
        // A node that STRIPS the label out of its own target set is stronger than a gated one: it
        // cannot emit the label at all, on any branch, so there is nothing left to gate. Added
        // 2026-09-02 with the unsubscribe-path fix, whose target list never contains 'responded'
        // and which then hard-strips it belt-and-braces. Without this the rule would demand a gate
        // on a node that has already been made incapable of the write - and the estate would carry
        // a permanent high finding for having done the safer thing.
        var stripsResponded = /indexOf\(\s*[A-Za-z_$][\w$]*\.labels\.responded\s*\)/.test(b)
                              && /\.splice\(/.test(b);
        // 2026-09-02, second amendment. Nik changed the Pipedrive handover automation to fire only
        // when the labels do NOT contain 'DO NOT CONTACT' or 'Disqualified'. Withholding
        // '3. Responded' stopped being the control; writing the truthful PAIR in one PATCH is.
        // A node that derives its target set from the shared `labelTargetV1` is therefore
        // satisfied - the mapping and the same-PATCH invariant are proven behaviourally by
        // WF_SHARED/test_label_target.js over 288 combinations, which is a stronger guarantee
        // than any regex here could express.
        var usesSharedEngine = /labelTargetV1\s*\(/.test(b) && /function\s+labelTargetV1/.test(b);
        // A rule engine quotes the patterns it polices; this rule must not fire on its own text.
        var isRuleEngine = /add\('R\d\d_/.test(b);
        if (!gated && !stripsResponded && !usesSharedEngine && !isRuleEngine) {
          add('R14_responded_without_engagement_gate', 'high', n.name, '3. Responded',
              'writes the "3. Responded" label with no engagement gate (no bounce / OOO / '
              + 'opt-out / reply-class check). That label is the Handover trigger, so a delivery '
              + 'failure or an unsubscribe would be handed to a human as a warm lead.');
        }
      }

      // ---- R11 existence guard that forgets the campaign -----------------------------------
      // Cost: Person-ab3144af - the backfill guard asked "does this person have a lead" when the
      // rule is one lead PER CAMPAIGN, so a 2025 lead suppressed his 2026 one.
      // must be an actual DECISION, not a node that merely carries the id through: a guard is
      // code that assigns the verdict or branches on it.
      var GUARD = /(__lead_exists\s*[:=]|hasLead\s*=|has_lead\s*=|hasDeal\s*=|blockCreate\s*=|__block\w*\s*=)/;
      if (t === 'n8n-nodes-base.code' && GUARD.test(c) && !/campaign/i.test(c)) {
        add('R11_existence_guard_ignores_campaign', 'high', n.name,
            (c.match(GUARD) || [''])[0].trim(),
            'guards on whether the PERSON has a lead/deal without scoping to the campaign. The '
            + 'estate rule is one lead per campaign, so this suppresses legitimate new leads.');
      }
    });

    // ---- R16 settings key that the public PUT API rejects ---------------------------------
    // Cost: WF-1's deploy of the stable-key fix was REJECTED with
    //   "request/body/settings must NOT have additional properties"
    // while WF-2's identical deploy succeeded, leaving the two receivers briefly out of step.
    // The offender is `timeSavedMode` - a UI-only field the API will not accept back. Anything
    // that re-deploys this workflow must strip it from the payload.
    var REJECTED_SETTINGS = ['timeSavedMode'];
    REJECTED_SETTINGS.forEach(function (k) {
      if ((wf.settings || {})[k] !== undefined) {
        add('R16_settings_key_rejected_by_put_api', 'medium', '(workflow settings)', k,
            'settings.' + k + ' is present. The public PUT /workflows/{id} API rejects it with '
            + '"settings must NOT have additional properties", so any redeploy of this workflow '
            + 'fails unless the key is stripped from the payload first.');
      }
    });

    // ---- R02 fan-in into one input treated as a join --------------------------------------
    // Cost: five days of I-04 outage. n8n fires a node once per branch ARRIVAL, so two producers
    // into one input is a race, not a join.
    Object.keys(rev).forEach(function (target) {
      var byInput = {};
      rev[target].forEach(function (e) {
        (byInput[e.inIndex] = byInput[e.inIndex] || []).push(e); });
      Object.keys(byInput).forEach(function (ix) {
        var edges = byInput[ix];
        var srcs = edges.map(function (e) { return e.src; })
          .filter(function (v, i, a) { return a.indexOf(v) === i; });
        if (srcs.length < 2) return;   // same node on two outputs = success/error pair, only one fires
        if (mutuallyExclusive(srcs)) return;   // ordinary diamond merge off one IF, not a race
        var tgt = byName[target] || {};
        var refs = srcs.filter(function (s) {
          return blob(tgt).indexOf("$('" + s + "')") !== -1; });
        add('R02_fan_in_treated_as_join', refs.length ? 'high' : 'medium', target,
            srcs.join(' + '),
            srcs.length + ' different nodes feed input ' + ix + '. n8n runs the target once per '
            + 'ARRIVAL, so whichever wins the race fires it'
            + (refs.length ? ' - and it reads ' + refs.map(function (s) { return '$(' + s + ')'; }).join(', ')
                             + ' by name, which will throw "hasn\'t been executed".'
                           : '. Chain them, or accept it runs twice.'));
      });
    });

    // ---- R03 IF wired as if output 1 were TRUE ---------------------------------------------
    // Cost: ~500 "queue STUCK" alerts fired on exactly the polls where nothing was stuck.
    nodes.forEach(function (n) {
      if (n.type !== 'n8n-nodes-base.if') return;
      var main = ((conns[n.name] || {}).main || []);
      var t0 = (main[0] || []).length, t1 = (main[1] || []).length;
      if (t0 !== 0 || t1 === 0) return;
      var cond = JSON.stringify(((n.parameters || {}).conditions || {}));
      var positive = /should_|is_|has_|_ok|healthy|exists|enabled|success|valid/i.test(cond);
      var targets = (main[1] || []).map(function (x) { return x.node; });
      var actiony = targets.some(function (x) {
        return /alert|post|send|warn|notify|create|patch|update|fire/i.test(x); });
      add('R03_if_false_branch_used_as_true', (positive && actiony) ? 'high' : 'medium', n.name,
          targets.join(', '),
          'only output 1 (FALSE) is wired'
          + (positive ? ', while the condition reads like a positive assertion' : '')
          + (actiony ? ', and it drives an action node' : '')
          + '. Confirm the intent is "when NOT true".');
    });

    // ---- R07 scheduled alert with no state memory ------------------------------------------
    // Cost: 96 identical messages a day, twice over, for five days.
    var hasSchedule = nodes.some(function (n) {
      return n.type === 'n8n-nodes-base.scheduleTrigger'; });
    var slacks = nodes.filter(function (n) { return n.type === 'n8n-nodes-base.slack'; });
    var wfBlob = JSON.stringify(nodes.map(blob));
    if (hasSchedule && slacks.length && wfBlob.indexOf('getWorkflowStaticData') === -1) {
      slacks.forEach(function (s) {
        // An UNCONDITIONAL periodic post - a digest - is supposed to repeat; that is the whole
        // point of "silence must never be ambiguous". The repeat-alert defect is a CONDITIONAL
        // post: something an IF decided to send, re-decided identically on the next tick.
        var gated = Object.keys(branchTags(s.name)).length > 0;
        if (!gated) return;
        add('R07_poll_alert_without_state_change', 'high', s.name, 'no getWorkflowStaticData',
            'a scheduled workflow posts to Slack behind an IF with no state memory anywhere, so it '
            + 're-posts on every poll for as long as the condition holds. Alerts fire once per '
            + 'STATE CHANGE.');
      });
    }
  });

  return out;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { lintAll: lintAll, stripJsComments: stripJsComments, codeStrippedParams: codeStrippedParams };
}
