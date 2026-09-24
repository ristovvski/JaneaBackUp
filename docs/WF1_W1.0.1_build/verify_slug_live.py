#!/usr/bin/env python3
"""Wire check: send exactly what the DEPLOYED nodes now send, against the real API, and run the
DEPLOYED verification expression over the real response. Statics used a hand-made response shape;
this uses Pipedrive's actual one (custom_fields as a flat array, per W1.0.16)."""
import json, os, re, ssl, subprocess, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p, attempt=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


def pd(p):
    with urllib.request.urlopen(urllib.request.Request(
            "https://api.pipedrive.com" + p,
            headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
            timeout=120, context=ctx) as x:
        return json.load(x)


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N = {n["name"]: n for n in wf["nodes"]}
verify_expr = N["M7 IF URL Found"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
body = verify_expr.strip()[4:-3].strip()  # strip '={{' and '}}'

CASES = [
    ("Person-9979a87c (the live bug)", "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     True),
    ("a slug that should NOT exist", "https://www.linkedin.com/in/pii-f91039f0",
     "zzz-not-a-real-person-9x", False),
]
for label, url, slug, want in CASES:
    resp = pd(f"/api/v2/persons/search?term={urllib.parse.quote(slug)}"
              f"&fields=custom_fields&exact_match=false&limit=20")
    items = ((resp or {}).get("data") or {}).get("items") or []
    src = f"""
const NORM = {{ lead: {{ url: {json.dumps(url)}, slug: {json.dumps(slug)} }} }};
const $ = (nm) => ({{ item: {{ json: NORM }} }});
const $json = {json.dumps(resp)};
console.log(JSON.stringify({{ v: ({body}) }}));
"""
    tmp = os.path.join(HERE, "_live_slug.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"[FAIL] {label}: {(p.stderr or '').strip()[:260]}")
        continue
    v = json.loads(p.stdout.strip().splitlines()[-1])["v"]
    ids = [(i.get("item") or {}).get("id") for i in items]
    print(f"[{'ok ' if v is want else 'FAIL'}] {label}")
    print(f"       live search returned {len(items)} item(s) {ids[:5]}")
    print(f"       DEPLOYED verification -> {v} (want {want})")

# and the old behaviour, for the record
old = pd(f"/api/v2/persons/search?term="
         f"{urllib.parse.quote('https://www.linkedin.com/in/pii-7a798b9a')}"
         f"&fields=custom_fields&exact_match=true&limit=20")
print(f"\nfor the record - the OLD request (verbatim URL, exact_match=true) still returns "
      f"{len((((old or {}).get('data') or {}).get('items') or []))} items")
