import json,os,ssl,urllib.parse,urllib.request
TOK=(os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_TOKEN")
     or os.environ.get("SLACK_API_TOKEN") or os.environ.get("SLACK_USER_TOKEN"))
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
if not TOK:
    print("no slack token in env; keys with SLACK:", [k for k in os.environ if "SLACK" in k.upper()]); raise SystemExit
for cid in ("C07LTD8UT70","C0B8GCVNR5W","C0BQM1X9ZUY"):
    u="https://slack.com/api/conversations.info?"+urllib.parse.urlencode({"channel":cid})
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={"Authorization":f"Bearer {TOK}"}),timeout=60,context=ctx) as x:
            d=json.load(x)
        c=d.get("channel") or {}
        print(f"  {cid}  ok={d.get('ok')}  name={c.get('name')!r}  private={c.get('is_private')}  err={d.get('error')}")
    except Exception as e:
        print(f"  {cid}  read failed: {str(e)[:90]}")
