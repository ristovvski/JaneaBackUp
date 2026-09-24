#!/usr/bin/env python3
"""AS-IS infrastructure discovery — STRICTLY READ-ONLY (GET/list only). Zero writes, zero
object-creating probes. AI4 is live. Auth from env (dot-source wf1_env.ps1 + disc_env.ps1 first).
Secrets are never printed or saved; request URLs carrying tokens are not persisted."""
import os, json, time, sys
try:
    import requests
except Exception:
    print("requests not available"); sys.exit(2)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discovery_raw.json")
CA = os.environ.get("REQUESTS_CA_BUNDLE")  # requests honors this automatically
S = requests.Session()
result = {"_meta": {"mode": "READ-ONLY GET/list", "generated_utc": None}}


def get(url, headers=None, params=None, tag=""):
    """Safe GET. Returns {ok,status,data|error}. Never stores url/params (may hold secrets)."""
    try:
        r = S.get(url, headers=headers or {}, params=params or {}, timeout=45)
        body = None
        try:
            body = r.json()
        except Exception:
            body = {"_non_json_len": len(r.text or "")}
        return {"ok": r.ok, "status": r.status_code, "data": body if r.ok else None,
                "error": None if r.ok else str(body)[:400]}
    except Exception as e:
        return {"ok": False, "status": None, "data": None, "error": str(e)[:300]}


def listify(d):
    if isinstance(d, dict):
        for k in ("data", "campaigns", "result", "items"):
            if isinstance(d.get(k), list):
                return d[k]
        if isinstance(d.get("data"), dict):
            return [d["data"]]
    return d if isinstance(d, list) else []


# ============================ SMARTLEAD ============================
SL_KEY = os.environ.get("SMARTLEAD_API_KEY")
SL_BASE = "https://server.smartlead.ai/api/v1"
sl = {"base": SL_BASE, "auth": "api_key query param", "have_key": bool(SL_KEY)}
if SL_KEY:
    p = {"api_key": SL_KEY}
    camps = get(SL_BASE + "/campaigns", params=p, tag="sl_campaigns")
    sl["campaigns_call"] = {k: camps[k] for k in ("ok", "status", "error")}
    clist = listify(camps["data"]) if camps["ok"] else []
    sl["campaigns"] = [{"id": c.get("id"), "name": c.get("name"), "status": c.get("status"),
                        "created_at": c.get("created_at")} for c in clist]
    # per-campaign webhooks + email-account assignment
    wh, assign = [], []
    for c in clist:
        cid = c.get("id")
        if cid is None:
            continue
        w = get(SL_BASE + "/campaigns/%s/webhooks" % cid, params=p)
        for x in (listify(w["data"]) if w["ok"] else []):
            wh.append({"campaign_id": cid, "campaign": c.get("name"),
                       "webhook_id": x.get("id"), "name": x.get("name"),
                       "url": x.get("webhook_url") or x.get("url"),
                       "events": x.get("event_types") or x.get("events"),
                       "is_active": x.get("is_active")})
        ea = get(SL_BASE + "/campaigns/%s/email-accounts" % cid, params=p)
        ea_list = listify(ea["data"]) if ea["ok"] else []
        assign.append({"campaign_id": cid, "campaign": c.get("name"), "email_account_count": len(ea_list)})
        time.sleep(0.15)
    sl["webhooks"] = wh
    sl["email_account_assignment"] = assign
    allea = get(SL_BASE + "/email-accounts", params={"api_key": SL_KEY, "offset": 0, "limit": 1000})
    ealist = listify(allea["data"]) if allea["ok"] else []
    sl["email_accounts_total"] = {"call": {k: allea[k] for k in ("ok", "status", "error")}, "count": len(ealist)}
    cats = get(SL_BASE + "/leads/fetch-categories", params=p)
    sl["categories_call"] = {k: cats[k] for k in ("ok", "status", "error")}
    sl["categories"] = listify(cats["data"]) if cats["ok"] else []
