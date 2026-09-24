"""Start the matrix campaigns and wait for sends.

T2 is deliberately held back: its assertion is "person already exists", and the person only exists
after Make has processed T1's send. Starting them together would make T2 a coin flip.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SL = "https://server.smartlead.ai/api/v1"
MANIFEST = Path(__file__).with_name("wf1-release-evidence") / "MATRIX_MANIFEST.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) janea-matrix-harness/1.0"


def sl(path, method="GET", body=None, tries=3):
    key = os.environ["SMARTLEAD_API_KEY"]
    sep = "&" if "?" in path else "?"
    url = f"{SL}{path}{sep}api_key={key}"
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Content-Type": "application/json", "Accept": "application/json",
                "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:160]}"
            if e.code < 500:
                break
            time.sleep(2 * (i + 1))
        except Exception as e:                       # noqa: BLE001
            last = str(e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{method} {path} -> {last}")


def sent_time(cid):
    try:
        st = sl(f"/campaigns/{cid}/statistics")
        rows = st.get("data") or []
        return rows[0].get("sent_time") if rows else None
    except Exception:                                # noqa: BLE001
        return None


def main():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_case = {c["case"]: c for c in man["cases"]}
    hold = {"T2"}

    print("=== starting every campaign except T2 ===")
    for c in man["cases"]:
        if c["case"] in hold:
            print(f"{c['case']:<4} HELD - waits for T1's person to exist")
            continue
        sl(f"/campaigns/{c['campaign_id']}/status", "POST", {"status": "START"})
        print(f"{c['case']:<4} cid={c['campaign_id']} STARTED")

    print("\n=== waiting for T1's send (then release T2) ===")
    t1 = by_case["T1"]
    deadline = time.time() + 15 * 60
    t1_sent = None
    while time.time() < deadline:
        t1_sent = sent_time(t1["campaign_id"])
        if t1_sent:
            break
        time.sleep(20)
    if not t1_sent:
        print("T1 has not sent within 15 minutes - NOT releasing T2")
        return 1
    print(f"T1 sent at {t1_sent}")
    # give Make its ~3s to create the person, plus margin
    time.sleep(45)
    sl(f"/campaigns/{by_case['T2']['campaign_id']}/status", "POST", {"status": "START"})
    print(f"T2   cid={by_case['T2']['campaign_id']} STARTED (after T1)")

    print("\n=== send status for every case ===")
    deadline = time.time() + 20 * 60
    sends = {}
    while time.time() < deadline:
        pending = []
        for c in man["cases"]:
            if c["case"] in sends:
                continue
            s = sent_time(c["campaign_id"])
            if s:
                sends[c["case"]] = s
                print(f"  {c['case']:<4} sent {s}")
            else:
                pending.append(c["case"])
        if not pending:
            break
        time.sleep(30)
    print(f"\nsent: {sorted(sends)}")
    missing = [c["case"] for c in man["cases"] if c["case"] not in sends]
    print(f"NOT sent: {missing or 'none'}")
    man["sends"] = sends
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
