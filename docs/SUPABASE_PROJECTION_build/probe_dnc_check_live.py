#!/usr/bin/env python3
"""Read-only PostgREST probe for DNC_CHECK.sql against the LIVE Supabase project, through n8n's own
Supabase credential (we hold no Supabase key locally). Same throwaway pattern as
probe_supabase_connectivity.py: deploy a tiny webhook workflow, fire it, deactivate + delete it.

WHAT IT PROVES
  1. every column DNC_CHECK.sql reads exists in the live tables (select=<cols>&limit=0: PostgREST
     rejects an unknown column with 400, and limit=0 returns NO ROW DATA) + live row counts
  2. how many ACTIVE people are keyed by email and have no LinkedIn - the population the old
     single-key Clay lookup can miss (a count, no rows)
  3. whether rpc/dnc_check is deployed (404 PGRST202 = not yet)
  4. if deployed: normalization parity with normalize_v1.js, a stranger is not blocked, and THE
     CORRECTION on real rows - up to 20 active email-keyed people, each checked WITH an unrelated
     LinkedIn URL, must all still be blocked. Their emails stay inside this process; only counts
     are printed.

The workflow accepts only the fixed operations below - it is not a generic proxy for the key it
holds. The credential is the n8n one (service role), so this does NOT prove the anon grants; Stefan's
test_dnc_check_postgrest.mjs, run with the publishable key, does.
"""
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

SUPABASE_URL = "https://icxrjwccqitqmpypwhie.supabase.co"
CRED = {"supabaseApi": {"id": "u6wyGnYC71Sr1KgT", "name": "Supabase account"}}
HOOK = "probe-dnc-check-" + uuid.uuid4().hex[:12]
REG_COLS = ("identity_key,norm_v,linkedin_url_norm,email_lc,status,reason,entry_type,reply_category,"
            "added_at,expires_at,removed_at")
DOM_COLS = "domain,status,reason,added_at"

ROUTER = r"""
const q = $json.query || {};
const R = '%s/rest/v1/';
const ops = {
  cols_registry:  {m: 'GET', u: R + 'dnc_registry?select=%s&limit=0'},
  cols_domains:   {m: 'GET', u: R + 'dnc_domains?select=%s&limit=0'},
  cols_bogus:     {m: 'GET', u: R + 'dnc_registry?select=identity_key,zz_no_such_column&limit=0'},
  count_active:   {m: 'GET', u: R + 'dnc_registry?select=identity_key&status=eq.active&limit=0'},
  count_emailkey: {m: 'GET', u: R + 'dnc_registry?select=identity_key&status=eq.active&linkedin_url_norm=is.null&email_lc=not.is.null&limit=0'},
  sample_emailkey:{m: 'GET', u: R + 'dnc_registry?select=email_lc&status=eq.active&linkedin_url_norm=is.null&email_lc=not.is.null&order=added_at.desc&limit=20'},
  rpc:            {m: 'POST', u: R + 'rpc/dnc_check'},
};
const op = ops[q.op];
if (!op) throw new Error('unknown op');
let body = '{}';
if (op.m === 'POST') {
  const b = JSON.parse(q.b || '{}');
  body = JSON.stringify({p_linkedin_url: b.p_linkedin_url ?? null, p_email: b.p_email ?? null});
}
return [{json: {method: op.m, url: op.u, body}}];
""" % (SUPABASE_URL, REG_COLS, DOM_COLS)


def http_node(name, method, x):
    p = {"method": method, "url": "={{ $json.url }}",
         "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
         "sendHeaders": True,
         "headerParameters": {"parameters": [{"name": "Prefer", "value": "count=exact"}]},
         # the REAL path - options.fullResponse is silently ignored (memory: n8n-http-fullresponse)
         "options": {"response": {"response": {"fullResponse": True, "neverError": True}}}}
    if method == "POST":
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json.body }}"})
    return {"parameters": p, "id": name.lower(), "name": name, "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2, "position": [x, 300], "credentials": CRED}


def build():
    nodes = [
        {"parameters": {"httpMethod": "GET", "path": HOOK, "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [-600, 300], "webhookId": str(uuid.uuid4())},
        {"parameters": {"jsCode": ROUTER}, "id": "router", "name": "Router",
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-400, 300]},
        {"parameters": {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict"},
                                       "conditions": [{"leftValue": "={{ $json.method }}",
                                                       "rightValue": "POST",
                                                       "operator": {"type": "string", "operation": "equals"}}],
                                       "combinator": "and"}, "options": {}},
         "id": "ispost", "name": "Is POST", "type": "n8n-nodes-base.if", "typeVersion": 2,
         "position": [-200, 300]},
        http_node("POST", "POST", 0),
        http_node("GET", "GET", 0),
        {"parameters": {"respondWith": "json", "responseBody":
                        "={{ JSON.stringify({status: $json.statusCode, range: ($json.headers || {})['content-range'] || null, body: $json.body}) }}",
                        "options": {}},
         "id": "respond", "name": "Respond", "type": "n8n-nodes-base.respondToWebhook",
         "typeVersion": 1.1, "position": [200, 300]},
    ]
    conn = {"Webhook": {"main": [[{"node": "Router", "type": "main", "index": 0}]]},
            "Router": {"main": [[{"node": "Is POST", "type": "main", "index": 0}]]},
            "Is POST": {"main": [[{"node": "POST", "type": "main", "index": 0}],
                                 [{"node": "GET", "type": "main", "index": 0}]]},
            "POST": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
            "GET": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]}}
    return {"name": "ZZ_PROBE_dnc_check_live_DELETE_ME", "nodes": nodes, "connections": conn,
            "settings": {"executionOrder": "v1"}}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
        raw = x.read()
        return json.loads(raw) if raw else {}


