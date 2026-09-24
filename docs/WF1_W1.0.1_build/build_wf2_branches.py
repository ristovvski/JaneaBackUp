"""WF-2 builder - branch library (imported by build_wf2.py).

Holds the node factories for SENT / REPLIED / BOUNCED / UNSUB / default plus the
WRITE_MODE gate machinery. Split out so each file stays reviewable.

WRITE_MODE pattern (architecture SS6): every write is a triple
    [Body <X>]  (Code: builds body + __intended)  ->  [Gate <X>] (IF WRITE_MODE==live)
        true  -> [<X>]         (the real HTTP/Slack node)
        false -> [Shadow Log]  (single shared recorder)
Ops-channel warns/errors are NOT gated - observability is never shadowed.
"""
import json

PD = "={{ $('CONFIG').item.json.pd_api }}"
SL = "={{ $('CONFIG').item.json.sl_api }}"
LLM = "={{ $('CONFIG').item.json.llm.base }}"

# B7 auth fix. Every HTTP node MUST carry a credential or it 401s - including the two ungated
# Smartlead READS (SL Fetch Lead, SL Message History) and LLM Classify, which run even in shadow.
# The instance today holds exactly two credentials (enumerated read-only across all workflows):
#   pipedriveApi 'Pipedrive account'  HnyULgvDdYp0lIkB   (same one production WF-1 uses)
#   slackApi     'Slack account 3'    Udq1K604RpJqg1cR
# SL_CRED / LLM_CRED are DEPLOY GATES: Nik must create them in the n8n UI (no key may live in
# the workflow JSON - see static AU4). validate() refuses to call the build deploy-ready until then.
PD_CRED = {"pipedriveApi": {"id": "HnyULgvDdYp0lIkB", "name": "Pipedrive account"}}
SL_CRED = {"httpQueryAuth": {"id": "YXf5ez4pxDNd2g2B", "name": "Smartlead API"}}
# Nik's credential, PROBED not assumed: it resolves as n8n's native `openAiApi` type, NOT the
# httpHeaderAuth the brief described - binding it as httpHeaderAuth failed with
# 'Credential with ID "ltWhbdbiCcOBKnLn" does not exist for type "httpHeaderAuth"'.
# With the predefined type n8n injects Authorization itself, so the credential stores just the key
# and rotation is: paste the new key here, no rebuild. THIS is the single bound credential.
LLM_CRED = {"openAiApi": {"id": "ltWhbdbiCcOBKnLn", "name": "OpenAI API"}}


# ----------------------------------------------------------------- helpers
def _n(nid, name, ntype, tv, pos, params, **extra):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype, "typeVersion": tv, "position": pos}
    n.update(extra)
    return n


def code(nid, name, pos, js, **extra):
    return _n(nid, name, "n8n-nodes-base.code", 2, pos, {"jsCode": js}, **extra)


def ifnode(nid, name, pos, expr, cid):
    return _n(nid, name, "n8n-nodes-base.if", 2, pos,
              {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                          "typeValidation": "strict", "version": 1},
                              "conditions": [{"id": cid, "leftValue": expr, "rightValue": True,
                                              "operator": {"type": "boolean", "operation": "true",
                                                           "singleValue": True}}],
                              "combinator": "and"}, "options": {}})


