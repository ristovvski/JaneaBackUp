"""B2 setup — pull WF-2's live definition and locate: CONFIG (label ids, owner id), the reply
categorize step, the lead-create body builder, the forward-resolve step, and the shadow-log node.
Read-only. Also fetches Pipedrive's real leadLabels so 'our label ID' can be checked against ground
truth, not assumed.
"""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
WF2 = "jp7rum9Z0YDJkQWv"
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.load(x)


def pd(path):
    r = urllib.request.Request("https://api.pipedrive.com" + path,
                               headers={"x-api-token": PDT, "User-Agent": "janea-flipday/1.0"})
    with urllib.request.urlopen(r, timeout=90) as x:
        return json.load(x)


wf = n8n(f"/api/v1/workflows/{WF2}")
json.dump(wf, open(os.path.join(HERE, "wf2_live_flipday.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"WF-2 live: version={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")

print("\n" + "=" * 92)
print("PIPEDRIVE GROUND TRUTH - the real 'Responded' label id")
print("=" * 92)
for L in pd("/v1/leadLabels").get("data") or []:
    if "respond" in str(L.get("name", "")).lower():
        print(f"  {L['id']}  {L.get('name')}")

print("\n" + "=" * 92)
print("WF-2 CONFIG")
print("=" * 92)
N = {n["name"]: n for n in wf["nodes"]}
cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
print(json.dumps(cfg, ensure_ascii=False, indent=2)[:3000])

print("\n" + "=" * 92)
print("NODE NAMES (all 145)")
print("=" * 92)
print([n["name"] for n in wf["nodes"]])