def fire(op, b=None):
    q = {"op": op}
    if b is not None:
        q["b"] = json.dumps(b, ensure_ascii=False)
    url = BASE.replace("/api/v1", "") + "/webhook/" + HOOK + "?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=60, context=ctx) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"status": "webhook-%d" % e.code, "range": None, "body": e.read().decode()[:300]}


def js_expect(cases):
    norm = os.path.join(ROOT, "DNC_OBS_P1_build", "subworkflows", "lib", "normalize_v1.js")
    src = ("const {normalizeIdentityV1:n}=require(%s);const c=%s;"
           "console.log(JSON.stringify(c.map(([l,e])=>{const r=n({linkedin_url:l,email:e});"
           "return r?r.identity_key??null:null;})));") % (json.dumps(norm), json.dumps(cases))
    p = subprocess.run(["node", "-e", src], capture_output=True, text=True, encoding="utf-8")
    return json.loads(p.stdout)


CASES = [["HTTPS://WWW.LinkedIn.com/in/Jane-Doe/?utm_source=x&utm_medium=y", None],
         ["https://www.linkedin.com/in/Andr%C3%A9-Martin/", None],
         [None, "  John.SMITH+sales@Example.COM  "],
         ["https://www.linkedin.com/company/acme-corp", "Jane@Acme.com"],
         [None, None], ["https://www.linkedin.com/in/%E0%A4%A", "x@y.co"],
         ["https://www.linkedin.com/in/%41bc", None],
         [" https://linkedin.com/in/jo-roe// ", None],
         ["https://www.linkedin.com/in/ÉLODIE-ROE", None],
         ["https://www.linkedin.com/in/", "a@b.io"], [None, "@acme.com"], [None, "jo@acmecom"]]


def main():
    res = {"pass": 0, "fail": 0}

    def ok(label, cond, detail=""):
        res["pass" if cond else "fail"] += 1
        print("  [%s] %s%s" % ("ok " if cond else "FAIL", label, "" if cond or not detail else "\n         " + detail))

    wf = build()
    wid = n8n("/api/v1/workflows", "POST", wf)["id"]
    n8n("/api/v1/workflows/%s/activate" % wid, "POST", {})
    print("probe workflow %s active (webhook %s…)" % (wid, HOOK[:16]))
    time.sleep(1.5)
    try:
        print("1. live schema")
        for op in ("cols_registry", "cols_domains"):
            r = fire(op)
            # 206 Partial Content is PostgREST's normal answer to a counted limit=0 read
            ok("%s: every column DNC_CHECK.sql reads exists" % op, r["status"] in (200, 206),
               "HTTP %s %s" % (r["status"], json.dumps(r["body"])[:300]))
            print("       rows: %s" % (r["range"] or "?").split("/")[-1])
        b = fire("cols_bogus")
        ok("non-vacuous: an unknown column is rejected (HTTP %s)" % b["status"], b["status"] == 400)
        print("2. the population the old lookup can miss")
        a, e = fire("count_active"), fire("count_emailkey")
        print("       active people: %s   of them keyed by email with no LinkedIn: %s"
              % ((a["range"] or "?/?").split("/")[-1], (e["range"] or "?/?").split("/")[-1]))
        print("3. is rpc/dnc_check deployed?")
        r = fire("rpc", {"p_linkedin_url": None, "p_email": None})
        if r["status"] != 200:
            code = r["body"].get("code") if isinstance(r["body"], dict) else None
            print("       NOT DEPLOYED - HTTP %s %s (expected until DNC_CHECK.sql is pasted into the SQL editor)"
                  % (r["status"], code or json.dumps(r["body"])[:200]))
            return res, False
        print("       deployed")
        print("4. deployed function")
        exp = js_expect(CASES)
        for (li, em), want in zip(CASES, exp):
            got = ((fire("rpc", {"p_linkedin_url": li, "p_email": em})["body"] or {})
                   .get("identity") or {}).get("identity_key")
            ok("parity %r / %r -> %r" % (li, em, want), got == want, "live produced %r" % (got,))
        nonce = "zz-dnc-selftest-" + uuid.uuid4().hex[:8]
        s = fire("rpc", {"p_linkedin_url": "https://www.linkedin.com/in/" + nonce,
                         "p_email": nonce + "@" + nonce + ".invalid"})["body"]
        ok("stranger is not blocked", s.get("blocked") is False and s.get("persons") == [], json.dumps(s)[:200])
        emails = [row["email_lc"] for row in (fire("sample_emailkey")["body"] or [])]
        blocked_plain = blocked_fix = 0
        for em in emails:
            blocked_plain += bool(fire("rpc", {"p_email": em})["body"].get("blocked"))
            blocked_fix += bool(fire("rpc", {"p_linkedin_url": "https://www.linkedin.com/in/" + nonce,
                                             "p_email": em})["body"].get("blocked"))
        ok("non-vacuous sample: %d active email-keyed rows read" % len(emails), len(emails) > 0)
        ok("email alone blocks %d/%d" % (blocked_plain, len(emails)), blocked_plain == len(emails))
        ok("THE CORRECTION - email + unrelated LinkedIn still blocks %d/%d" % (blocked_fix, len(emails)),
           blocked_fix == len(emails))
        return res, True
    finally:
        n8n("/api/v1/workflows/%s/deactivate" % wid, "POST", {})
        n8n("/api/v1/workflows/%s" % wid, "DELETE")
        print("probe workflow %s deactivated + deleted (throwaway, no incident value)" % wid)


if __name__ == "__main__":
    r, deployed = main()
    print("\n%d passed, %d failed%s" % (r["pass"], r["fail"], "" if deployed else "  - function not deployed"))
    raise SystemExit(1 if r["fail"] else (3 if not deployed else 0))
