#!/usr/bin/env python3
"""FLIP DAY - P0b + F1/F2/F3 pre-flight. READ-ONLY except one harmless webhook probe.

Reuses the checks flip_preflight.py already had (its A-G naming) but reports them under the F1-F3
names from Friday's plan, which supersede. Every gate prints GREEN/RED with the evidence it used.
"""
import json, os, ssl, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
MTOK = os.environ["MAKE_API_TOKEN"]
ZONE = os.environ.get("MAKE_ZONE", "eu2")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF2S, WF2R = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx", "U8Bb7Pdq7S6nzYPa"
WFERR = "BbrXPABgOaaTJjD6"
MELISA = 16340280
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
NOW = datetime.now(timezone.utc)
gates = {}


def _get(url, headers, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    try:
        r = urllib.request.Request(url, headers=headers, method=method, data=data)
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            raw = x.read()
            try:
                return {"__status": x.status, "body": json.loads(raw)}
            except Exception:
                return {"__status": x.status, "raw": raw.decode("utf-8", "replace")[:200]}
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return {"__err": str(e)[:150]}


def n8n(p, q=None):
    u = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    d = _get(u, {"X-N8N-API-KEY": KEY, "accept": "application/json"})
    return d.get("body", d)


def sl(p, q=None):
    qq = dict(q or {}); qq["api_key"] = SLK
    d = _get(f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
             {"User-Agent": "janea-flip/1.0"})
    return d.get("body", d)


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def gate(name, ok, detail):
    gates[name] = ok
    print(f"  [{'GREEN' if ok else 'RED  '}] {name}: {detail}")


print("=" * 100)
print("P0b - WF-2R continuation build, clean cycle visible")
print("=" * 100)
wf2r = n8n(f"/api/v1/workflows/{WF2R}")
rcfg = json.loads(next(n for n in wf2r["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
ex = n8n("/api/v1/executions", {"workflowId": WF2R, "limit": 8})
rcycles = sorted((ex.get("data") or []), key=lambda r: str(r.get("startedAt")))
post = [e for e in rcycles if str(e.get("startedAt")) > "2026-08-10T10:5"]
clean = [e for e in post if e.get("status") == "success"]
for e in rcycles[-4:]:
    print(f"    {e['startedAt']} {e.get('status')} id={e['id']}")
gate("P0b", wf2r.get("active") is True and bool(clean),
     f"active={wf2r.get('active')} versionId={wf2r.get('versionId')[:8]} "
     f"resume_rounds={rcfg.get('max_resume_rounds')} pages={rcfg.get('max_pages_per_campaign')} "
     f"clean cycles since deploy={len(clean)}")

print("\n" + "=" * 100)
print("F1 - infrastructure health")
print("=" * 100)
wf2 = n8n(f"/api/v1/workflows/{WF2}")
cfg = json.loads(next(n for n in wf2["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
gate("F1.WF-2-active", wf2.get("active") is True,
     f"active={wf2.get('active')} versionId={str(wf2.get('versionId'))[:8]} "
     f"WRITE_MODE={cfg.get('WRITE_MODE')}")

probe = _get(cfg["wf2_webhook"] if "wf2_webhook" in cfg
             else "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}",
             {"Content-Type": "application/json"}, "POST", {"event_type": "flip_preflight_probe"})
gate("F1.webhook-200", probe.get("__status") == 200 or probe.get("__err") is None,
     f"status={probe.get('__status', probe.get('__err'))}")

wf2s = n8n(f"/api/v1/workflows/{WF2S}")
scfg = json.loads(next(n for n in wf2s["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
sex = n8n("/api/v1/executions", {"workflowId": WF2S, "limit": 5})
srows = sorted((sex.get("data") or []), key=lambda r: str(r.get("startedAt")))
slast = srows[-1] if srows else {}
sage = (NOW - ts(slast.get("startedAt"))).total_seconds() / 60 if slast.get("startedAt") else 9e9
gate("F1.WF-2S", wf2s.get("active") is True and slast.get("status") == "success" and sage < 45,
     f"active={wf2s.get('active')} max_per_run={scfg.get('max_per_run')} "
     f"last={slast.get('startedAt')} ({sage:.0f} min ago) status={slast.get('status')}")

rlast = rcycles[-1] if rcycles else {}
rage = (NOW - ts(rlast.get("startedAt"))).total_seconds() / 60 if rlast.get("startedAt") else 9e9
gate("F1.WF-2R", wf2r.get("active") is True and rlast.get("status") == "success" and rage < 45,
     f"last={rlast.get('startedAt')} ({rage:.0f} min ago) status={rlast.get('status')}")

werr = n8n(f"/api/v1/workflows/{WFERR}")
gate("F1.WF-ERR", werr.get("active") is True, f"active={werr.get('active')}")

owners = cfg.get("forward_owner_map") or {}
has_mario = owners.get("Mario") == "mario@janeasystems.com"
gate("F1.forward-map-mario", has_mario, f"Mario -> {owners.get('Mario')!r}")

print("\n" + "=" * 100)
print("F2 - campaign correctness on the freshest shadow window")
print("=" * 100)
sex2 = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60})
reply_execs = []
for e in sorted((sex2.get("data") or []), key=lambda r: str(r.get("startedAt")), reverse=True):
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})

    def g(nm, k):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
        except Exception:
            return None

    if g("Normalize", "event") != "REPLIED":
        continue
    reply_execs.append({
        "id": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
        "campaign": g("Normalize", "campaign_name"),
        "category": g("Classify Parse", "__category"),
        "conf": g("Classify Parse", "__confidence"),
        "forward_to": g("Forward Resolve", "__forward_to"),
        "forward_owner": g("Forward Resolve", "__forward_owner"),
        "lead_id": g("Lead Resolve", "__lead_id") or g("Merge Reply Ctx", "__lead_id"),
        "lead_how": g("Lead Resolve", "__lead_how"),
        "label_union": g("Body Lead Labels Union", "__label_union"),
    })
    if len(reply_execs) >= 3:
        break
for r in reply_execs:
    print(f"    exec {r['id']} {r['at']}  {str(r['campaign'])[:40]}")
    print(f"        category={r['category']!r} conf={r['conf']} -> {r['forward_to']} "
          f"({r['forward_owner']})")
    print(f"        lead={str(r['lead_id'])[:8]} how={r['lead_how']} labels={r['label_union']}")
cat_ok = all(r["category"] for r in reply_execs)
fwd_ok = all(r["forward_to"] for r in reply_execs)
lead_ok = all(r["lead_id"] for r in reply_execs)
lbl_ok = all((r["label_union"] or []) and RESPONDED in (r["label_union"] or [])
             for r in reply_execs)
gate("F2.replies-categorized", bool(reply_execs) and cat_ok,
     f"{len(reply_execs)} reply execution(s) sampled")
gate("F2.forward-resolved", bool(reply_execs) and fwd_ok, "all have a forward target")
gate("F2.lead-matched", bool(reply_execs) and lead_ok, "all resolved a lead")
gate("F2.label-id", bool(reply_execs) and lbl_ok,
     f"'3. Responded' ({RESPONDED[:8]}) present in every computed union")
gate("F2.owner-melisa", cfg.get("owner_id") == MELISA,
     f"CONFIG.owner_id={cfg.get('owner_id')} (Melisa={MELISA})")
gate("F2.label-const", (cfg.get("labels") or {}).get("responded") == RESPONDED,
     f"CONFIG.labels.responded={(cfg.get('labels') or {}).get('responded')}")

print("\n" + "=" * 100)
print("F3 - kill-list preflight")
print("=" * 100)


def mk(p):
    return _get(f"https://{ZONE}.make.com/api/v2{p}",
                {"Authorization": f"Token {MTOK}", "User-Agent": "janea-flip/1.0"}).get("body", {})


for sid, label in ((8557031, "lead creation"), (8557478, "responded label + forwards")):
    s = (mk(f"/scenarios/{sid}") or {}).get("scenario") or {}
    on = s.get("isActive") is True
    gate(f"F3.make-{sid}", on, f"{label}: isActive={s.get('isActive')} name={str(s.get('name'))[:44]!r}")

backups = [f for f in os.listdir(HERE) if f.startswith(("wf2_backup_before", "wf2r_backup_before"))]
gate("F3.rollback-artifact", len(backups) > 0,
     f"{len(backups)} backup snapshot(s) on disk, newest={sorted(backups)[-1] if backups else None}")

print("\n" + "=" * 100)
red = [k for k, v in gates.items() if not v]
print(f"RESULT: {len(gates) - len(red)}/{len(gates)} GREEN")
if red:
    print("RED GATES:", red)
print("=" * 100)
with open(os.path.join(HERE, "wf1-release-evidence", "flip_f1_f3_preflight.json"), "w",
          encoding="utf-8") as f:
    json.dump({"at": NOW.isoformat(), "gates": gates, "reply_execs": reply_execs}, f,
              indent=2, ensure_ascii=False, default=str)
