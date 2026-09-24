"""WF-2 graph assembly (Phase B). Imported by build_wf2.py's build().

Wires the branch library into the full topology and returns (nodes, connections).
Every write goes through the Body -> Gate -> Write triple; ops warns are ungated.
"""
from build_wf2_branches import (code, ifnode, http, slack, write_triple, PD, SL, LLM,
                                BODY_PERSON_CREATE, BODY_PERSON_PATCH, BODY_LEAD_CREATE,
                                ORG_RESOLVE, BODY_ORG_CREATE, LEAD_RESOLVE, FIRST_REPLY_GATE,
                                ALERT_TEXT, NURTURE_TEXT, CLASSIFY_BODY, CLASSIFY_PARSE,
                                FORWARD_RESOLVE, BODY_FORWARD, BODY_SL_CATEGORY, BODY_SL_UNSUB,
                                BODY_LABELS, BODY_REPLY_ACTIVITY, BODY_BOUNCE_NOTE,
                                OPS_WARN_TEXT_UNKNOWN_EVENT, OPS_WARN_TEXT_MARKER,
                                OPS_WARN_TEXT_NOLEAD, OPS_WARN_TEXT_CLASSIFY, OPS_WARN_TEXT_INBOX)

TOK = "={{ $('CONFIG').item.json }}"

# B19 verify-apply bodies (one per resolve point; %(pick)s names the node that picked)
VERIFY_APPLY_SENT = r'''
const picked = $('Person Pick').item.json;
if (!picked.__person_found) return [{ json: { ...picked, __person_deleted: false } }];
// no try/catch: none of this can throw, and a dead catch is just an untestable branch.
// Unknown/absent flags mean NOT deleted - an unreachable or odd GET must never delete by accident.
const d = ($json && ($json.data ?? $json)) || {};
const deleted = (d.is_deleted === true) || (d.active_flag === false);
if (deleted) {
  // treat exactly as "not found" so the existing create / no-lead branches take over unchanged
  return [{ json: { __person: null, __person_id: null, __person_found: false,
                    __person_deleted: true, __person_deleted_id: picked.__person_id } }];
}
return [{ json: { ...picked, __person_deleted: false, __person_verified: true } }];
'''

VERIFY_APPLY_REPLY = r'''
const picked = $('R Person Pick').item.json;
if (!picked.__person_found) return [{ json: { ...picked, __person_deleted: false } }];
// no try/catch: none of this can throw, and a dead catch is just an untestable branch.
// Unknown/absent flags mean NOT deleted - an unreachable or odd GET must never delete by accident.
const d = ($json && ($json.data ?? $json)) || {};
const deleted = (d.is_deleted === true) || (d.active_flag === false);
if (deleted) {
  // treat exactly as "not found" so the existing create / no-lead branches take over unchanged
  return [{ json: { __person: null, __person_id: null, __person_found: false,
                    __person_deleted: true, __person_deleted_id: picked.__person_id } }];
}
return [{ json: { ...picked, __person_deleted: false, __person_verified: true } }];
'''

OPS_WARN_DELETED_PERSON = (
    "={{ (() => { const j=$json; const n=$('Normalize').item.json;"
    " const esc=(v)=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');"
    " return '\\u26a0\\ufe0f WF-2: Pipedrive search returned a DELETED person (' "
    " + esc(j.__person_deleted_id) + ') for ' + esc(n.lead.email)"
    " + ' \\u2014 treated as not found (' + esc(n.campaign_name) + ')'; })() }}"
)



def one(name, to):
    return {name: {"main": [[{"node": to, "type": "main", "index": 0}]]}}


def two(name, t_true, t_false):
    return {name: {"main": [[{"node": t_true, "type": "main", "index": 0}],
                            [{"node": t_false, "type": "main", "index": 0}]]}}


