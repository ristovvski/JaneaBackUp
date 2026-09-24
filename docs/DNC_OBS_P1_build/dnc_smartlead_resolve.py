"""
Projections Pass, Smartlead channel: resolve email_lc -> Smartlead lead_id(s) for the 2,264
matched persons that have a real email (987 of them, per the seed data). Read-only, GET only,
zero writes. Reuses the proven global lookup GET /leads?email= (see backfill_ai4_persons.py /
c2_backfill300_refresh.py) -- NOT the per-campaign form, which is verified 400 Bad Request.
"""
import json, os, ssl, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
FIX = os.path.join(HERE, "fixtures")
OUT_FILE = os.path.join(FIX, "smartlead_resolve_report.json")
THROTTLE_SECONDS = 0.3


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else ssl.create_default_context()


def sl(path, retries=3):
    url = f"https://server.smartlead.ai/api/v1{path}&api_key={SLK}" if "?" in path \
        else f"https://server.smartlead.ai/api/v1{path}?api_key={SLK}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"accept": "application/json",
                                                         "User-Agent": "Mozilla/5.0 janea-backfill/1.0"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                return {"__status": r.status, **json.loads(r.read())}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"__status": 404}
            if attempt == retries - 1:
                return {"__err": e.code, "__body": e.read()[:300].decode("utf-8", "replace")}
            time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == retries - 1:
                return {"__err": "exception", "__body": str(e)}
            time.sleep(2 ** attempt)


def main():
    with open(os.path.join(FIX, "seed_write_payload_people.json"), encoding="utf-8") as f:
        rows = json.load(f)
    candidates = [r for r in rows if r.get("email_lc") and r.get("pipedrive_person_id")]
    print(f"candidates (matched person + real email): {len(candidates)}")

    results = {"resolved": [], "not_found": [], "already_unsubscribed": [], "errors": []}
    for i, r in enumerate(candidates):
        email = r["email_lc"]
        d = sl(f"/leads?email={urllib.parse.quote(email)}")
        if d is None or d.get("__err"):
            results["errors"].append({"email": email, "identity_key": r["identity_key"],
                                       "error": (d or {}).get("__err")})
        elif d.get("__status") == 404 or not d.get("id"):
            results["not_found"].append({"email": email, "identity_key": r["identity_key"]})
        elif d.get("is_unsubscribed") is True:
            results["already_unsubscribed"].append({
                "email": email, "identity_key": r["identity_key"], "lead_id": d.get("id"),
                "campaigns": [c.get("campaign_id") for c in (d.get("lead_campaign_data") or [])],
            })
        else:
            results["resolved"].append({
                "email": email, "identity_key": r["identity_key"], "lead_id": d.get("id"),
                "campaigns": [c.get("campaign_id") for c in (d.get("lead_campaign_data") or [])],
            })
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(candidates)} resolved so far: "
                  f"resolved={len(results['resolved'])} unsub={len(results['already_unsubscribed'])} "
                  f"not_found={len(results['not_found'])} errors={len(results['errors'])}")
        time.sleep(THROTTLE_SECONDS)

    summary = {
        "total_candidates": len(candidates),
        "resolved_pending_action": len(results["resolved"]),
        "already_unsubscribed_noop": len(results["already_unsubscribed"]),
        "not_found_in_smartlead": len(results["not_found"]),
        "errors": len(results["errors"]),
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT_FILE}")


if __name__ == "__main__":
    main()
