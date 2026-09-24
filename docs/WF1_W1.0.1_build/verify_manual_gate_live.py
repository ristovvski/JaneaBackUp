#!/usr/bin/env python3
"""Wire proof: run the DEPLOYED M7 Alert Gate against the REAL Normalize outputs from the four
executions that caused this — Ken (33785), Josh (34588), and two genuine campaign replies.

Synthetic statics used a hand-made campaign object. This uses what actually arrived."""
import json, os, ssl, subprocess, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
GATE = next(n for n in wf["nodes"] if n["name"] == "M7 Alert Gate")["parameters"]["jsCode"]
print(f"deployed gate carries __manual_thread: {'__manual_thread' in GATE}\n")

# find real executions: the two manual ones, plus campaign ones for regression
targets = {}
cur, pages = None, 0
while pages < 6 and len(targets) < 6:
    q = {"workflowId": "2jdjKM2NJr473GdA", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    rows = d.get("data") or []
    if not rows:
        break
    for r in rows:
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if "M7 Alert Gate" not in rd or "Normalize" not in rd:
            continue
        try:
            nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
            b = rd["M7 Build"][0]["data"]["main"][0][0]["json"]
            old = rd["M7 Alert Gate"][0]["data"]["main"][0][0]["json"]
        except Exception:
            continue
        camp = nz.get("campaign") or {}
        kind = "manual" if not (camp.get("id") or camp.get("name")) else "campaign"
        name = (nz.get("lead") or {}).get("full_name")
        k = f"{kind}:{name}"
        if k not in targets and len([1 for t in targets if t.startswith(kind)]) < 3:
            targets[k] = (r["id"], nz, b, old)
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break

print(f"replaying {len(targets)} real executions through the DEPLOYED gate\n")
ok = True
for k, (eid, nz, b, old) in sorted(targets.items()):
    src = f"""
const NORM = {json.dumps(nz, ensure_ascii=False)};
const B = {json.dumps(b, ensure_ascii=False)};
const $json = B;
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: {{}} }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  throw new Error('absent ' + nm);
}};
const SD = {{ __alerted_v1: {{}} }};
const $getWorkflowStaticData = () => SD;
const OUT = (() => {{
{GATE}
}})();
const j = OUT[0].json;
console.log(JSON.stringify({{ should: j.__should_alert, reason: j.__alert_reason,
                              manual: j.__manual_thread }}));
"""
    tmp = os.path.join(HERE, "_vmg.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {k}: {(p.stderr or '').strip()[:200]}")
        ok = False
        continue
    got = json.loads(p.stdout.strip().splitlines()[-1])
    kind = k.split(":")[0]
    want = False if kind == "manual" else True
    good = got["should"] is want
    ok = good and ok
    was = old.get("__should_alert")
    print(f"  [{'ok ' if good else 'FAIL'}] exec {eid}  {k}")
    print(f"        BEFORE (live at the time): should_alert={was} reason={old.get('__alert_reason')!r}")
    print(f"        NOW    (deployed gate)   : should_alert={got['should']} "
          f"reason={got['reason']!r} manual={got['manual']}")
print(f"\nWIRE PROOF: {'PASS' if ok else 'FAIL'}")
