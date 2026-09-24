#!/usr/bin/env python3
"""#29 (1): does HeyReach auto-withdraw unaccepted connection requests after N days, and is it
configurable PER CAMPAIGN?

Probe the API for the setting rather than reasoning from the UI. Look at: campaign objects (any
withdraw/expiry field), LinkedIn account objects (account-level setting), and any settings endpoint.
Report what the API actually exposes - and say plainly what it does NOT, rather than inferring.
"""
import json, os, ssl, urllib.parse, urllib.request

CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
KEY = (os.environ.get("HEYREACH_API_KEY") or os.environ.get("HEYREACH_KEY")
       or os.environ.get("HEY_REACH_API_KEY"))
print(f"HeyReach key present: {bool(KEY)}")
if not KEY:
    print("env keys containing 'HEY':",
          [k for k in os.environ if "HEY" in k.upper()])
    raise SystemExit("no HeyReach API key in env - stopping rather than guessing")

BASE = "https://api.heyreach.io/api/public"


def hr(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-API-KEY": KEY, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": f"HTTP {e.code} {e.read()[:200].decode('utf-8','replace')}"}
    except Exception as e:
        return {"__err": str(e)[:160]}


WORDS = ("withdraw", "cancel", "expire", "expiry", "pending", "days", "timeout", "auto",
         "retract", "cleanup")


def scan(obj, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if any(w in k.lower() for w in WORDS):
                hits.append((p, v if not isinstance(v, (dict, list)) else type(v).__name__))
            hits += scan(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            hits += scan(v, f"{path}[{i}]")
    return hits


print("\n=== campaigns ===")
camps = hr("/campaign/GetAll", "POST", {"offset": 0, "limit": 5})
if camps.get("__err"):
    print("  ", camps["__err"])
else:
    items = camps.get("items") or camps.get("data") or []
    print(f"  campaigns returned: {len(items)}")
    if items:
        print(f"  campaign object keys: {sorted(items[0].keys())}")
        h = scan(items[0])
        print(f"  fields matching withdraw/expiry vocabulary: {h or 'NONE'}")
        cid = items[0].get("id")
        det = hr(f"/campaign/GetById?campaignId={cid}")
        if not det.get("__err"):
            print(f"\n  GetById keys: {sorted(det.keys())}")
            print(f"  matches: {scan(det) or 'NONE'}")
            for k in ("campaignSettings", "settings", "sequence", "steps"):
                if k in det:
                    print(f"  {k}: {json.dumps(det[k], ensure_ascii=False)[:700]}")
        else:
            print("  GetById:", det["__err"])

print("\n=== linkedin accounts (account-level setting?) ===")
accs = hr("/linkedinaccount/GetAll", "POST", {"offset": 0, "limit": 5})
if accs.get("__err"):
    print("  ", accs["__err"])
else:
    items = accs.get("items") or accs.get("data") or []
    print(f"  accounts: {len(items)}")
    if items:
        print(f"  keys: {sorted(items[0].keys())}")
        print(f"  matches: {scan(items[0]) or 'NONE'}")

print("\n=== other endpoints worth a look ===")
for p, m, b in (("/campaign/GetCampaignsForLinkedInAccount", "POST", {"offset": 0, "limit": 2}),
                ("/list/GetAll", "POST", {"offset": 0, "limit": 2}),
                ("/stats/GetOverallStats", "POST", {})):
    r = hr(p, m, b)
    print(f"  {p}: {'ERR ' + r['__err'] if r.get('__err') else sorted(list(r.keys()))[:8]}")
