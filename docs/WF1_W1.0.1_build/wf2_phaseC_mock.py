"""Phase C harness: an in-n8n mock of the Smartlead + Anthropic endpoints.

Why a mock at all: Phase C runs the double with WRITE_MODE=live, and the Smartlead write
endpoints (category writeback, GLOBAL unsubscribe, forward-email) act on REAL prospects in
Melisa's production account. An unsubscribe is not meaningfully reversible, so those calls are
served from inside n8n instead. Pipedrive and Slack stay REAL - that is the part of the matrix
worth running live, and its synthetic entities are cleanable.

Every mock response body is a shape RECORDED from the live API on 2026-07-28
(see wf1-release-evidence/wf2-api-shapes.md), not an invented one.

The LLM mock derives its category from a CATEG=<name> token planted in the reply body, so each
E-case controls classification deterministically without spending Anthropic tokens.

n8n Cloud 404s on ':param' webhook segments (probed), so the mock serves STATIC paths and the
double's SL URLs carry campaign_id / sl_lead_id in the QUERY string instead. That keeps the id
interpolation under test - the mock echoes __query back - while avoiding route params entirely.
"""
import argparse
import json
import sys
from pathlib import Path

MOCK_NAME = "WF-2 PHASE-C MOCK - Smartlead + Anthropic (DELETE AFTER)"
MOCK_PREFIX = "slmock-c1"          # webhook path prefix, unique to this run
LLM_PATH = "llmmock-c1"


def _wh(nid, name, path, method, pos):
    return {"parameters": {"httpMethod": method, "path": path, "responseMode": "lastNode",
                           "options": {}},
            "id": nid, "name": name, "type": "n8n-nodes-base.webhook", "typeVersion": 2,
            "position": pos, "webhookId": nid}


