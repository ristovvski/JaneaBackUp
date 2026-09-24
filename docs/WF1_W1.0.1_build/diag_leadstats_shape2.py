import os, json, urllib.request, urllib.parse
SLK = os.environ["SMARTLEAD_API_KEY"]
UA = "Mozilla/5.0 janea-forensics/1.0"
CAMPS = [3686193, 3686187, 3686184, 3686181]
types_seen = {}
sample_reply = None
for cid in CAMPS:
    skip = 0
    for _ in range(6):
        url = "https://server.smartlead.ai/api/v1/campaigns/%s/leads-statistics?" % cid + urllib.parse.urlencode({"limit": 100, "offset": skip, "api_key": SLK})
        r = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(r, timeout=45) as x:
            data = json.load(x)
        rows = data.get("data") or []
        for row in rows:
            for h in (row.get("history") or []):
                t = h.get("type")
                types_seen[t] = types_seen.get(t, 0) + 1
                if t and t != "SENT" and sample_reply is None:
                    sample_reply = {"lead_id": row.get("lead_id"), "to": row.get("to"), "event": h}
            # also check top-level fields for category info
        if not data.get("hasMore"):
            break
        skip += 100
print("event types seen across all 4 campaigns:", types_seen)
if sample_reply:
    print("\nSAMPLE non-SENT event:")
    print(json.dumps(sample_reply, indent=2, default=str)[:2000])
else:
    print("\nNo non-SENT event type found in any page.")
# also print top-level keys of a row that might carry category
for cid in CAMPS[:1]:
    url = "https://server.smartlead.ai/api/v1/campaigns/%s/leads-statistics?" % cid + urllib.parse.urlencode({"limit": 20, "offset": 0, "api_key": SLK})
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(r, timeout=45) as x:
        data = json.load(x)
    for row in (data.get("data") or []):
        print("row top-level keys:", sorted(row.keys()))
        break
