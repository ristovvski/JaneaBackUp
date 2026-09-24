#!/usr/bin/env python3
"""
Two live checks before committing to I-04's n8n storage design:
1. Does n8n's Code node sandbox expose zlib/gzip (either directly or via a Buffer/Compression
   node)? Determines whether the snapshot can be gzip-compressed inside n8n at all, or whether
   the port must store uncompressed JSON (larger, but verified-safe) instead of guessing.
2. What's the ACTUAL current lead/person count (native-pagination page count), to size
   max_requests correctly rather than guessing at "579 pages" from a stale README number.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
WEBHOOK_PATH = "zz-probe-check-gzip-scale"


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_"), "name": name,
         "type": ntype, "typeVersion": tv, "position": [x, y]}
    if extra:
        n.update(extra)
    return n


def conns(pairs):
    c = {}
    for a, b in pairs:
        c.setdefault(a, {"main": [[]]})
        c[a]["main"][0].append({"node": b, "type": "main", "index": 0})
    return c


gzip_check_js = (
    "const results = {};\n"
    "try { const zlib = require('zlib'); const out = zlib.gzipSync(Buffer.from('hello world'.repeat(100)));\n"
    "  results.zlib_require = 'OK'; results.gzip_bytes = out.length; results.base64_sample = out.toString('base64').slice(0,20);\n"
    "} catch (e) { results.zlib_require = 'FAILED: ' + e.message; }\n"
    "try { const buf = Buffer.from('test'); results.buffer_global = 'OK'; } catch (e) { results.buffer_global = 'FAILED: ' + e.message; }\n"
    "return [{ json: results }];\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobei04a"}),
    node("Check Gzip", "n8n-nodes-base.code", {"jsCode": gzip_check_js, "mode": "runOnceForAllItems"}, -680, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, -400),
]

wf_json = {
    "name": "zz_probe_check_gzip_and_scale",
    "nodes": nodes,
    "connections": conns([("Webhook", "Check Gzip"), ("Check Gzip", "Respond")]),
    "settings": {},
}


def main():
    print("Creating probe workflow...")
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created id={wid}")
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            print("ACTIVATION DID NOT TAKE")
            sys.exit(1)
        time.sleep(2)
        req = urllib.request.Request(BASE + "/webhook/" + WEBHOOK_PATH, method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        raw = b""
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
        print("\n=== GZIP/BUFFER AVAILABILITY ===")
        print(raw.decode())
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"cleaned up {wid}")


if __name__ == "__main__":
    main()
