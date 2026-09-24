#!/usr/bin/env python3
"""Quote the actual capture conditions: S4 event populations, WF-1's marker parser, WF-2's ids."""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


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


print("=" * 78)
print("1. S4 — dnc_s4_event_populations (hhdnug5xdFLAxrOg)")
print("=" * 78)
wf = n8n("/api/v1/workflows/hhdnug5xdFLAxrOg")
print(f"active={wf.get('active')} nodes={len(wf['nodes'])}")
print("node names:", [n["name"] for n in wf["nodes"]])
for n in wf["nodes"]:
    js = (n.get("parameters") or {}).get("jsCode") or ""
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if n["name"] == "CONFIG" or "jsonOutput" in blob:
        raw = (n.get("parameters") or {}).get("jsonOutput")
        if raw:
            print(f"\n--- {n['name']} CONFIG ---")
            print(raw[:2200])
    if re.search(r"campaign|event", js, re.I):
        print(f"\n--- {n['name']} (code) ---")
        for i, l in enumerate(js.splitlines(), 1):
            if re.search(r"campaign|event|match|includes|indexOf|startsWith|filter", l, re.I):
                print(f"  {i:>3}| {l.rstrip()[:116]}")
    elif re.search(r"campaign", blob, re.I) and n["type"].endswith(("httpRequest", "if", "switch")):
        print(f"\n--- {n['name']} ({n['type'].split('.')[-1]}) ---")
        print("   " + blob[:700])

print("\n" + "=" * 78)
print("2. WF-1 Normalize — the two-bracket event-marker parser")
print("=" * 78)
wf1 = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N1 = {n["name"]: n for n in wf1["nodes"]}
js = N1["Normalize"]["parameters"]["jsCode"]
started = False
for i, l in enumerate(js.splitlines(), 1):
    if "two-bracket" in l:
        started = True
    if started:
        print(f"  {i:>3}| {l.rstrip()[:116]}")
        if "event_trio" in l and "_trio" not in l.split("event_trio")[0]:
            break
cfg1 = json.loads(N1["CONFIG"]["parameters"]["jsonOutput"])
print(f"\n  CONFIG.event_marker_canon = "
      f"{json.dumps(cfg1.get('event_marker_canon'), ensure_ascii=False)[:600]}")
for k in cfg1:
    if "campaign" in k.lower() or "event" in k.lower():
        print(f"  CONFIG.{k} = {json.dumps(cfg1[k], ensure_ascii=False)[:300]}")

print("\n" + "=" * 78)
print("3. WF-2 — where AI4 campaign ids are hardcoded")
print("=" * 78)
wf2 = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
for n in wf2["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if "3686181" in blob or "3686184" in blob:
        js = (n.get("parameters") or {}).get("jsCode") or ""
        print(f"\n--- {n['name']} ---")
        if js:
            for i, l in enumerate(js.splitlines(), 1):
                if "3686" in l or "campaign" in l.lower():
                    print(f"  {i:>3}| {l.rstrip()[:116]}")
        else:
            for m in re.findall(r".{0,90}3686\d{3}.{0,90}", blob):
                print(f"   {m}")