result["smartlead"] = sl

# ============================ PIPEDRIVE ============================
PD_TOKEN = os.environ.get("PIPEDRIVE_API_TOKEN")
PD_BASE = "https://janeasystems.pipedrive.com/api/v1"
pd = {"base": PD_BASE, "auth": "api_token query param", "have_token": bool(PD_TOKEN)}
if PD_TOKEN:
    pp = {"api_token": PD_TOKEN}
    field_eps = {"person": "/personFields", "organization": "/organizationFields",
                 "deal": "/dealFields", "lead": "/leadFields", "product": "/productFields"}
    pd["fields"] = {}
    for ent, ep in field_eps.items():
        r = get(PD_BASE + ep, params={"api_token": PD_TOKEN, "start": 0, "limit": 500})
        flds = listify(r["data"]) if r["ok"] else []
        pd["fields"][ent] = {"call": {k: r[k] for k in ("ok", "status", "error")},
                             "list": [{"key": f.get("key"), "name": f.get("name"),
                                       "field_type": f.get("field_type"),
                                       "edit_flag": f.get("edit_flag"),
                                       "add_visible_flag": f.get("add_visible_flag")}
                                      for f in flds]}

    # usage sampling: % non-empty per field over recent records
    def sample(ep, ent, limit):
        recs = []
        start = 0
        while len(recs) < limit:
            r = get(PD_BASE + ep, params={"api_token": PD_TOKEN, "start": start,
                                          "limit": min(500, limit - len(recs)),
                                          "sort": "add_time DESC"})
            if not r["ok"]:
                return {"call": {k: r[k] for k in ("ok", "status", "error")}, "sampled": 0, "usage": {}}
            batch = listify(r["data"])
            if not batch:
                break
            recs.extend(batch)
            more = False
            if isinstance(r["data"], dict):
                ad = (r["data"].get("additional_data") or {}).get("pagination") or {}
                more = ad.get("more_items_in_collection")
                start = ad.get("next_start") or (start + len(batch))
            if not more:
                break
            time.sleep(0.15)
        keys = [f["key"] for f in pd["fields"].get(ent, {}).get("list", [])]
        usage = {}
        n = len(recs) or 1
        for k in keys:
            nonempty = 0
            for rec in recs:
                v = rec.get(k)
                if v not in (None, "", [], {}):
                    nonempty += 1
            usage[k] = round(100.0 * nonempty / n, 1)
        return {"call": {"ok": True}, "sampled": len(recs), "usage": usage}

    pd["sampling"] = {
        "person": sample("/persons", "person", 500),
        "organization": sample("/organizations", "organization", 300),
        "deal": sample("/deals", "deal", 500),
        "lead": sample("/leads", "lead", 500),
    }
    wh = get(PD_BASE + "/webhooks", params=pp)
    whl = listify(wh["data"]) if wh["ok"] else []
    pd["webhooks"] = {"call": {k: wh[k] for k in ("ok", "status", "error")},
                      "list": [{"id": w.get("id"), "url": w.get("subscription_url"),
                                "event_action": w.get("event_action"), "event_object": w.get("event_object"),
                                "user_id": w.get("user_id"), "is_active": w.get("is_active", w.get("active_flag"))}
                               for w in whl]}
    us = get(PD_BASE + "/users", params=pp)
    usl = listify(us["data"]) if us["ok"] else []
    pd["users"] = {"count": len(usl), "list": [{"id": u.get("id"), "name": u.get("name"),
                    "email": u.get("email"), "active": u.get("active_flag")} for u in usl]}
    ll = get(PD_BASE + "/leadLabels", params=pp)
    pd["lead_labels"] = [{"id": x.get("id"), "name": x.get("name"), "color": x.get("color")}
                         for x in (listify(ll["data"]) if ll["ok"] else [])]
    fl = get(PD_BASE + "/filters", params=pp)
    pd["filters"] = [{"id": x.get("id"), "name": x.get("name"), "type": x.get("type")}
                     for x in (listify(fl["data"]) if fl["ok"] else [])]
    pd["automations"] = {"api_exposed": False, "note": "Pipedrive Automations are not API-exposed — GAP, not guessed."}
