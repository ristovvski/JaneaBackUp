#!/usr/bin/env python3
"""READ ONLY final check. Deliberately matches on a substring containing NO escape sequences -
"manually check the inbox" - because two checks today already failed on how a character is
represented rather than on whether it is there."""
import json
import os
import ssl
import sys
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
NEEDLE = "manually check the inbox"


def g(i):
    with urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/v1/workflows/" + i, headers={"X-N8N-API-KEY": KEY}),
            timeout=240, context=ctx) as x:
        return json.load(x)


ok = True
for wid, tag, alert, note in (("2jdjKM2NJr473GdA", "WF-1", "M7 Build", "M7 Build"),
                              ("jp7rum9Z0YDJkQWv", "WF-2", "Body Reply Alert",
                               "Body Reply Activity")):
    w = g(wid)
    N = {n["name"]: n for n in w["nodes"]}
    aj = N[alert]["parameters"]["jsCode"]
    nj = N[note]["parameters"]["jsCode"]
    has_reply = "Reply: " in aj
    has_ph = NEEDLE in nj
    print("%s  version=%s  active=%s  nodes=%d"
          % (tag, str(w.get("versionId"))[:8], w.get("active"), len(w["nodes"])))
    print("   [%s] alert %-20s carries NO 'Reply:' line" % ("ok " if not has_reply else "FAIL",
                                                            alert))
    print("   [%s] note  %-20s still carries the placeholder"
          % ("ok " if has_ph else "FAIL", note))
    ok = ok and (not has_reply) and has_ph
print("\n=== %s ===" % ("VERIFIED" if ok else "PROBLEMS"))
sys.exit(0 if ok else 1)
