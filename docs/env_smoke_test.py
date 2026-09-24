#!/usr/bin/env python3
"""Prove the .env actually WORKS - a populated file is not the same as a working one.

One cheap read-only call per service. Nothing is written anywhere, and no value is ever printed:
each line reports the variable's length and the HTTP outcome only.

    . .\\load_env.ps1 ; python env_smoke_test.py
"""
import json, os, ssl, sys, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path=os.path.join(HERE, ".env")):
    """Also usable standalone, so a bare `python env_smoke_test.py` works without sourcing."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if not t or t.startswith("#") or "=" not in t:
                continue
            k, v = t.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v and not os.environ.get(k.strip()):
                os.environ[k.strip()] = v


load_env()
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def probe(name, var, url, headers=None, ok=lambda d: True):
    val = os.environ.get(var)
    if not val:
        return (name, var, "-", "NOT SET")
    try:
        r = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
            raw = x.read()
            status = x.status
        # A 200 with an empty or non-JSON body is still a successful auth - HeyReach's
        # CheckApiKey answers exactly that way. Demanding JSON here reported a working key as
        # broken, which is the wrong direction to fail in for a credentials check.
        try:
            d = json.loads(raw.decode("utf-8"))
        except Exception:
            return (name, var, len(val),
                    "OK" if 200 <= status < 300 else f"HTTP {status}")
        return (name, var, len(val), "OK" if ok(d) else "REACHED but unexpected shape")
    except urllib.error.HTTPError as e:
        return (name, var, len(val), f"HTTP {e.code}")
    except Exception as e:
        return (name, var, len(val), f"ERR {str(e)[:60]}")


rows = []

pdt = os.environ.get("PIPEDRIVE_API_TOKEN")
rows.append(probe("Pipedrive", "PIPEDRIVE_API_TOKEN",
                  "https://api.pipedrive.com/api/v2/persons?limit=1",
                  {"x-api-token": pdt or ""}, lambda d: "data" in d))

slk = os.environ.get("SMARTLEAD_API_KEY")
rows.append(probe("Smartlead", "SMARTLEAD_API_KEY",
                  f"https://server.smartlead.ai/api/v1/campaigns?api_key="
                  f"{urllib.parse.quote(slk or '')}",
                  {"User-Agent": "janea-smoke/1.0"},
                  lambda d: isinstance(d, (list, dict))))

hrk = os.environ.get("HEYREACH_API_KEY")
rows.append(probe("HeyReach", "HEYREACH_API_KEY",
                  "https://api.heyreach.io/api/public/auth/CheckApiKey",
                  {"X-API-KEY": hrk or "", "Content-Type": "application/json"},
                  lambda d: True))

base = (os.environ.get("N8N_BASE_URL") or "").rstrip("/")
rows.append(probe("n8n", "N8N_API_KEY", f"{base}/api/v1/workflows?limit=1",
                  {"X-N8N-API-KEY": os.environ.get("N8N_API_KEY") or "",
                   "accept": "application/json"},
                  lambda d: "data" in d))

zone = os.environ.get("MAKE_ZONE") or "eu2"
rows.append(probe("Make.com", "MAKE_API_TOKEN",
                  f"https://{zone}.make.com/api/v2/organizations",
                  {"Authorization": f"Token {os.environ.get('MAKE_API_TOKEN') or ''}",
                   "User-Agent": "janea-smoke/1.0"},
                  lambda d: "organizations" in d))

rows.append(probe("OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1/models",
                  {"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY') or ''}"},
                  lambda d: "data" in d))

print(f"{'service':<12} {'variable':<22} {'len':>5}  result")
print("-" * 72)
for name, var, ln, res in rows:
    print(f"{name:<12} {var:<22} {str(ln):>5}  {res}")

ca_ok = bool(CA and os.path.exists(CA))
print(f"\nREQUESTS_CA_BUNDLE present on disk: {ca_ok}"
      + ("" if ca_ok else f"  <-- MISSING at {CA}"))
bad = [r for r in rows if r[3] not in ("OK",)]
print(f"\n{len(rows) - len(bad)}/{len(rows)} services reachable with these credentials")
for r in bad:
    print(f"  FAILED: {r[0]} -> {r[3]}")
sys.exit(1 if bad or not ca_ok else 0)
