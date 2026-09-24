#!/usr/bin/env python3
"""URGENT CHECK. WF-2H's CONFIG maps 52a7c290-fc73-11f0-ad98-81d4703453f3 -> 'dnc'. That is the one
label Person-9979a87c's lead was already carrying, which I preserved as an unnamed 'human label' and
then added cold + responded beside - and I asked Noah in the team channel to reply to him.

If that label really is Do-Not-Contact, I have told a colleague to contact a lead flagged not to be
contacted. Resolve the label id against Pipedrive itself, not against any single CONFIG."""
import json, os, ssl, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:160]}


print("=== Pipedrive lead labels, by name ===")
r = pd("/v1/leadLabels")
rows = (r or {}).get("data") or []
if r.get("__err"):
    print("  read failed:", r["__err"])
for l in rows:
    print(f"   {l.get('id')}  {l.get('name')!r}  color={l.get('color')}")

TARGET = "52a7c290-fc73-11f0-ad98-81d4703453f3"
hit = [l for l in rows if str(l.get("id")) == TARGET]
print(f"\n  label on Philip's lead ({TARGET}):")
print(f"    -> {hit[0].get('name')!r}" if hit else "    -> NOT FOUND in leadLabels")

print("\n=== Philip's lead right now ===")
lead = (pd("/v1/leads/fb215d20-94e7-11f1-9c86-a5bfb8f637e5") or {}).get("data") or {}
names = {str(l.get("id")): l.get("name") for l in rows}
print(f"   labels: {[(x, names.get(x, '?')) for x in (lead.get('label_ids') or [])]}")
print(f"   person_id={lead.get('person_id')} title={lead.get('title')!r}")

print("\n=== is the PERSON marked do-not-contact / unsubscribed? ===")
p = (pd("/api/v2/persons/85517") or {}).get("data") or {}
print(f"   marketing_status={p.get('marketing_status')!r}")
for e in (p.get("emails") or []):
    print(f"   email={e.get('value')!r}")
