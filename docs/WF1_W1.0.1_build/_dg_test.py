import json,os,ssl,urllib.request
from deal_guard import assert_safe_to_create_lead, activity_target, DealGuardBlocked
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
print("LIVE test against the real record that caused this:")
for who,pid in (("Andrea 69696 (open deal - MUST block)",69696),
                ("Philip 85517 (no deals - must allow)",85517)):
    try:
        assert_safe_to_create_lead(pd,pid); print(f"  ALLOW  {who}")
    except DealGuardBlocked as e: print(f"  BLOCK  {who}\n         {e}")
    print(f"         activity_target -> {activity_target(pd,pid)}")
def bad(p): return {"__err":"boom"}
try:
    assert_safe_to_create_lead(bad,1); print("  FAIL: unknown state did not block")
except DealGuardBlocked as e: print(f"  BLOCK  unknown deal state (fail closed)\n         {e}")
