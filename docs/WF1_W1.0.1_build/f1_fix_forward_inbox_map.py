#!/usr/bin/env python3
"""F1 fix - owner addresses missing from forward_inbox_map.

THE DEFECT: `forward_inbox_map` maps a SENDING inbox -> owner name. `forward_owner_map` maps that
owner name -> the address we forward to. The company addresses (mario@janeasystems.com et al) are
present as forward TARGETS but absent as sending INBOXES - so a reply to a campaign sent from a
real company address misses the lookup and falls back to forward_default.

Live proof: exec 13236, sender_inbox mario@janeasystems.com, __forward_reason 'owner_miss',
a MEETING REQUEST forwarded to melisa@janeasystems.com instead of Mario.

In shadow this only mis-addressed a logged intention. At WRITE_MODE=live it mis-delivers real
prospect replies.

Adds every forward_owner_map address as an inbox for its own owner. Idempotent.
"""
import argparse, json, os, ssl, sys, urllib.error, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
        raise


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
cfg_node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
owners = cfg.get("forward_owner_map") or {}
inbox = cfg.get("forward_inbox_map") or {}
lower = {k.lower() for k in inbox}

# 'Test' is an alias owner pointing at melisa@janeasystems.com, and dict iteration order would
# otherwise map Melisa's own inbox to 'Test'. Same forward target either way, but the readable
# owner name is what shows up in ops warnings and in the diff harness - prefer the real person.
missing = {}
for owner, addr in owners.items():
    if not addr or owner == "Test":
        continue
    if addr.lower() not in lower:
        missing[addr.lower()] = owner

print(f"forward_owner_map entries : {len(owners)}")
print(f"forward_inbox_map entries : {len(inbox)}")
print(f"owner addresses NOT registered as sending inboxes: {len(missing)}")
for addr, owner in sorted(missing.items()):
    print(f"   {addr:<46} -> {owner}")

if not missing:
    print("\nnothing to add")
    sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

inbox.update(missing)
cfg["forward_inbox_map"] = dict(sorted(inbox.items()))
cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)

backup = f"wf2_backup_before_inboxmap_{int(datetime.now(timezone.utc).timestamp())}.json"
open(backup, "w", encoding="utf-8").write(json.dumps(n8n(f"/api/v1/workflows/{WF2}"),
                                                     indent=2, ensure_ascii=False))
print(f"\nbackup: {backup}")
was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
if was:
    n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2}")
acfg = json.loads(next(n for n in after["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
aim = acfg.get("forward_inbox_map") or {}
ok = all(addr in aim for addr in missing) and after.get("active") is was
print(f"\nlive verification: {'CLEAN' if ok else 'PROBLEM'}")
print(f"  active={after.get('active')} versionId={after.get('versionId')}")
print(f"  forward_inbox_map entries now: {len(aim)} (+{len(aim) - len(inbox) + len(missing)})")
for addr, owner in sorted(missing.items()):
    print(f"  {addr} -> {aim.get(addr)!r} {'OK' if aim.get(addr) == owner else 'MISSING'}")
print(f"  WRITE_MODE still: {acfg.get('WRITE_MODE')}")
sys.exit(0 if ok else 1)
