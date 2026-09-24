"""
ENRICH QUEUE artifact (Nik, 2026-08-18): the S1 + S2 no-identity skips, as one review list for a
Slava/Clay enrichment pass. Pulls the actual skip records (full_name, pipedrive_person_id, source,
what's missing) directly from each fire's executions -- not re-derived, the real logged data.
"""
import os
import json
import requests

WF_IDS = {"S1": "BxJZmz1HY5AdaQqE", "S2": "E0oTTvHHQ0hVTNDD"}
LOG_NODE = {"S1": "S1 Log No Identity", "S2": "S2 Log No Identity"}


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def n8n_headers():
    return {"X-N8N-API-KEY": os.environ["N8N_API_KEY"], "accept": "application/json"}


def collect(scenario, base_url, limit=30):
    wf_id = WF_IDS[scenario]
    node = LOG_NODE[scenario]
    r = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": wf_id, "limit": limit},
                      headers=n8n_headers(), timeout=30)
    execs = r.json().get("data", [])
    rows = []
    seen_pids = set()
    for e in execs:
        r2 = requests.get(f"{base_url}/api/v1/executions/{e['id']}", params={"includeData": "true"},
                           headers=n8n_headers(), timeout=30)
        run = r2.json().get("data", {}).get("resultData", {}).get("runData", {})
        entries = run.get(node)
        if not entries:
            continue
        items = entries[0]["data"]["main"][0] or []
        for item in items:
            j = item["json"]
            pid = j.get("pipedrive_person_id")
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            rows.append({
                "full_name": j.get("full_name"),
                "pipedrive_person_id": pid,
                "source": j.get("source"),
                "missing": "email, LinkedIn" if not j.get("email") and not j.get("linkedin_url") else
                           ("email" if not j.get("email") else "LinkedIn"),
            })
    return rows


def main():
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    s1_rows = collect("S1", base_url, limit=50)
    s2_rows = collect("S2", base_url, limit=30)
    print(f"S1 no-identity rows collected: {len(s1_rows)}")
    print(f"S2 no-identity rows collected: {len(s2_rows)}")

    out = {"s1_no_identity": s1_rows, "s2_no_identity": s2_rows,
           "s1_count": len(s1_rows), "s2_count": len(s2_rows)}
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "enrich_queue.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"written to {out_path}")


if __name__ == "__main__":
    main()
