#!/usr/bin/env python3
"""Sweep for 'shadow is home' assumptions now that live is the steady state.

The flip inverted the world: WRITE_MODE=live used to be a temporary, risky window that a watchdog
policed; it is now the normal condition, and SHADOW is the anomaly. Anything still written for the
old world will either nag forever or stay silent when it should shout.

Finds:
  * CONFIG keys whose value or name encodes a shadow/live-window assumption
  * node code branching on WRITE_MODE
  * watchdogs that treat 'live' as the alarm condition

READ-ONLY.
"""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p):
    r = urllib.request.Request(BASE + p, headers={"X-N8N-API-KEY": KEY,
                                                  "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


findings = []
for w in n8n("/api/v1/workflows?limit=100").get("data") or []:
    full = n8n(f"/api/v1/workflows/{w['id']}")
    for n in full["nodes"]:
        params = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
        if n["name"] == "CONFIG" and n.get("type") == "n8n-nodes-base.set":
            try:
                cfg = json.loads(n["parameters"]["jsonOutput"])
            except Exception:
                continue
            for k, v in cfg.items():
                kl = k.lower()
                if ("shadow" in kl or "write_mode" in kl or "live" in kl
                        or (isinstance(v, str) and v.lower() == "shadow")):
                    findings.append({"wf": w["name"], "node": "CONFIG", "kind": "config-key",
                                     "detail": f"{k} = {v!r}"})
        if re.search(r"WRITE_MODE|__mode_overdue|__wf2_live_since|'shadow'|\"shadow\"", params):
            snippets = sorted(set(re.findall(r"[^\n\"]{0,60}(?:WRITE_MODE|shadow)[^\n\"]{0,60}",
                                             params)))[:3]
            findings.append({"wf": w["name"], "node": n["name"], "kind": "code-branch",
                             "detail": " | ".join(s.strip()[:110] for s in snippets)})

print(f"findings: {len(findings)}\n")
by_wf = {}
for f in findings:
    by_wf.setdefault(f["wf"], []).append(f)
for wf, rows in by_wf.items():
    print("=" * 96)
    print(wf)
    print("=" * 96)
    for r in rows:
        print(f"  [{r['kind']:<11}] {r['node']}")
        print(f"      {r['detail'][:300]}")
json.dump(findings, open(os.path.join(HERE, "wf1-release-evidence",
                                      "audit_shadow_assumptions.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
print("\nwrote wf1-release-evidence/audit_shadow_assumptions.json")