def assemble(cred):
    N, C = [], {}

    def add(nodes=None, conns=None):
        if nodes:
            N.extend(nodes if isinstance(nodes, list) else [nodes])
        if conns:
            for k, v in conns.items():
                C[k] = v

    # ======================================================= ops warn nodes (UNGATED)
    warns = [
        ("wf2-w1", "Ops Warn Unknown Event", OPS_WARN_TEXT_UNKNOWN_EVENT, [3600, 1400]),
        ("wf2-w2", "Ops Warn Unknown Marker", OPS_WARN_TEXT_MARKER, [3600, 1520]),
        ("wf2-w3", "Ops Warn No Lead", OPS_WARN_TEXT_NOLEAD, [3600, 1640]),
        ("wf2-w4", "Ops Warn Classify", OPS_WARN_TEXT_CLASSIFY, [3600, 1760]),
        ("wf2-w5", "Ops Warn Unknown Inbox", OPS_WARN_TEXT_INBOX, [3600, 1880]),
    ]
    for nid, nm, txt, pos in warns:
        add(slack(nid, nm, pos, "slack_channel_ops", txt, cred))

    # ======================================================= SENT branch
    y = 200
    add(ifnode("wf2-s01", "IF Nurture SENT", [2400, y],
               "={{ $('Normalize').item.json.is_nurture === true }}", "wf2-cs01"))
    add(code("wf2-s02", "NoOp Nurture SENT", [2600, y - 140], "return [{ json: { skipped: 'nurture' } }];"))
    add(ifnode("wf2-s03", "IF First Email", [2600, y + 60],
               "={{ ($('Dedupe').item.json.sequence_number === 1) || ($('Dedupe').item.json.__first_sent === true) }}",
               "wf2-cs03"))
    add(code("wf2-s04", "NoOp Repeat SENT", [2800, y - 80], "return [{ json: { skipped: 'not_first_email' } }];"))
    add(ifnode("wf2-s05", "IF Need Enrich", [2800, y + 120],
               "={{ !$('Normalize').item.json.lead.title || !$('Normalize').item.json.lead.company }}",
               "wf2-cs05"))
    # B8/1: /campaigns/{id}/leads?email= answers 400 - verified against the live API 2026-07-28.
    # The working lookup is the GLOBAL /leads?email=, which returns a FLAT lead object.
    add(http("wf2-s06", "SL Fetch Lead", [3000, y + 40], "GET",
             SL + "{{ '/leads?email=' + encodeURIComponent($('Normalize').item.json.lead.email) }}",
             body=False, retry=True, cof=True))
    add(code("wf2-s07", "Apply Enrich", [3200, y + 40], r"""
const n = $('Normalize').item.json;
// B8/2: three real shapes, verified live. /leads?email= -> FLAT object; the paged
// /campaigns/{id}/leads -> { data: [ { lead: {...} } ] }. The old chain resolved to {} on the
// flat one, so enrichment silently did nothing on every SENT event.
let d = {};
try {
  const r = $json;
  d = (r && r.email) ? r
    : (r?.data?.[0]?.lead ?? r?.data?.[0] ?? r?.[0]?.lead ?? r?.[0] ?? r?.data ?? {}) || {};
} catch (e) { d = {}; }
const cf = d.custom_fields || {};
const merged = JSON.parse(JSON.stringify(n));
// no job_title exists at the top level of the SL lead - titles only ever arrive via custom_fields
merged.lead.title = merged.lead.title || cf.job_title || cf.title || d.job_title || d.title || null;
merged.lead.company = merged.lead.company || d.company_name || null;
merged.lead.linkedin = merged.lead.linkedin || d.linkedin_profile || null;
merged.lead.website = merged.lead.website || d.website || d.company_url || null;
merged.lead.location = merged.lead.location || d.location || null;
return [{ json: { __enriched: merged } }];
"""))
    add(http("wf2-s08", "Person Search", [3400, y + 120], "GET",
             PD + "{{ '/api/v2/persons/search?fields=email&exact_match=true&limit=20&term=' + encodeURIComponent($('Normalize').item.json.lead.email) }}",
             body=False, retry=True))
    add(code("wf2-s09", "Person Pick", [3600, y + 120], r"""
const n = $('Normalize').item.json;
// B27: emit every email-verified candidate instead of deciding on the first hit. Pipedrive search
// order is relevance-based and unstable, and duplicates are normal (Make makes one person per send).
// The provisional id is the OLDEST, which is the only deterministic choice; the real decision is
// made downstream by whichever lead actually belongs to this campaign.
const items = ($json.data?.items ?? []) || [];
const want = String(n.lead.email || '').toLowerCase();
const cands = [];
for (const it of items) {
  const p = it.item ?? it;
  const mails = [].concat(p.emails ?? p.email ?? [])
    .map(e => String((e && e.value) ? e.value : e).toLowerCase());
  // B/U previously took items[0] with NO email check - a fuzzy match could be a different person
  if (mails.includes(want)) cands.push(p);
}
cands.sort((a, b) => Number(a.id) - Number(b.id));
const hit = cands.length ? cands[0] : null;
return [{ json: { __person: hit, __person_id: hit ? hit.id : null, __person_found: !!hit,
                  __person_candidates: cands.map(c => c.id),
                  __person_dupes: cands.length > 1 } }];
"""))
    # B19: re-read the picked person before any write can target it
    add(http("wf2-s09b", "Person Verify", [3680, y + 20], "GET",
             PD + "{{ '/api/v2/persons/' + ($('Person Pick').item.json.__person_id || 0) }}",
             body=False, retry=True, cof=True))
    add(code("wf2-s09c", "Person Verify Apply", [3740, y + 120], VERIFY_APPLY_SENT))
    add(ifnode("wf2-s09d", "IF Person Deleted", [3740, y + 620],
               "={{ $json.__person_deleted === true }}", "wf2-cs09d"))
    add(slack("wf2-s09e", "Ops Warn Deleted Person", [3900, y + 620],
              "slack_channel_ops", OPS_WARN_DELETED_PERSON, cred))
    add(code("wf2-s09f", "NoOp Person Live", [3900, y + 740],
             "return [{ json: { person: 'live' } }];"))
    add(http("wf2-s10", "Org Search", [3800, y + 120], "GET",
             # B16: search the ENRICHED company - Normalize's is null on a real EMAIL_SENT payload
             PD + "{{ '/api/v2/organizations/search?limit=10&term=' + encodeURIComponent("
                  "(() => { try { const e=$('Apply Enrich').item.json.__enriched; "
                  "if (e && e.lead && e.lead.company) return e.lead.company; } catch(x){} "
                  "return $('Normalize').item.json.lead.company || '__none__'; })()) }}",
             body=False, retry=True, cof=True))
    add(code("wf2-s11", "Org Resolve", [4000, y + 120], ORG_RESOLVE))
    add(ifnode("wf2-s12", "IF Org Found", [4200, y + 120], "={{ $json.__org_found === true }}", "wf2-cs12"))

    on, oc, oc_entry, oc_live = write_triple("wf2-s13", "Org Create", [4400, y + 260], BODY_ORG_CREATE,
                                             "POST", PD + "{{ '/api/v2/organizations' }}")
    add(on, oc)
    add(code("wf2-s14", "Org Id After Create", [4960, y + 260], r"""
const id = $json?.data?.id ?? $json?.id ?? null;
return [{ json: { __org_id: id, __org_found: !!id, __org_created: true } }];
"""))
    add(code("wf2-s15", "Carry Person Ctx", [4400, y + 120], r"""
const ps = (() => {
  // B19 completion: reading the raw pick here bypassed the deleted-person guard entirely - and
  // Person Id Final would then attach a new lead to the DELETED person's id.
  try { const v = $('Person Verify Apply').item.json; if (v && '__person_found' in v) return v; } catch (e) {}
  return $('Person Pick').item.json;
})();
let org = null;
try { org = $('Org Resolve').item.json.__org_id ?? null; } catch (e) { org = null; }
try { const c = $('Org Id After Create').item.json; if (c && c.__org_id) org = c.__org_id; } catch (e) {}
return [{ json: { ...ps, __org_id: org } }];
"""))
    add(ifnode("wf2-s16", "IF Person Found", [5160, y + 120], "={{ $json.__person_found === true }}", "wf2-cs16"))

    pp_n, pp_c, pp_entry, pp_live = write_triple("wf2-s17", "Person Patch", [5360, y + 40], BODY_PERSON_PATCH,
                                                 "PATCH",
                                                 PD + "{{ '/api/v2/persons/' + $('Person Pick').item.json.__person_id }}")
    add(pp_n, pp_c)
    pc_n, pc_c, pc_entry, pc_live = write_triple("wf2-s18", "Person Create", [5360, y + 300], BODY_PERSON_CREATE,
                                                 "POST", PD + "{{ '/api/v2/persons' }}")
    add(pc_n, pc_c)
    add(code("wf2-s19", "Person Id Final", [5920, y + 170], r"""
let pid = null;
try {
  const v = $('Person Verify Apply').item.json;
  pid = (v && '__person_found' in v) ? (v.__person_id ?? null)
                                     : ($('Person Pick').item.json.__person_id ?? null);
} catch (e) {}
if (!pid) { try { pid = $json?.data?.id ?? $json?.id ?? null; } catch (e) {} }
let org = null;
try { org = $('Carry Person Ctx').item.json.__org_id ?? null; } catch (e) {}
return [{ json: { __person_id: pid, __org_id: org } }];
"""))
    # B23: exposed the moment WF-2S started replaying real SENT events. In shadow mode Person
    # Create is skipped, so a brand-new prospect reaches here with __person_id null, the URL
    # fabricated person_id=0, and Pipedrive answered 400 "provided dataset is not valid". Unlike
    # its three siblings (R/B/U Lead List) this node had no cof, so the 400 ABORTED the execution
    # and Shadow Log recorded nothing at all - blinding the shadow window for precisely the
    # brand-new leads it exists to observe. Two fixes: gate the call (B22 pattern - no id, no GET)
    # and give it the same cof as its siblings so a Pipedrive hiccup degrades instead of aborting.
    add(ifnode("wf2-s19g", "IF Have Person Id", [5960, y + 170],
               "={{ $json.__person_id !== null && $json.__person_id !== undefined }}", "wf2-cs19g"))
    add(http("wf2-s20", "Lead List", [6120, y + 170], "GET",
             PD + "{{ '/v1/leads?limit=500&archived_status=all&sort=add_time%20DESC' }}",
             body=False, retry=True, cof=True))
    # empty list, not a skip-out: Lead Select's contract is unchanged, it finds no existing lead,
    # and the chain continues to the Lead Create intent (B20 - every false branch continues)
    # named "... Skipped" not "Skip ...": the Skip prefix is reserved for WRITE-gate false
    # branches (B20/SH2), and this is a branch skip, not a suppressed write.
    # pairedItem is set explicitly: Lead Select recovers person/org via $('Person Id Final').item,
    # and a Code node that returns a freshly built object drops the pairing that lookup needs.
    add(code("wf2-s20s", "Lead List Skipped", [6120, y + 300],
             "return $input.all().map((it, i) => ({ json: { ...it.json, data: [],"
             " __no_person: true }, pairedItem: { item: i } }));"))
    add(code("wf2-s21", "Lead Select", [6320, y + 170], r"""
const CFG = $('CONFIG').item.json; const F = CFG.fields;
const n = $('Normalize').item.json;
const canon = (s) => String(s ?? '').replace(/[   ]/g, ' ').replace(/\s+/g, ' ').trim();
// B27: the read is no longer filtered by person_id, so this page holds OTHER people's leads for the
// same campaign too. Matching on campaign alone would attach us to a stranger's lead. The rule is
// (campaign matches) AND (the lead belongs to one of OUR email-verified candidates).
const _pick = (() => {
  for (const nm of ['R Person Pick', 'Person Pick', 'B Lead Ctx', 'U Lead Ctx',
                    'R Person Verify Apply', 'Person Verify Apply']) {
    try {
      const j = $(nm).item.json;
      if (j && (Array.isArray(j.__person_candidates) || j.__person_id)) return j;
    } catch (e) { /* node not on this branch */ }
  }
  return {};
})();
// ids are stringified ONLY for set comparison; the provisional keeps its original type, because
// downstream code and tests compare person ids as numbers
const cand = Array.isArray(_pick.__person_candidates)
  ? _pick.__person_candidates.map(String)
  : (_pick.__person_id ? [String(_pick.__person_id)] : []);
const candRaw = Array.isArray(_pick.__person_candidates)
  ? _pick.__person_candidates
  : (_pick.__person_id ? [_pick.__person_id] : []);
const candSet = new Set(cand);
const leads = ($json.data ?? []) || [];
const live = leads.filter(l => !l.is_archived);
// page saturation: if the whole page is ours-or-not, we cannot tell whether an older lead exists.
// Reported, never silent - same rule as the digest.
const saturated = leads.length >= 500;
const mine = candSet.size ? live.filter(l => candSet.has(String(l.person_id))) : [];
const CK = F.lead_campaign;
const canon2 = (s) => String(s ?? '').replace(/[\u00a0\u2007\u202f]/g, ' ').replace(/\s+/g, ' ').trim();
let hit = mine.find(l => canon2(l[CK]) === canon2(n.campaign_name)) || null;
let how = hit ? 'campaign_field' : null;
if (!hit && n.campaign_id) {
  const pre = String(n.campaign_id) + ' - ';
  hit = mine.find(l => String(l.title || '').startsWith(pre)) || null;
  if (hit) how = 'title_prefix';
}
// ADOPT the person that actually holds the campaign's lead. This is the whole point: the lead is
// the authority, not the arbitrary first search hit. 6 of 7 matrix replies missed their CRM update
// because the lead hung off a different duplicate than the one we had picked.
const provisional = candRaw.length ? candRaw[0] : null;
const personId = hit ? (hit.person_id ?? provisional) : provisional;
let org = null;
try { org = $('Person Id Final').first().json.__org_id; } catch (e) { org = null; }
return [{ json: { __lead_exists: !!hit, __lead_id: hit ? hit.id : null,
                  __lead_how: how || 'none', __person_id: personId, __org_id: org,
                  __person_adopted: !!(hit && provisional && String(hit.person_id) !== String(provisional)),
                  __leads_page_saturated: saturated } }];
"""))
    add(ifnode("wf2-s22", "IF Lead Exists", [6520, y + 170], "={{ $json.__lead_exists === true }}", "wf2-cs22"))
    add(code("wf2-s23", "NoOp Lead Exists", [6720, y + 60], "return [{ json: { skipped: 'lead_exists' } }];"))
    lc_n, lc_c, lc_entry, lc_live = write_triple("wf2-s24", "Lead Create", [6720, y + 300], BODY_LEAD_CREATE,
                                                 "POST", PD + "{{ '/v1/leads' }}")
    add(lc_n, lc_c)

    add(conns=two("IF Nurture SENT", "NoOp Nurture SENT", "IF First Email"))
    add(conns=two("IF First Email", "IF Need Enrich", "NoOp Repeat SENT"))
    add(conns=two("IF Need Enrich", "SL Fetch Lead", "Person Search"))
    add(conns=one("SL Fetch Lead", "Apply Enrich"))
    add(conns=one("Apply Enrich", "Person Search"))
    add(conns=one("Person Search", "Person Pick"))
    add(ifnode("wf2-s09g", "IF Person Resolved", [3620, y + 120],
               "={{ $json.__person_found === true }}", "wf2-cs09g"))
    add(conns=one("Person Pick", "IF Person Resolved"))
    # B22: no resolve -> no verify. The GET was firing as /persons/0 on every no-match.
    add(conns=two("IF Person Resolved", "Person Verify", "Org Search"))
    add(conns=one("Person Verify", "Person Verify Apply"))
    # one output, two consumers: the main chain continues AND the deleted-check tees off
    add(conns={"Person Verify Apply": {"main": [[{"node": "Org Search", "type": "main", "index": 0},
                                                 {"node": "IF Person Deleted", "type": "main", "index": 0}]]}})
    add(conns=two("IF Person Deleted", "Ops Warn Deleted Person", "NoOp Person Live"))
    add(conns=one("Org Search", "Org Resolve"))
    add(conns=two("IF Org Found", "Carry Person Ctx", oc_entry))
    add(conns=one("Org Resolve", "IF Org Found"))
    add(conns=one(oc_live, "Org Id After Create"))
    add(conns=one("Org Id After Create", "Carry Person Ctx"))
    add(conns=one("Carry Person Ctx", "IF Person Found"))
    add(conns=two("IF Person Found", pp_entry, pc_entry))
    add(conns=one(pp_live, "Person Id Final"))
    add(conns=one(pc_live, "Person Id Final"))
    add(conns=one("Person Id Final", "IF Have Person Id"))
    add(conns=two("IF Have Person Id", "Lead List", "Lead List Skipped"))
    add(conns=one("Lead List", "Lead Select"))
    add(conns=one("Lead List Skipped", "Lead Select"))
    add(conns=one("Lead Select", "IF Lead Exists"))
    add(conns=two("IF Lead Exists", "NoOp Lead Exists", lc_entry))

    # ======================================================= REPLIED branch
    ry = 900
    add(ifnode("wf2-r01", "IF Nurture REPLIED", [2400, ry],
               "={{ $('Normalize').item.json.is_nurture === true }}", "wf2-cr01"))
    nu_n, nu_c, nu_entry, nu_live = write_triple("wf2-r02", "Nurture Alert", [2600, ry - 200],
                                                 "return [{ json: { __body: {}, __intended: { node: 'Nurture Alert', method: 'POST', url: 'slack:replies', body: { nurture: true } } } }];",
                                                 "POST", None, cred, channel_key="slack_channel_replies",
                                                 text_expr=NURTURE_TEXT)
    add(nu_n, nu_c)
    add(http("wf2-r03", "R Person Search", [2600, ry + 80], "GET",
             PD + "{{ '/api/v2/persons/search?fields=email&exact_match=true&limit=20&term=' + encodeURIComponent($('Normalize').item.json.lead.email) }}",
             body=False, retry=True))
    add(code("wf2-r04", "R Person Pick", [2800, ry + 80], r"""
// B27: emit every email-verified candidate instead of deciding on the first hit. Pipedrive search
// order is relevance-based and unstable, and duplicates are normal (Make makes one person per send).
// The provisional id is the OLDEST, which is the only deterministic choice; the real decision is
// made downstream by whichever lead actually belongs to this campaign.
const items = ($json.data?.items ?? []) || [];
const want = String($('Normalize').item.json.lead.email || '').toLowerCase();
const cands = [];
for (const it of items) {
  const p = it.item ?? it;
  const mails = [].concat(p.emails ?? p.email ?? [])
    .map(e => String((e && e.value) ? e.value : e).toLowerCase());
  // B/U previously took items[0] with NO email check - a fuzzy match could be a different person
  if (mails.includes(want)) cands.push(p);
}
cands.sort((a, b) => Number(a.id) - Number(b.id));
const hit = cands.length ? cands[0] : null;
return [{ json: { __person: hit, __person_id: hit ? hit.id : null, __person_found: !!hit,
                  __person_candidates: cands.map(c => c.id),
                  __person_dupes: cands.length > 1 } }];
"""))
    # B19: same guard on the reply path -> deleted means the no-lead branch
    add(http("wf2-r05b", "R Person Verify", [2880, ry + 20], "GET",
             PD + "{{ '/api/v2/persons/' + ($('R Person Pick').item.json.__person_id || 0) }}",
             body=False, retry=True, cof=True))
    add(code("wf2-r05c", "R Person Verify Apply", [2940, ry + 80], VERIFY_APPLY_REPLY))
    add(http("wf2-r05", "R Lead List", [3000, ry + 80], "GET",
             PD + "{{ '/v1/leads?limit=500&archived_status=all&sort=add_time%20DESC' }}",
             body=False, retry=True, cof=True))
    add(code("wf2-r06", "Lead Resolve", [3200, ry + 80], LEAD_RESOLVE))
    add(code("wf2-r07", "Merge Reply Ctx", [3400, ry + 80], r"""
const lr = $json;
let pj = {};
const pv = (() => {
  // B19 completion: reading the raw pick here bypassed the deleted-person guard entirely - and
  // Person Id Final would then attach a new lead to the DELETED person's id.
  try { const v = $('R Person Verify Apply').item.json; if (v && '__person_found' in v) return v; } catch (e) {}
  return $('R Person Pick').item.json;
})();
pj = pv;
return [{ json: { ...pj, ...lr } }];
"""))
    add(ifnode("wf2-r08", "IF No Lead", [3600, ry + 80], "={{ $json.__no_lead === true }}", "wf2-cr08"))
    add(code("wf2-r09", "First Reply Gate", [3800, ry + 80], FIRST_REPLY_GATE))
    add(ifnode("wf2-r10", "IF Should Alert", [4000, ry + 80], "={{ $json.__should_alert === true }}", "wf2-cr10"))
    al_n, al_c, al_entry, al_live = write_triple("wf2-r11", "Reply Alert", [4200, ry - 60],
                                                 # B25: spreads $json, so it must state its own __skip. Nothing upstream sets the flag today,
                                                 # but that is not a guarantee - an inherited __skip is how a write vanishes silently.
                                                 "return [{ json: { ...$json, __body: {}, __skip: false, __intended: { node: 'Reply Alert', method: 'POST', url: 'slack:replies', body: { alert: true } } } }];",
                                                 "POST", None, cred, channel_key="slack_channel_replies",
                                                 text_expr=ALERT_TEXT)
    add(al_n, al_c)
    add(code("wf2-r12", "Classify Body", [4200, ry + 200], CLASSIFY_BODY))
    # classify_enabled: the Anthropic credential is an organizational deferral, so the LLM leg must be
    # switchable without touching the graph. Flag OFF routes into the SAME Classify Parse guardrail that
    # already handles an unparseable answer, rather than duplicating the degraded semantics anywhere.
    add(ifnode("wf2-r12b", "IF Classify Enabled", [4300, ry + 200],
               "={{ $('CONFIG').item.json.classify_enabled === true }}", "wf2-cr12b"))
    add(code("wf2-r12c", "Classify Skipped", [4400, ry + 340], r"""
// Flag-off leg. An empty payload makes Classify Parse fall into its guardrail:
//   category 'Uncategorized' -> __category_id null -> SL Category takes its skip path
//   __is_dnc false           -> no TEXT-derived DNC (the UNSUBSCRIBED event path is untouched)
//   __forwardable            -> CFG.forward_on_uncategorized, i.e. fail-open forwarding
// __classify_disabled marks this as an EXPECTED state so IF Classify Failed does not warn on
// every single reply for the whole shadow window.
// F5 (Nik): while our classifier is off, Smartlead's own category is the source, so the shadow
// diff measures REAL SL-writeback / forward / DNC gating instead of a fail-open placeholder.
// Shaped like an LLM answer so the existing Classify Parse guardrail handles it unchanged.
const nz = $('Normalize').item.json;
const native = nz.reply_category || null;
if (!native) return [{ json: { __classify_disabled: true, __category_source: 'none' } }];
// shaped like an OpenAI answer (choices[0].message.content) so Classify Parse handles the native
// category through exactly the same path as a real completion - one contract, not two.
return [{ json: { __classify_disabled: true, __category_source: 'smartlead-native',
                  choices: [{ message: { content: JSON.stringify({
                    category: native, confidence: 1,
                    is_dnc: native === 'Do Not Contact',
                    one_line_summary: null }) } }] } }];
"""))
    add(http("wf2-r13", "LLM Classify", [4500, ry + 200], "POST",
             LLM, retry=True, cof=True))   # base from CONFIG.llm.base so the C-double can mock it
    add(code("wf2-r14", "Classify Parse", [4600, ry + 200], CLASSIFY_PARSE))
    add(ifnode("wf2-r15", "IF Classify Failed", [4800, ry + 200],
               "={{ $json.__classify_ok !== true && $json.__classify_disabled !== true }}", "wf2-cr15"))
    cat_n, cat_c, cat_entry, cat_live = write_triple("wf2-r16", "SL Category", [5000, ry + 320],
                                                     BODY_SL_CATEGORY, "POST",
                                                     SL + "{{ '/campaigns/' + $('Normalize').item.json.campaign_id + '/leads/' + $('Normalize').item.json.sl_lead_id + '/category' }}",
                                                     cof=True)
    add(cat_n, cat_c)
    # B18: these two sit downstream of the SL Category HTTP call, so $json is Smartlead's ack and
    # the classification is gone. Read them from Classify Parse by name. Symptom before the fix:
    # __forwardable was true and the item still took the false branch - forwarding NEVER fired, and
    # classification-derived DNC never fired either. Both are core features.
    add(ifnode("wf2-r17", "IF DNC", [5560, ry + 320],
               "={{ $('Classify Parse').item.json.__is_dnc === true }}", "wf2-cr17"))
    un_n, un_c, un_entry, un_live = write_triple("wf2-r18", "SL Unsubscribe", [5760, ry + 180],
                                                 BODY_SL_UNSUB, "POST",
                                                 SL + "{{ '/leads/' + $('Normalize').item.json.sl_lead_id + '/unsubscribe' }}",
                                                 cof=True)
    add(un_n, un_c)
    add(code("wf2-r19", "Mark DNC", [6320, ry + 180], r"""
// B12: this sits AFTER the SL Unsubscribe HTTP call, so $json is the Smartlead ack - spreading it
// carried none of the reply context onward and the downstream label union lost `existing`.
// Rebuild from the nodes that own the context.
const pick = (nm) => { try { return $(nm).item.json || {}; } catch (e) { return {}; } };
const base = { ...pick('Merge Reply Ctx'), ...pick('Classify Parse') };
return [{ json: { ...base, __dnc_label: true, __forwardable: false } }];
"""))
    add(ifnode("wf2-r20", "IF Forwardable", [5760, ry + 460],
               "={{ $('Classify Parse').item.json.__forwardable === true }}", "wf2-cr20"))
    add(code("wf2-r21", "Forward Resolve", [5960, ry + 460], FORWARD_RESOLVE))
    add(ifnode("wf2-r22", "IF Inbox Known", [6160, ry + 460], "={{ $json.__forward_miss !== true }}", "wf2-cr22"))
    add(http("wf2-r23", "SL Message History", [6360, ry + 460], "GET",
             SL + "{{ '/campaigns/' + $('Normalize').item.json.campaign_id + '/leads/' + $('Normalize').item.json.sl_lead_id + '/message-history' }}",
             body=False, retry=True, cof=True))
    add(code("wf2-r24", "Pick Last Message", [6560, ry + 460], r"""
let hist = [];
try { hist = $json.history ?? $json.data?.history ?? $json.data ?? []; } catch (e) { hist = []; }
if (!Array.isArray(hist)) hist = [];
// B8/3: we forward the PROSPECT'S reply, so anchor on the last REPLY entry, not the last entry.
// Live history is [SENT, REPLY, ...]; a follow-up landing after the reply would otherwise make us
// forward our own outbound email. Falls back to the last entry when no REPLY is present.
const replies = hist.filter((h) => String(h?.type || '').toUpperCase() === 'REPLY');
const last = replies.length ? replies[replies.length - 1] : (hist.length ? hist[hist.length - 1] : {});
let ctx = {};
try { ctx = $('Forward Resolve').item.json; } catch (e) {}
return [{ json: { ...ctx, __history: hist, __message_id: last.message_id ?? null, __stats_id: last.stats_id ?? null } }];
"""))
    fw_n, fw_c, fw_entry, fw_live = write_triple("wf2-r25", "SL Forward Email", [6760, ry + 460],
                                                 BODY_FORWARD, "POST",
                                                 SL + "{{ '/campaigns/' + $('Normalize').item.json.campaign_id + '/forward-email' }}",
                                                 cof=True)
    add(fw_n, fw_c)

    # CRM writes chain
    lb_n, lb_c, lb_entry, lb_live = write_triple("wf2-r26", "Lead Labels Union", [7400, ry + 320],
                                                 BODY_LABELS, "PATCH",
                                                 PD + "{{ '/v1/leads/' + $json.__lead_id }}")
    add(lb_n, lb_c)
    ra_n, ra_c, ra_entry, ra_live = write_triple("wf2-r27", "Reply Activity", [7960, ry + 320],
                                                 BODY_REPLY_ACTIVITY, "POST",
                                                 PD + "{{ '/api/v2/activities' }}", cof=True)
    add(ra_n, ra_c)
    add(code("wf2-r28", "Reply CRM Done", [8520, ry + 320], "return [{ json: { done: true } }];"))

    add(conns=two("IF Nurture REPLIED", nu_entry, "R Person Search"))
    add(conns=one("R Person Search", "R Person Pick"))
    add(ifnode("wf2-r05d", "IF R Person Resolved", [2840, ry + 80],
               "={{ $json.__person_found === true }}", "wf2-cr05d"))
    add(conns=one("R Person Pick", "IF R Person Resolved"))
    add(conns=two("IF R Person Resolved", "R Person Verify", "R Lead List"))
    add(conns=one("R Person Verify", "R Person Verify Apply"))
    add(conns={"R Person Verify Apply": {"main": [[{"node": "R Lead List", "type": "main", "index": 0},
                                                   {"node": "IF Person Deleted", "type": "main", "index": 0}]]}})
    add(conns=one("R Lead List", "Lead Resolve"))
    add(conns=one("Lead Resolve", "Merge Reply Ctx"))
    add(conns=one("Merge Reply Ctx", "IF No Lead"))
    add(conns={"IF No Lead": {"main": [[{"node": "Ops Warn No Lead", "type": "main", "index": 0},
                                        {"node": "First Reply Gate", "type": "main", "index": 0}],
                                       [{"node": "First Reply Gate", "type": "main", "index": 0}]]}})
    add(conns=one("First Reply Gate", "IF Should Alert"))
    add(conns=two("IF Should Alert", al_entry, "Classify Body"))
    add(conns=one(al_live, "Classify Body"))
    add(conns=one("Classify Body", "IF Classify Enabled"))
    add(conns=two("IF Classify Enabled", "LLM Classify", "Classify Skipped"))
    add(conns=one("LLM Classify", "Classify Parse"))
    add(conns=one("Classify Skipped", "Classify Parse"))
    add(conns=one("Classify Parse", "IF Classify Failed"))
    add(conns={"IF Classify Failed": {"main": [[{"node": "Ops Warn Classify", "type": "main", "index": 0},
                                                {"node": cat_entry, "type": "main", "index": 0}],
                                               [{"node": cat_entry, "type": "main", "index": 0}]]}})
    add(conns=one(cat_live, "IF DNC"))
    add(conns=two("IF DNC", un_entry, "IF Forwardable"))
    add(conns=one(un_live, "Mark DNC"))
    add(conns=one("Mark DNC", lb_entry))
    add(conns=two("IF Forwardable", "Forward Resolve", lb_entry))
    add(conns=one("Forward Resolve", "IF Inbox Known"))
    add(conns={"IF Inbox Known": {"main": [[{"node": "SL Message History", "type": "main", "index": 0}],
                                           [{"node": "Ops Warn Unknown Inbox", "type": "main", "index": 0},
                                            {"node": "SL Message History", "type": "main", "index": 0}]]}})
    add(conns=one("SL Message History", "Pick Last Message"))
    add(conns=one("Pick Last Message", fw_entry))
    add(conns=one(fw_live, lb_entry))
    add(conns=one(lb_live, ra_entry))
    add(conns=one(ra_live, "Reply CRM Done"))

    # ======================================================= BOUNCED
    by = 1900
    add(http("wf2-b01", "B Person Search", [2400, by], "GET",
             PD + "{{ '/api/v2/persons/search?fields=email&exact_match=true&limit=20&term=' + encodeURIComponent($('Normalize').item.json.lead.email) }}",
             body=False, retry=True, cof=True))
    add(code("wf2-b02", "B Lead Ctx", [2600, by], r"""
// B27: emit every email-verified candidate instead of deciding on the first hit. Pipedrive search
// order is relevance-based and unstable, and duplicates are normal (Make makes one person per send).
// The provisional id is the OLDEST, which is the only deterministic choice; the real decision is
// made downstream by whichever lead actually belongs to this campaign.
const items = ($json.data?.items ?? []) || [];
const want = String($('Normalize').item.json.lead.email || '').toLowerCase();
const cands = [];
for (const it of items) {
  const p = it.item ?? it;
  const mails = [].concat(p.emails ?? p.email ?? [])
    .map(e => String((e && e.value) ? e.value : e).toLowerCase());
  // B/U previously took items[0] with NO email check - a fuzzy match could be a different person
  if (mails.includes(want)) cands.push(p);
}
cands.sort((a, b) => Number(a.id) - Number(b.id));
const hit = cands.length ? cands[0] : null;
return [{ json: { __person: hit, __person_id: hit ? hit.id : null, __person_found: !!hit,
                  __person_candidates: cands.map(c => c.id),
                  __person_dupes: cands.length > 1 } }];
"""))
    add(http("wf2-b03", "B Lead List", [2800, by], "GET",
             PD + "{{ '/v1/leads?limit=500&archived_status=all&sort=add_time%20DESC' }}",
             body=False, retry=True, cof=True))
    add(code("wf2-b04", "B Lead Select", [3000, by], LEAD_RESOLVE))
    bn_n, bn_c, bn_entry, bn_live = write_triple("wf2-b05", "Bounce Note", [3200, by],
                                                 BODY_BOUNCE_NOTE, "POST",
                                                 PD + "{{ '/api/v2/activities' }}", cof=True)
    add(bn_n, bn_c)
    add(conns=one("B Person Search", "B Lead Ctx"))
    add(conns=one("B Lead Ctx", "B Lead List"))
    add(conns=one("B Lead List", "B Lead Select"))
    add(conns=one("B Lead Select", bn_entry))

    # ======================================================= UNSUB (DNC minus classify)
    uy = 2300
    add(http("wf2-u01", "U Person Search", [2400, uy], "GET",
             PD + "{{ '/api/v2/persons/search?fields=email&exact_match=true&limit=20&term=' + encodeURIComponent($('Normalize').item.json.lead.email) }}",
             body=False, retry=True, cof=True))
    add(code("wf2-u02", "U Lead Ctx", [2600, uy], r"""
// B27: emit every email-verified candidate instead of deciding on the first hit. Pipedrive search
// order is relevance-based and unstable, and duplicates are normal (Make makes one person per send).
// The provisional id is the OLDEST, which is the only deterministic choice; the real decision is
// made downstream by whichever lead actually belongs to this campaign.
const items = ($json.data?.items ?? []) || [];
const want = String($('Normalize').item.json.lead.email || '').toLowerCase();
const cands = [];
for (const it of items) {
  const p = it.item ?? it;
  const mails = [].concat(p.emails ?? p.email ?? [])
    .map(e => String((e && e.value) ? e.value : e).toLowerCase());
  // B/U previously took items[0] with NO email check - a fuzzy match could be a different person
  if (mails.includes(want)) cands.push(p);
}
cands.sort((a, b) => Number(a.id) - Number(b.id));
const hit = cands.length ? cands[0] : null;
return [{ json: { __person: hit, __person_id: hit ? hit.id : null, __person_found: !!hit,
                  __person_candidates: cands.map(c => c.id),
                  __person_dupes: cands.length > 1 } }];
"""))
    add(http("wf2-u03", "U Lead List", [2800, uy], "GET",
             PD + "{{ '/v1/leads?limit=500&archived_status=all&sort=add_time%20DESC' }}",
             body=False, retry=True, cof=True))
    add(code("wf2-u04", "U Lead Select", [3000, uy], LEAD_RESOLVE))
    uu_n, uu_c, uu_entry, uu_live = write_triple("wf2-u05", "U SL Unsubscribe", [3200, uy],
                                                 BODY_SL_UNSUB, "POST",
                                                 SL + "{{ '/leads/' + $('Normalize').item.json.sl_lead_id + '/unsubscribe' }}",
                                                 cof=True)
    add(uu_n, uu_c)
    # B12: same as Mark DNC - $json here is the Smartlead unsubscribe ack, not the lead context.
    add(code("wf2-u06", "U Mark DNC", [3760, uy], r"""
const pick = (nm) => { try { return $(nm).item.json || {}; } catch (e) { return {}; } };
return [{ json: { ...pick('U Lead Select'), __dnc_label: true } }];
"""))
    ul_n, ul_c, ul_entry, ul_live = write_triple("wf2-u07", "U Lead DNC Label", [3960, uy],
                                                 BODY_LABELS, "PATCH",
                                                 PD + "{{ '/v1/leads/' + $json.__lead_id }}")
    add(ul_n, ul_c)
    add(conns=one("U Person Search", "U Lead Ctx"))
    add(conns=one("U Lead Ctx", "U Lead List"))
    add(conns=one("U Lead List", "U Lead Select"))
    add(conns=one("U Lead Select", uu_entry))
    add(conns=one(uu_live, "U Mark DNC"))
    add(conns=one("U Mark DNC", ul_entry))

    # ======================================================= marker warn tee (off Normalize path)
    add(ifnode("wf2-m01", "IF Unknown Marker", [2400, 2700],
               "={{ !!$('Normalize').item.json.marker_unknown }}", "wf2-cm01"))
    add(conns=two("IF Unknown Marker", "Ops Warn Unknown Marker", "NoOp Marker OK"))
    add(code("wf2-m02", "NoOp Marker OK", [2600, 2820], "return [{ json: { marker: 'ok' } }];"))

    return N, C