def http(nid, name, pos, method, url, *, body=True, retry=False, cof=False):
    # n8n expression fields carry ONE leading '='; text outside {{ }} is literal. Concatenating
    # PD + '={{ ... }}' therefore injected a literal '=' mid-URL ("https://api.pipedrive.com=/api/v2/...").
    # It hit 23 of 24 nodes. Refuse to build that shape ever again (statics URL1/URL2 assert the
    # evaluated result, since the raw string looked plausible enough to survive a whole phase).
    assert "}}={{" not in url, f"{name}: literal '=' between expression segments: {url[:80]}"
    hdrs = [{"name": "Content-Type", "value": "application/json"}]
    # auth is inferred from the host so no future call site can forget it (AU1-AU3 lock this)
    auth, cred = {}, None
    if url.startswith(PD):
        auth = {"authentication": "predefinedCredentialType", "nodeCredentialType": "pipedriveApi"}
        cred = PD_CRED
    elif url.startswith(SL):
        auth = {"authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth"}
        cred = SL_CRED
    elif url.startswith(LLM):
        # predefined type: n8n supplies the Authorization header from the credential, so no auth
        # material appears in the workflow JSON (AU4) and no header literal can drift out of date
        auth = {"authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi"}
        cred = LLM_CRED
        # provider switched to OpenAI: no anthropic-version header, and Authorization comes from
        # the credential ("OpenAI API", httpHeaderAuth Bearer) - never from the workflow JSON.
    else:
        raise AssertionError(f"{name}: unknown host, refusing to build an unauthenticated node: {url[:60]}")
    p = {"method": method, "url": url, "sendHeaders": True,
         "headerParameters": {"parameters": hdrs}, "options": {}}
    p.update(auth)
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.__body) }}"})
    extra = {}
    if cred:
        extra["credentials"] = cred
    if retry:
        extra.update({"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 1000})
    else:
        extra.update({"retryOnFail": False})
    if cof:
        extra.update({"onError": "continueRegularOutput"})
    return _n(nid, name, "n8n-nodes-base.httpRequest", 4.2, pos, p, **extra)


def slack_first(nid, name, pos, channel_key, text_expr, cred, cof=True):
    """Slack node whose channel is resolved with .first() instead of .item.

    For any workflow where the Slack node sits downstream of a fan-out, `$('CONFIG').item` cannot
    resolve its paired item. WF-2 does not have that problem (single-item chain) and keeps using
    slack(); WF-2H and WF-2S do, and use this.
    """
    extra = {"credentials": cred}
    if cof:
        extra["onError"] = "continueRegularOutput"
    return _n(nid, name, "n8n-nodes-base.slack", 2.3, pos,
              {"select": "channel",
               "channelId": {"__rl": True, "mode": "id",
                             "value": "={{ $('CONFIG').first().json." + channel_key + " }}"},
               "text": text_expr, "otherOptions": {}}, **extra)


def slack(nid, name, pos, channel_key, text_expr, cred, cof=True):
    extra = {"credentials": cred}
    if cof:
        extra["onError"] = "continueRegularOutput"
    return _n(nid, name, "n8n-nodes-base.slack", 2.3, pos,
              {"select": "channel",
               "channelId": {"__rl": True, "value": "={{ $('CONFIG').item.json." + channel_key + " }}",
                             "mode": "id"},
               "text": text_expr, "otherOptions": {}}, **extra)


# B14: the gate is the ONLY place a write can be stopped, so it must honour BOTH conditions.
# Six bodies computed __skip and nothing ever read it - which meant the "locked" category
# fail-safe would still have POSTed category_id:null, and a no-lead reply would still have
# PATCHed /v1/leads/undefined. Skipped writes fall through to Shadow Log, same as shadow mode.
GATE_EXPR = ("={{ $('CONFIG').item.json.WRITE_MODE === 'live'"
             " && $json.__skip !== true }}")


def write_triple(prefix, label, pos, body_js, method, url, cred=None, *,
                 channel_key=None, text_expr=None, retry=False, cof=False):
    """Returns (nodes, conns_fragment, entry_name, live_node_name)."""
    bn, gn, wn = f"Body {label}", f"Gate {label}", label
    nodes = [
        code(f"{prefix}-body", bn, [pos[0], pos[1]], body_js),
        ifnode(f"{prefix}-gate", gn, [pos[0] + 180, pos[1]], GATE_EXPR, f"{prefix}-c"),
    ]
    if channel_key:
        nodes.append(slack(f"{prefix}-w", wn, [pos[0] + 360, pos[1]], channel_key, text_expr, cred))
    else:
        nodes.append(http(f"{prefix}-w", wn, [pos[0] + 360, pos[1]], method, url, retry=retry, cof=cof))
    conns = {
        bn: {"main": [[{"node": gn, "type": "main", "index": 0}]]},
        gn: {"main": [[{"node": wn, "type": "main", "index": 0}],
                      [{"node": "Shadow Log", "type": "main", "index": 0}]]},
    }
    return nodes, conns, bn, wn


# ----------------------------------------------------------------- shared JS
CANON_HELPERS = r"""
const CFG = $('CONFIG').item.json;
const F = CFG.fields;
// B16: Apply Enrich published its result as __enriched and every consumer read $('Normalize')
// instead, so enrichment was computed and thrown away. It shows up as company:null -> Pipedrive
// "Validation failed: name: Missing required field", because the REAL EMAIL_SENT payload carries
// no lead_data at all. Prefer the enriched copy; fall back on paths where enrichment never ran.
const n = (() => {
  try { const e = $('Apply Enrich').item.json.__enriched; if (e && e.lead) return e; } catch (x) {}
  return $('Normalize').item.json;
})();
const omit = (o) => { for (const k of Object.keys(o)) { const v = o[k]; if (v === '' || v === null || v === undefined) delete o[k]; } return o; };
"""

# --- SENT: person body (create) -------------------------------------------------
BODY_PERSON_CREATE = CANON_HELPERS + r"""
// Nik's field-fill directive: standard fields AND the lh_ mirrors, everything with a sensible home.
const org = $json.__org_id ?? null;
const cf = {};
const title = n.lead.title;
if (title) { cf[F.position_lh] = title; cf[F.title_std_cf] = title; cf[F.title_linkedin] = title; }
if (n.lead.company) cf[F.company_lh] = n.lead.company;
if (n.lead.linkedin) { cf[F.linkedin_lh] = n.lead.linkedin; cf[F.linkedin_profile] = n.lead.linkedin; }
if (n.lead.location) cf[F.location_lh] = n.lead.location;
if (n.campaign_name) cf[F.campaign] = n.campaign_name;            // canon
if (n.hypothesis) cf[F.hypothesis] = n.hypothesis;
if (n.event_name) cf[F.event_name] = n.event_name;
cf[F.medium] = CFG.medium_value;                                   // eMail
cf[F.source] = CFG.source_value;                                   // 446 create-only
omit(cf);
const body = { name: n.lead.full_name || n.lead.email, owner_id: CFG.owner_id, custom_fields: cf };
// B17: NOT job_title. Pipedrive 403s on this tenant - "Contact sync fields are not allowed
// because contact sync is not enabled (postal_address, im, notes, birthday, job_title)". Every
// person create would have failed. The three title mirrors above already carry the value, so
// Nik's fill-as-much-as-possible directive is satisfied without the standard field.
if (n.lead.email) body.emails = [{ value: n.lead.email, primary: true, label: 'work' }];
if (org) body.org_id = org;
return [{ json: { __body: body, __intended: { node: 'Person Create', method: 'POST', url: '/api/v2/persons', body } } }];
"""

# --- SENT: person patch (existing person, fill-if-empty + campaign overwrite) ----
BODY_PERSON_PATCH = CANON_HELPERS + r"""
const cur = ($json.__person?.custom_fields) ?? {};
const val = (k) => { const v = cur[k]; return (v && typeof v === 'object') ? v.value : v; };
const cf = {};
const title = n.lead.title;
if (title) { for (const k of [F.position_lh, F.title_std_cf, F.title_linkedin]) if (!val(k)) cf[k] = title; }
if (n.lead.company && !val(F.company_lh)) cf[F.company_lh] = n.lead.company;
if (n.lead.linkedin) { for (const k of [F.linkedin_lh, F.linkedin_profile]) if (!val(k)) cf[k] = n.lead.linkedin; }
if (n.lead.location && !val(F.location_lh)) cf[F.location_lh] = n.lead.location;
if (!val(F.medium)) cf[F.medium] = CFG.medium_value;               // fill-if-empty (cross-channel safe)
if (n.hypothesis && val(F.hypothesis) !== n.hypothesis) cf[F.hypothesis] = n.hypothesis;
if (n.event_name && val(F.event_name) !== n.event_name) cf[F.event_name] = n.event_name;
// ALWAYS-OVERWRITE exception (W1.0.11.1 semantics extended to email):
if (n.campaign_name && val(F.campaign) !== n.campaign_name) cf[F.campaign] = n.campaign_name;
omit(cf);
const body = { custom_fields: cf };
// B17: same here - job_title is unwritable on this tenant (contact sync disabled).
const orgId = $json.__org_id ?? null;
if (orgId && !$json.__person?.org_id) body.org_id = orgId;         // link fill-if-empty
const empty = Object.keys(cf).length === 0 && !body.org_id;
return [{ json: { __body: body, __skip: empty, __person_id: $json.__person?.id ?? null,
  __intended: { node: 'Person Patch', method: 'PATCH', url: '/api/v2/persons/{id}', body } } }];
"""

# --- SENT: lead create ---------------------------------------------------------
BODY_LEAD_CREATE = CANON_HELPERS + r"""
const title = [n.campaign_id, n.campaign_name, n.lead.full_name].filter(v => v !== null && v !== undefined && v !== '').map(String).join(' - ');
const body = {
  title,
  person_id: $json.__person_id ?? null,
  owner_id: CFG.owner_id,
  label_ids: [CFG.labels.cold],                                    // union-of-one on create
  channel: CFG.lead_channel,
};
body[F.lead_campaign] = n.campaign_name;                           // fixes Make's disease #4
body[F.lead_opportunity_type] = CFG.lead_opportunity_type_value;   // 480
const orgId = $json.__org_id ?? null;
if (orgId) body.organization_id = orgId;
omit(body);
return [{ json: { __body: body, __intended: { node: 'Lead Create', method: 'POST', url: '/v1/leads', body } } }];
"""

# --- org resolve + body -------------------------------------------------------
ORG_RESOLVE = CANON_HELPERS + r"""
// exact canonical name match -> website-domain tiebreak; decide create vs link
const items = ($json.data?.items ?? $json.data ?? []) || [];
// canonicalize BOTH sides: the tenant demonstrably carries nbsp/double-space dirt in names,
// so a trim-only compare would miss an existing org and create a duplicate.
const cn = (s) => String(s ?? '').replace(/[   ]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
const want = cn(n.lead.company);
const dom = (u) => String(u || '').toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0];
const wantDom = dom(n.lead.website);
let hit = null;
const exact = items.map(x => x.item ?? x).filter(o => cn(o.name) === want);
if (exact.length === 1) hit = exact[0];
else if (exact.length > 1 && wantDom) hit = exact.find(o => dom(o.address || o.website) === wantDom) || exact[0];
else if (exact.length > 1) hit = exact[0];
return [{ json: { __org_id: hit ? hit.id : null, __org_found: !!hit, __org_ambiguous: exact.length > 1,
                  __org_name_want: n.lead.company } }];
"""

BODY_ORG_CREATE = CANON_HELPERS + r"""
const isLi = (u) => /(^|\.)linkedin\.com/i.test(String(u || ''));
const cf = {};
const w = n.lead.website;
if (w && !isLi(w)) { cf[F.org_website_a] = w; cf[F.org_website_b] = w; cf[F.org_website_lh] = w; }
if (w && isLi(w)) cf[F.org_linkedin_lh] = w;                       // W1.0.12 guard
omit(cf);
const body = { name: n.lead.company, owner_id: CFG.owner_id };
if (Object.keys(cf).length) body.custom_fields = cf;
// B16b: no company name -> POST would be rejected outright. Skip instead (enforced by the gate).
return [{ json: { __body: body, __skip: !n.lead.company,
  __intended: { node: 'Org Create', method: 'POST', url: '/api/v2/organizations', body } } }];
"""

# --- REPLIED: lead resolve ----------------------------------------------------
LEAD_RESOLVE = CANON_HELPERS + r"""
// Campaign-field exact (canon) -> title prefix fallback "{campaign_id} - " (covers pre-convention leads)
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
return [{ json: { __lead: hit, __lead_id: hit ? hit.id : null, __lead_how: how || 'none',
                  __lead_labels: hit ? (hit.label_ids || []) : [],
                  __no_lead: !hit,
                  __person_id: personId,
                  __person_adopted: !!(hit && provisional && String(hit.person_id) !== String(provisional)),
                  __person_candidates: cand,
                  __leads_page_saturated: saturated } }];
"""

FIRST_REPLY_GATE = CANON_HELPERS + r"""
// W1.0.14a parity: alert only on the FIRST human reply per lead. Fail-open.
const labels = $json.__lead_labels;
const readable = Array.isArray(labels);
const already = readable ? labels.includes(CFG.labels.responded) : false;
const alertEvery = CFG.flags?.alert_every_reply === true;
const should = alertEvery ? true : (!readable ? true : !already);   // unreadable -> alert (fail-open)
return [{ json: { ...$json, __should_alert: should, __alert_reason: alertEvery ? 'alert_every_reply' : (!readable ? 'fail_open' : (already ? 'repeat_reply' : 'first_reply')) } }];
"""

ALERT_TEXT = (
    "={{ (() => { const CFG=$('CONFIG').item.json; const n=$('Normalize').item.json; "
    "const esc=(v)=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); "
    "const L=$json.__lead_id; const base=CFG.pipedrive_base; "
    "const who=esc(n.lead.full_name||n.lead.email); "
    "const pos=n.lead.title?esc(n.lead.title):''; const co=n.lead.company?esc(n.lead.company):''; "
    "const paren=(pos||co)?(' ('+[pos,co].filter(Boolean).join(' @ ')+')'):''; "
    "const camp=esc(n.campaign_name); const inbox=esc(n.sender_inbox); "
    # A (Nik, live review): the fallback rendered base+'/person/'+null -> a dead .../person/ link.
    # Two causes: no person exists in the no-lead case, and $json here is post-body context, so the
    # id must be recovered by owner node (same class as B12). No id -> emit NO link at all.
    "const P=(()=>{const g=(nm)=>{try{return $(nm).item.json||{}}catch(e){return{}}}; "
    "return $json.__person_id ?? g('Merge Reply Ctx').__person_id ?? g('R Person Pick').__person_id ?? null;})(); "
    "const link=L?('<'+base+'/leads/inbox/'+L+'|Open lead>')"
    ":(P?('no lead \\u00b7 <'+base+'/person/'+P+'|Open person>'):'no lead \\u00b7 not in CRM yet'); "
    # D (click-verified by Nik). Prefer the payload's OWN app_url: it ships ready-made, so it needs
    # no assumption about whether the REST map id equals the webhook's. Construct only as fallback,
    # and with neither available emit nothing rather than a link that 404s (LK-class rule).
    "const slUrl=(n.sl_app_url || (n.sl_lead_map_id ? (CFG.sl_inbox_base + n.sl_lead_map_id) : null)); "
    "const slLink=slUrl?(' \\u00b7 <'+slUrl+'|Open in Smartlead>'):''; "
    "return '\\ud83d\\udcac '+who+paren+' \\u00b7 '+camp+' \\u00b7 via '+inbox+' \\u2014 '+link+slLink+' \\u00b7 \\u2709\\ufe0f '+esc(n.lead.email); })() }}"
)

NURTURE_TEXT = (
    "={{ (() => { const n=$('Normalize').item.json; "
    "const esc=(v)=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); "
    "return '\\ud83d\\udcac '+esc(n.lead.full_name||n.lead.email)+' \\u00b7 '+esc(n.campaign_name)"
    "+' \\u00b7 \\u2709\\ufe0f '+esc(n.lead.email)+' \\u00b7 nurture'; })() }}"
)

CLASSIFY_BODY = CANON_HELPERS + r"""
const cats = Object.keys(CFG.category_map || {});
const catList = cats.length ? cats.join(', ') : 'Interested, Meeting Request, Not Interested, Information Request, Do Not Contact, Out Of Office, Wrong Person, No Longer Working There, Sender Originated Bounce';
const subject = n.reply.subject || '';
const bodyTxt = String(n.reply.body || '').slice(0, 4000);
const prompt = 'Classify this cold-outreach email reply. Return STRICT JSON only, no prose:\n'
 + '{"category": one of [' + catList + '], "confidence": 0..1, "is_dnc": boolean, "one_line_summary": string}\n\n'
 + 'Subject: ' + subject + '\n\nBody:\n' + bodyTxt;
// OpenAI chat/completions shape. json_object forces a parseable object, which is what makes the
// downstream guardrail meaningful rather than hopeful. No temperature key: current flagships accept
// only the default, and it is not what buys determinism here.
const body = { model: CFG.llm.model,
               max_completion_tokens: CFG.llm.max_completion_tokens,
               response_format: { type: 'json_object' },
               messages: [
                 { role: 'system', content: 'You classify cold-outreach email replies. '
                   + 'Answer with a single JSON object and nothing else.' },
                 { role: 'user', content: prompt }] };
return [{ json: { __body: body,
  __intended: { node: 'LLM Classify', method: 'POST', url: 'openai:/v1/chat/completions', body } } }];
"""

CLASSIFY_PARSE = CANON_HELPERS + r"""
// guardrail: invalid JSON / unknown category / low confidence -> Uncategorized (SL untouched)
// OpenAI puts the answer in choices[0].message.content as a JSON *string*. The legacy shapes are
// kept as fallbacks so a provider swap cannot silently blank every classification, and so the
// Smartlead-native synthetic payload keeps working through the same guardrail.
const raw = (() => {
  try {
    return $json.choices?.[0]?.message?.content
        ?? $json.content?.[0]?.text
        ?? $json.completion
        ?? '';
  } catch (e) { return ''; }
})();
// token cost is reported per classification so the spend is observable, not inferred
const __usage = (() => { try { const u = $json.usage || {};
  return { prompt: u.prompt_tokens ?? null, completion: u.completion_tokens ?? null,
           total: u.total_tokens ?? null, model: $json.model ?? null }; } catch (e) { return {}; } })();
let parsed = null;
try { const m = String(raw).match(/\{[\s\S]*\}/); parsed = m ? JSON.parse(m[0]) : null; } catch (e) { parsed = null; }
const known = Object.keys(CFG.category_map || {});
const minC = Number(CFG.llm?.min_confidence ?? 0.6);
let category = parsed?.category ?? null;
const conf = Number(parsed?.confidence ?? 0);
const okCat = category && (known.length === 0 || known.includes(category));
const ok = !!parsed && okCat && conf >= minC;
if (!ok) category = 'Uncategorized';
const isDnc = ok ? (parsed.is_dnc === true || category === 'Do Not Contact') : false;
const fwdList = CFG.forwardable_categories || [];
const forwardable = ok ? fwdList.includes(category) : (CFG.forward_on_uncategorized === true);
return [{ json: { ...$json, __category: category, __confidence: conf, __is_dnc: isDnc,
  __summary: parsed?.one_line_summary ?? null, __classify_ok: ok, __forwardable: forwardable,
  __category_id: (CFG.category_map || {})[category] ?? null,
  __llm_usage: __usage, __llm_provider: CFG.llm?.provider ?? null,
  // the spread above carries 'smartlead-native'/'none' from the flag-off leg; when the classifier
  // actually ran, name the provider - the diff harness needs to tell our answer from Smartlead's,
  // and that column IS the accuracy report.
  __category_source: $json.__category_source ?? (CFG.llm?.provider ?? 'llm') } }];
"""

FORWARD_RESOLVE = CANON_HELPERS + r"""
// inbox -> owner NAME (sheet col 1 parity) -> owner email; miss -> forward_default + warn
const inboxMap = CFG.forward_inbox_map || {};
const ownerMap = CFG.forward_owner_map || {};
const inbox = String(n.sender_inbox || '').trim().toLowerCase();
const ownerName = inboxMap[inbox] ?? null;

// THREE-WAY ROUTING (Nik). Reaching this node already means "forwardable" - IF Forwardable sent the
// non-forwardable and DNC cases elsewhere, so branch 3 is the absence of a forward, not a target.
//   1. a real category      -> the campaign sender's own mailbox
//   2. Uncategorized / low-confidence / unparseable -> the REVIEW address, because nobody should
//      have to trust a classifier that just told us it was unsure
//   3. DNC / non-forwardable -> never gets here
// A review-routed reply is deliberately NOT sent to the sender: it is unclassified, so routing it
// as if it were qualified would quietly launder low-confidence output into someone's inbox.
const cp = (() => { try { return $('Classify Parse').item.json || {}; } catch (e) { return {}; } })();
const review = cp.__classify_ok !== true;

let to, ownerOut, miss = false, reason;
if (review) {
  to = CFG.forward_review_address;
  ownerOut = null;
  reason = 'review';
} else {
  to = ownerName ? (ownerMap[ownerName] ?? null) : null;
  ownerOut = ownerName;
  miss = !to;                       // unknown inbox: still forwards, but ops is told (FM4)
  if (miss) to = CFG.forward_default;
  reason = miss ? 'owner_miss' : 'owner';
}
return [{ json: { ...$json, __forward_to: String(to || '').trim(), __forward_owner: ownerOut,
  __forward_miss: miss, __forward_reason: reason, __forward_review: review,
  __forward_source: CFG.forward_map_source } }];
"""

BODY_FORWARD = CANON_HELPERS + r"""
const hist = (() => { try { return $json.__history ?? []; } catch (e) { return []; } })();
const last = Array.isArray(hist) && hist.length ? hist[hist.length - 1] : {};
const body = { message_id: $json.__message_id ?? last.message_id ?? n.reply.message_id,
               stats_id: $json.__stats_id ?? last.stats_id ?? n.reply.stats_id,
               to_emails: $json.__forward_to };
// B25: this used to spread $json and NOT set __skip, so it INHERITED the flag from
// Body SL Category upstream (__skip: !__classify_ok). Every Uncategorized reply therefore
// skipped its forward - meaning the human-review routing to forward_review_address was dead in
// exactly the case it exists for. Proven live 2026-07-30 on a 0.62-confidence reply.
// Every Body node now decides its own __skip; inheriting one is how a write disappears silently.
return [{ json: { ...$json, __body: body,
  __skip: !body.to_emails || (!body.message_id && !body.stats_id),
  __intended: { node: 'SL Forward Email', method: 'POST', url: '/campaigns/{cid}/forward-email', body } } }];
"""

BODY_SL_CATEGORY = CANON_HELPERS + r"""
const body = { category_id: $json.__category_id };
if ($json.__is_dnc === true) body.pause_lead = true;               // pause only for DNC
return [{ json: { ...$json, __body: body, __skip: !$json.__classify_ok || $json.__category_id === null,
  __intended: { node: 'SL Category', method: 'POST', url: '/campaigns/{cid}/leads/{lid}/category', body } } }];
"""

BODY_SL_UNSUB = CANON_HELPERS + r"""
const body = {};                                                   // global suppression, prevents re-adding
// B25: explicit, not inherited - the branch decides whether we get here, WRITE_MODE decides the write
return [{ json: { ...$json, __body: body, __skip: false,
  __intended: { node: 'SL Unsubscribe', method: 'POST', url: '/leads/{lid}/unsubscribe', body } } }];
"""

BODY_LABELS = CANON_HELPERS + r"""
// B12: $json does NOT survive an HTTP node - after a write, $json is the API response and every
// __ field is gone. Live proof: Body Lead Labels Union is fed from SL Forward Email, so `existing`
// came back [] and the UNION silently degenerated into Make's absolute set. Recover context from
// the node that OWNS it, by name, and treat $json as an override only.
const fromNode = (nm) => { try { return $(nm).item.json || {}; } catch (e) { return {}; } };
const ctx = (key, ...names) => {
  if ($json && $json[key] !== undefined && $json[key] !== null) return $json[key];
  for (const nm of names) { const v = fromNode(nm)[key]; if (v !== undefined && v !== null) return v; }
  return undefined;
};

// email label model preserved literally: cold + connected + responded, but as a UNION
const target = [CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];
if (ctx('__dnc_label', 'Mark DNC', 'U Mark DNC') === true) target.push(CFG.labels.dnc);
const _lbl = ctx('__lead_labels', 'Mark DNC', 'Merge Reply Ctx', 'Lead Resolve', 'U Mark DNC', 'U Lead Select');
const existing = Array.isArray(_lbl) ? _lbl.slice() : [];
const union = existing.slice();
for (const id of target) if (id && !union.includes(id)) union.push(id);
const changed = union.length !== existing.length;
const body = { label_ids: union };
const _leadId = ctx('__lead_id', 'Mark DNC', 'Merge Reply Ctx', 'Lead Resolve', 'U Mark DNC', 'U Lead Select') ?? null;
return [{ json: { ...$json, __lead_id: _leadId, __body: body,
  // B13: no lead -> no PATCH. Previously this produced PATCH /v1/leads/undefined -> 400 -> the
  // whole execution errored, which also killed the ops warn that should have reported it.
  __skip: !changed || !_leadId, __label_union: union,
  __intended: { node: 'Lead Labels Union (shared body: also U Lead DNC Label)',
               method: 'PATCH', url: '/v1/leads/' + (_leadId ?? '{none}'), body } } }];
"""

BODY_REPLY_ACTIVITY = CANON_HELPERS + r"""
// B12: $json does NOT survive an HTTP node - after a write, $json is the API response and every
// __ field is gone. Live proof: Body Lead Labels Union is fed from SL Forward Email, so `existing`
// came back [] and the UNION silently degenerated into Make's absolute set. Recover context from
// the node that OWNS it, by name, and treat $json as an override only.
const fromNode = (nm) => { try { return $(nm).item.json || {}; } catch (e) { return {}; } };
const ctx = (key, ...names) => {
  if ($json && $json[key] !== undefined && $json[key] !== null) return $json[key];
  for (const nm of names) { const v = fromNode(nm)[key]; if (v !== undefined && v !== null) return v; }
  return undefined;
};

// first time email reply text lands in the CRM at all
const subj = n.reply.subject ? String(n.reply.subject) : 'Email reply';
const noteParts = [];
if (n.reply.subject) noteParts.push('Subject: ' + n.reply.subject);
if (n.reply.body) noteParts.push(String(n.reply.body).slice(0, 8000));
if (ctx('__summary', 'Classify Parse')) noteParts.push('— ' + ctx('__summary', 'Classify Parse'));
const note = noteParts.join('\n\n');
const body = { subject: 'Email reply — ' + n.campaign_name, type: 'email', done: true,
               owner_id: CFG.owner_id, lead_id: ctx('__lead_id', 'Merge Reply Ctx', 'Lead Resolve') };
if (note) body.note = note;                                        // empty-omit (W1.0.6)
if (n.reply.received_at) body.due_date = String(n.reply.received_at).slice(0, 10);
omit(body);
return [{ json: { ...$json, __body: body, __skip: !ctx('__lead_id', 'Merge Reply Ctx', 'Lead Resolve'),
  __intended: { node: 'Reply Activity', method: 'POST', url: '/api/v2/activities', body } } }];
"""

BODY_BOUNCE_NOTE = CANON_HELPERS + r"""
const body = { subject: 'Email bounced — ' + n.campaign_name, type: 'email', done: true,
               owner_id: CFG.owner_id, lead_id: $json.__lead_id,
               note: 'Smartlead reported a bounce for ' + (n.lead.email || '') + ' on ' + (n.timestamp || '') };
omit(body);
return [{ json: { ...$json, __body: body, __skip: !$json.__lead_id,
  __intended: { node: 'Bounce Note', method: 'POST', url: '/api/v2/activities', body } } }];
"""

OPS_WARN_TEXT_UNKNOWN_EVENT = (
    "={{ '\\u26a0\\ufe0f WF-2: unknown Smartlead event \\\"' + ($('Normalize').item.json.raw_event || '?') "
    "+ '\\\" \\u2014 ignored (campaign: ' + ($('Normalize').item.json.campaign_name || '?') + ')' }}"
)
OPS_WARN_TEXT_MARKER = (
    "={{ '\\u26a0\\ufe0f WF-2: unknown campaign marker \\\"' + ($('Normalize').item.json.marker_unknown || '?') "
    "+ '\\\" \\u2014 hypothesis skipped (' + ($('Normalize').item.json.campaign_name || '?') + ')' }}"
)
OPS_WARN_TEXT_NOLEAD = (
    "={{ '\\u26a0\\ufe0f WF-2: reply with no matching lead \\u2014 ' + ($('Normalize').item.json.lead.email || '?') "
    "+ ' (' + ($('Normalize').item.json.campaign_name || '?') + '); person-side writes only' }}"
)
OPS_WARN_TEXT_CLASSIFY = (
    # review-routed replies: whoever reads this needs the text AND a way into the conversation,
    # otherwise the warn is just noise telling them something they cannot act on
    "={{ (() => { const n=$('Normalize').item.json; const CFG=$('CONFIG').item.json;"
    " const esc=(v)=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');"
    r" const plain=(v)=>{let t=String(v??'');"
    r" t=t.replace(/<blockquote[\s\S]*$/i,'');"
    r" t=t.replace(/<br\s*\/?>/gi,' ').replace(/<\/(div|p|li|tr)>/gi,' ');"
    r" t=t.replace(/<[^>]*>/g,'');"
    r" t=t.replace(/&nbsp;/gi,' ');"
    r" t=t.replace(/&quot;/gi,String.fromCharCode(34));"
    r" t=t.replace(/&#39;/gi,String.fromCharCode(39));"
    r" t=t.replace(/&lt;/gi,'<').replace(/&gt;/gi,'>').replace(/&amp;/gi,'&');"
    r" t=t.replace(/\s+/g,' ').trim();"
    r" return esc(t).slice(0,300);};"
    " const cp=(()=>{try{return $('Classify Parse').item.json||{}}catch(e){return{}}})();"
    " const sl=(n.sl_app_url || (n.sl_lead_map_id ? (CFG.sl_inbox_base + n.sl_lead_map_id) : null));"
    " const link=sl?(' \\u00b7 <'+sl+'|Open in Smartlead>'):'';"
    " const conf=(cp.__confidence!==undefined&&cp.__confidence!==null)?cp.__confidence:'?';"
    " return '\\u26a0\\ufe0f WF-2: classifier fallback \\u2014 routed to review ('"
    " + esc(CFG.forward_review_address) + ') for ' + esc(n.lead.email || '?')"
    " + ' \\u00b7 confidence ' + conf + link"
    " + '\\n> ' + plain(n.reply.body); })() }}"
)
OPS_WARN_TEXT_INBOX = (
    "={{ '\\u26a0\\ufe0f WF-2: unknown sender inbox ' + ($('Normalize').item.json.sender_inbox || '?') "
    "+ ' \\u2014 forwarded to default (' + $('CONFIG').item.json.forward_default + '); add it to the map' }}"
)
