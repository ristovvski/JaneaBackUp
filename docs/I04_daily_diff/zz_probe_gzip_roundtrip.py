#!/usr/bin/env python3
"""Real functional test: build a moderately-sized JSON string, convert to binary, gzip via
n8n's Compression node, base64-encode for storage, then decompress and verify round-trip
integrity. This is a genuine end-to-end test, not just a "did the node accept the params" check.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
WEBHOOK_PATH = "zz-probe-gzip-roundtrip"


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


build_js = (
    # simulate a moderately large snapshot payload -- repeat a lead-shaped record 5000 times.
    "const rec = { lead_id: 'abc123', label_ids: 'x|y|z', person_id: 12345, add_time: '2026-08-20T00:00:00Z' };\n"
    "const leads = {};\n"
    "for (let i = 0; i < 5000; i++) leads['lead_' + i] = rec;\n"
    "const jsonStr = JSON.stringify({ date: '2026-08-20', leads });\n"
    "const buf = Buffer.from(jsonStr, 'utf-8');\n"
    "return [{ json: { original_length: jsonStr.length }, binary: { data: {\n"
    "  data: buf.toString('base64'), mimeType: 'application/json', fileName: 'snapshot.json' } } }];\n"
)
decompress_js = (
    "const b64 = $input.first().binary.data.data;\n"
    "const gzBuf = Buffer.from(b64, 'base64');\n"
    "return [{ json: { compressed_b64_length: b64.length, gz_bytes: gzBuf.length },\n"
    "  binary: $input.first().binary }];\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -1200, extra={"webhookId": "zzprobei04gz"}),
    node("Build Payload", "n8n-nodes-base.code", {"jsCode": build_js, "mode": "runOnceForAllItems"}, -1000, tv=2),
    node("Compress", "n8n-nodes-base.compression",
         {"operation": "compress", "binaryPropertyName": "data", "outputFormat": "gzip"}, -800, tv=1.1),
    node("Report Compressed", "n8n-nodes-base.code", {"jsCode": decompress_js, "mode": "runOnceForAllItems"}, -600, tv=2),
    node("Decompress", "n8n-nodes-base.compression",
         {"operation": "decompress", "binaryPropertyName": "data", "outputFormat": "gzip"}, -400, tv=1.1),
    node("Verify", "n8n-nodes-base.code", {"jsCode": (
        "const buf = Buffer.from($input.first().binary.data.data, 'base64');\n"
        "const str = buf.toString('utf-8');\n"
        "let parsed = null, parseOk = false;\n"
        "try { parsed = JSON.parse(str); parseOk = true; } catch (e) {}\n"
        "return [{ json: { decompressed_length: str.length, parse_ok: parseOk,\n"
        "  lead_count: parsed ? Object.keys(parsed.leads).length : null } }];\n"
    ), "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_gzip_roundtrip",
    "nodes": nodes,
    "connections": conns([
        ("Webhook", "Build Payload"), ("Build Payload", "Compress"),
        ("Compress", "Report Compressed"), ("Report Compressed", "Decompress"),
        ("Decompress", "Verify"), ("Verify", "Respond"),
    ]),
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
        print("\n=== GZIP ROUND-TRIP RESULT ===")
        print(raw.decode())
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        print(f"deactivated (NOT deleted, id={wid}) -- inspect executions before cleanup")


if __name__ == "__main__":
    main()