def _code(nid, name, js, pos):
    return {"parameters": {"jsCode": js}, "id": nid, "name": name,
            "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}


# --- recorded live shapes -------------------------------------------------------------------
LEAD_BY_EMAIL = r"""
// GET /leads?email=  -> FLAT lead object (recorded: pii-9569b1b9@example.invalid)
const q = $json.query || {};
const email = String(q.email || '');
return [{ json: {
  id: '4086543431', first_name: 'Mock', last_name: 'Enriched ', email,
  phone_number: null, company_name: 'MockEnrich Ltd', website: null,
  location: 'London, England, United Kingdom',
  custom_fields: { city: 'London', job_title: 'Head of Mock Data' },
  linkedin_profile: 'https://www.linkedin.com/in/pii-1f2cea07',
  company_url: 'https://mockenrich.example', is_unsubscribed: false,
  unsubscribed_client_id_map: {}, lead_campaign_data: [],
  __mock: 'leads_by_email',
} }];
"""

MESSAGE_HISTORY = r"""
// GET /campaigns/{cid}/leads/{lid}/message-history -> { history:[...], from, to }
// Recorded live: the sequence is [SENT, REPLY] and stats_id is shared across the thread.
// A trailing SENT is included on purpose: it proves Pick Last Message anchors on the REPLY.
const p = $json.params || {};
return [{ json: {
  history: [
    { stats_id: 'mock-stats-1', from: 'pii-e1200ff3@example.invalid', to: 'prospect@example.com',
      type: 'SENT',  message_id: '<pii-5cd00089@example.invalid>',
      time: '2026-07-28T09:00:00.000Z', email_body: '<div>Mock outbound</div>' },
    { stats_id: 'mock-stats-1', from: 'prospect@example.com', to: 'pii-e1200ff3@example.invalid',
      type: 'REPLY', message_id: '<mock-reply-1@example.com>',
      time: '2026-07-28T09:05:00.000Z', email_body: '<div>Mock reply body</div>' },
    { stats_id: 'mock-stats-1', from: 'pii-e1200ff3@example.invalid', to: 'prospect@example.com',
      type: 'SENT',  message_id: '<pii-58f3f228@example.invalid>',
      time: '2026-07-28T09:10:00.000Z', email_body: '<div>Mock follow-up</div>' },
  ],
  from: 'pii-e1200ff3@example.invalid', to: 'prospect@example.com',
  __mock: 'message_history', __params: p,
} }];
"""

ACK = r"""
// Smartlead write endpoints answer a small ack. We echo the received body so the E-matrix can
// assert on exactly what WF-2 sent (read back from this workflow's execution data).
return [{ json: { ok: true, __mock: '%s', __received: $json.body ?? null,
                  __params: $json.params ?? null, __query: $json.query ?? null } }];
"""

LLM = r"""
// POST /v1/messages -> Anthropic Messages shape. The category comes from a CATEG=<name> token
// planted in the prompt by the E-case, so classification is deterministic and costs nothing.
const body = $json.body || {};
const prompt = JSON.stringify(body);
const m = prompt.match(/CATEG=([^;"'\\]{1,40});/);   // token contract: CATEG=<name>;
const category = m ? m[1].trim() : 'Interested';
const conf = /LOWCONF/.test(prompt) ? 0.2 : 0.95;
const payload = /BADJSON/.test(prompt)
  ? 'not json at all'
  : JSON.stringify({ category, confidence: conf,
                     is_dnc: category === 'Do Not Contact',
                     reason: 'phase-C mock' });
return [{ json: { id: 'msg_mock', type: 'message', role: 'assistant', model: 'mock',
                  content: [{ type: 'text', text: payload }],
                  stop_reason: 'end_turn', usage: { input_tokens: 0, output_tokens: 0 },
                  __mock: 'llm' } }];
"""


CRYPTO_PROBE = r"""
// Phase C probe: is node's crypto available inside a Code node on THIS n8n instance?
// It decides whether the webhook secret can be stored as a HASH in CONFIG (safe to commit)
// or would have to sit in the workflow JSON as plaintext (which AU4/validate forbid).
let ok = false, err = null, sample = null;
try { const c = require('crypto');
      sample = c.createHash('sha256').update('probe').digest('hex');
      ok = typeof c.createHash === 'function' && !!c.timingSafeEqual;
} catch (e) { err = String(e && e.message || e); }
return [{ json: { crypto_available: ok, digest_of_probe: sample, error: err } }];
"""

ROUTES = [
    # (node id, display name, path, method, response js)
    ("mk1", "WH leads by email", f"{MOCK_PREFIX}/leads", "GET", LEAD_BY_EMAIL),
    ("mk2", "WH message history", f"{MOCK_PREFIX}/message-history", "GET", MESSAGE_HISTORY),
    ("mk3", "WH category", f"{MOCK_PREFIX}/category", "POST", ACK % "category"),
    ("mk4", "WH unsubscribe", f"{MOCK_PREFIX}/unsubscribe", "POST", ACK % "unsubscribe"),
    ("mk5", "WH forward email", f"{MOCK_PREFIX}/forward-email", "POST", ACK % "forward"),
    ("mk6", "WH llm", LLM_PATH, "POST", LLM),
    ("mk7", "WH crypto probe", f"{MOCK_PREFIX}/cryptoprobe", "GET", CRYPTO_PROBE),
]


def build_mock():
    nodes, conns = [], {}
    for i, (nid, name, path, method, js) in enumerate(ROUTES):
        y = i * 200
        nodes.append(_wh(nid, name, path, method, [0, y]))
        rname = f"R {name}"
        nodes.append(_code(f"{nid}r", rname, js, [260, y]))
        conns[name] = {"main": [[{"node": rname, "type": "main", "index": 0}]]}
    return {"name": MOCK_NAME, "nodes": nodes, "connections": conns,
            "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all",
                         "saveDataErrorExecution": "all", "saveExecutionProgress": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    a = ap.parse_args()
    wf = build_mock()
    a.output.write_bytes((json.dumps(wf, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"mock built -> {a.output} ({len(wf['nodes'])} nodes, {len(ROUTES)} routes)")
    for _, name, path, method, _js in ROUTES:
        print(f"  {method:5s} /webhook/{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
