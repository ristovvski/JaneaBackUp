#!/usr/bin/env python3
"""Confirmed miss: HeyReach sends 'https://www.linkedin.com/in/pii-7a798b9a', Pipedrive stores
'https://linkedin.com/in/pii-7a798b9a'. Term search on the full URL WITH www -> 0 hits.

Two things left before proposing a fix:
  1. what expression does M7 Person Search URL actually send (raw URL? slug?)
  2. how many stored persons carry a format that would miss - is this one lead or a class?
Bounded sample, no bulk sweep.
"""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
LI = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"


def n8n(p, attempt=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:140]}


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N = {n["name"]: n for n in wf["nodes"]}
for nm in ("M7 Person Search URL", "M7 Person Search Member", "M7 Person Search Email"):
    n = N.get(nm)
    if not n:
        continue
    blob = json.dumps(n.get("parameters"), ensure_ascii=False)
    print(f"=== {nm} ===")
    for m in re.findall(r'"(?:url|value)":\s*"([^"]{0,240})"', blob):
        if "term" in m or "persons" in m or "linkedin" in m.lower():
            print(f"   {m[:230]}")
    print()

print("=== stored linkedin_lh formats (bounded sample) ===")
fmt = {}
cursor = None
scanned = 0
for _ in range(3):
    q = f"/api/v2/persons?limit=100&include_fields=&custom_fields={LI}"
    if cursor:
        q += f"&cursor={cursor}"
    r = pd(q)
    rows = (r or {}).get("data") or []
    if not rows:
        break
    for p in rows:
        scanned += 1
        v = ((p.get("custom_fields") or {}).get(LI))
        if not v or not isinstance(v, str):
            continue
        if "linkedin" not in v.lower():
            continue
        key = ("www." if "//www." in v else "no-www") + \
              (" +https" if v.lower().startswith("https") else
               (" +http" if v.lower().startswith("http") else " +bare")) + \
              (" +slash" if v.rstrip().endswith("/") else "")
        fmt[key] = fmt.get(key, 0) + 1
    cursor = ((r.get("additional_data") or {}).get("next_cursor"))
    if not cursor:
        break
print(f"  persons scanned: {scanned}")
tot = sum(fmt.values())
for k, v in sorted(fmt.items(), key=lambda t: -t[1]):
    print(f"   {k:<22} {v:>4}  ({100*v/tot:.0f}% of {tot} with a linkedin value)")
print("\n  HeyReach sends 'https://www.linkedin.com/in/<slug>'. A verbatim term search matches only")
print("  the rows whose stored string starts the same way; every other format above is a MISS.")