result["pipedrive"] = pd

# ============================ N8N ============================
N8N_BASE = (os.environ.get("N8N_BASE_URL") or "").rstrip("/")
N8N_KEY = os.environ.get("N8N_API_KEY")
if N8N_BASE and "/api/" not in N8N_BASE:
    N8N_API = N8N_BASE + "/api/v1"
else:
    N8N_API = N8N_BASE
n8 = {"base_present": bool(N8N_BASE), "api": N8N_API if N8N_KEY else None}
if N8N_BASE and N8N_KEY:
    h = {"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"}
    wfs, cursor, pages = [], None, 0
    while pages < 20:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = get(N8N_API + "/workflows", headers=h, params=params)
        if not r["ok"]:
            n8["workflows_call"] = {k: r[k] for k in ("ok", "status", "error")}
            break
        data = r["data"] or {}
        wfs.extend(data.get("data", []) if isinstance(data, dict) else [])
        cursor = data.get("nextCursor") if isinstance(data, dict) else None
        pages += 1
        if not cursor:
            n8["workflows_call"] = {"ok": True, "status": 200}
            break
    trig_types = ("Trigger", "trigger", "webhook", "cron", "schedule", "executeWorkflowTrigger")
    summ = []
    for w in wfs:
        nodes = w.get("nodes", []) or []
        triggers = [n.get("type") for n in nodes
                    if any(t.lower() in (n.get("type", "").lower()) for t in trig_types)]
        webhook_paths = [((n.get("parameters") or {}).get("path")) for n in nodes
                         if "webhook" in (n.get("type", "").lower())]
        summ.append({"id": w.get("id"), "name": w.get("name"), "active": w.get("active"),
                     "node_count": len(nodes), "trigger_types": triggers,
                     "webhook_paths": [p for p in webhook_paths if p]})
    n8["workflows"] = summ
    dt = get(N8N_API + "/datatables", headers=h)
    n8["datatables"] = {"call": {k: dt[k] for k in ("ok", "status", "error")},
                        "list": listify(dt["data"]) if dt["ok"] else []}
result["n8n"] = n8

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False, default=str)

# ---- compact summary to stdout (no secrets) ----
def okc(x):
    return x.get("ok") if isinstance(x, dict) else x
print("=== SMARTLEAD ===  have_key:", sl.get("have_key"))
print("  campaigns:", len(sl.get("campaigns", [])), "| webhooks:", len(sl.get("webhooks", [])),
      "| email_accounts:", sl.get("email_accounts_total", {}).get("count"),
      "| categories:", len(sl.get("categories", [])))
print("  campaigns_call:", sl.get("campaigns_call"))
print("  categories_call:", sl.get("categories_call"))
print("=== PIPEDRIVE ===  have_token:", pd.get("have_token"))
for ent in ("person", "organization", "deal", "lead", "product"):
    fc = pd.get("fields", {}).get(ent, {})
    print("  %-13s fields:" % ent, len(fc.get("list", [])), "call:", fc.get("call"))
print("  webhooks:", len(pd.get("webhooks", {}).get("list", [])), pd.get("webhooks", {}).get("call"))
print("  users:", pd.get("users", {}).get("count"), "| lead_labels:", len(pd.get("lead_labels", [])),
      "| filters:", len(pd.get("filters", [])))
for ent, s in pd.get("sampling", {}).items():
    print("  sample %-12s:" % ent, s.get("sampled"), "records")
print("=== N8N ===  api:", bool(n8.get("api")))
print("  workflows:", len(n8.get("workflows", [])), n8.get("workflows_call"))
print("  datatables:", n8.get("datatables", {}).get("call"), "count:", len(n8.get("datatables", {}).get("list", [])))
print("\nRAW ->", OUT)
