#!/usr/bin/env python3
"""Deploy dnc_morning_digest.post.json to the live digest through safe_patch_workflow, which aborts
on ANY node diff other than exactly the one expected. Checks the live version is still the one the
patch was built from first."""
import json, os, ssl, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "DNC_OBS_P1_build"))
from patch_utils import safe_patch_workflow  # noqa: E402
env = {}
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.strip().split("=", 1); env[k] = v.strip('"')
ctx = ssl.create_default_context(cafile=env.get("REQUESTS_CA_BUNDLE"))
BASE = env["N8N_BASE_URL"].rstrip("/")
def n8n(path, method="GET", body=None):
    p = path if path.startswith("/api/") else "/api/v1" + path
    r = urllib.request.Request(BASE.replace("/api/v1", "") + p, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": env["N8N_API_KEY"], "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        raw = x.read(); return json.loads(raw) if raw else {}
WID = "qJKfR602wV9yfFrj"
built_from = json.load(open(os.path.join(HERE, "backup", "dnc_morning_digest.pre.json"), encoding="utf-8"))["versionId"]
live = n8n("/api/v1/workflows/" + WID)
if live["versionId"] != built_from:
    raise SystemExit("ABORT: live digest changed since the patch was built (%s != %s)" % (live["versionId"], built_from))
v = safe_patch_workflow(n8n, WID, os.path.join(HERE, "dnc_morning_digest.post.json"), "digest",
    expected_to_add={"DT Domains Rows", "DT Domains Agg", "DT Claims Rows", "DT Size Agg"},
    expected_to_remove={"CRM Changelog 24h", "Changelog Count"},
    expected_param_diffs={"CONFIG", "Compose"})
post = json.load(open(os.path.join(HERE, "dnc_morning_digest.post.json"), encoding="utf-8"))
same = lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
L = {n["name"]: n for n in v["nodes"]}
print("versionId", v["versionId"], "active", v["active"], "nodes", len(v["nodes"]))
print("connections identical to local:", same(v["connections"], post["connections"]))
print("Compose/CONFIG/DT Size Agg code identical:", all(same(L[n]["parameters"], {m["name"]: m for m in post["nodes"]}[n]["parameters"])
      for n in ("Compose", "CONFIG", "DT Size Agg", "DT Domains Agg", "DT Domains Rows", "DT Claims Rows")))
json.dump(v, open(os.path.join(HERE, "backup", "dnc_morning_digest.post-live.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
