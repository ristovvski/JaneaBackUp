"""WF-2 classifier calibration report.

PURPOSE
Decide the confidence threshold on evidence instead of on one sample. For every organic REPLIED
execution it records the triple that matters:

    ours (category + confidence)   vs   Smartlead native category   vs   where it actually forwarded

then reports the confidence distribution and, for a range of candidate thresholds, how much traffic
each one would send to human review and how often we agreed with Smartlead on the rest.

WHY IT PERSISTS TO A LEDGER
n8n retains ~13 hours of executions (250 rows covered 13.0h on 2026-07-30, and the list was still
paginating). Reaching 30-50 organic replies takes days, so reading executions on demand would keep
losing the earlier half of the sample. Every run appends new executions to a JSONL ledger, keyed by
execution id, so the evidence accumulates even as n8n prunes. Re-running is safe and idempotent.

READ-ONLY: this touches nothing but the n8n executions API and its own ledger file.

  python wf2_calibration.py                 # ingest new executions, print the report
  python wf2_calibration.py --report-only   # print from the ledger without calling n8n
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

WF2_ID = "jp7rum9Z0YDJkQWv"
LEDGER = Path(__file__).with_name("wf1-release-evidence") / "wf2-calibration-ledger.jsonl"

# Nik's own address: his test reply was deliberately terse ("Sounds good, thanks for reaching out!")
# and is not representative of prospect replies, so it is recorded but excluded from the statistics.
SYNTHETIC_LEADS = {"pii-c61c7d08@example.invalid"}
# Anything on a .invalid domain is one of my own probe leads, never a prospect.
# .invalid and test.com are both mine: pii-ef1d7dcd@example.invalid x5 came from my own probe payloads.
SYNTHETIC_DOMAINS = (".invalid", "@test.com", ".test.com")

# Older executions recorded reply_category as the RAW NUMERIC id, because they ran before the
# id->name fix was deployed. Comparing "Meeting Request" against 2 counted a correct call as a
# disagreement - it reported 50% agreement when the true figure was far higher. Resolution happens
# at REPORT time, not ingest time, so rows already in the ledger get corrected too.
_CATEGORY_MAP = None


def category_map():
    global _CATEGORY_MAP
    if _CATEGORY_MAP is None:
        import json as _j
        wf = _j.loads(Path(__file__).with_name("WF-2 Smartlead Receiver - built.json")
                      .read_text(encoding="utf-8"))
        cfg = _j.loads(next(n for n in wf["nodes"]
                            if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
        _CATEGORY_MAP = {v: k for k, v in (cfg.get("category_map") or {}).items()}
    return _CATEGORY_MAP


_FORWARDABLE = None


def forwardable_categories():
    global _FORWARDABLE
    if _FORWARDABLE is None:
        import json as _j
        wf = _j.loads(Path(__file__).with_name("WF-2 Smartlead Receiver - built.json")
                      .read_text(encoding="utf-8"))
        cfg = _j.loads(next(n for n in wf["nodes"]
                            if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
        _FORWARDABLE = {c.strip().lower() for c in (cfg.get("forwardable_categories") or [])}
    return _FORWARDABLE


def norm_cat(v):
    """Category as a comparable NAME, whether it arrived as a name or a numeric id."""
    if v is None or v == "":
        return None
    s = str(v).strip()
    if s.isdigit():
        return category_map().get(int(s), f"id:{s}")
    return s

CANDIDATE_THRESHOLDS = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]


def api(path):
    base = os.environ["N8N_BASE_URL"].rstrip("/")
    req = urllib.request.Request(base + path,
                                 headers={"X-N8N-API-KEY": os.environ["N8N_API_KEY"]})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def node_json(run_data, name, default=None):
    """First output item of a node, or default if the node did not run."""
    try:
        return run_data[name][0]["data"]["main"][0][0]["json"]
    except Exception:
        return default


def extract(ex_id, detail):
    rd = detail.get("data", {}).get("resultData", {}).get("runData", {})
    nz = node_json(rd, "Normalize")
    if not nz or nz.get("event") != "REPLIED":
        return None
    cp = node_json(rd, "Classify Parse", {}) or {}
    fr = node_json(rd, "Forward Resolve", {}) or {}
    usage = cp.get("__llm_usage") or {}
    lead = (nz.get("lead") or {}).get("email")
    return {
        "exec_id": ex_id,
        "at": detail.get("startedAt"),
        "campaign_id": nz.get("campaign_id"),
        "campaign_name": nz.get("campaign_name"),
        "lead_email": lead,
        "is_nurture": nz.get("is_nurture") is True,
        "synthetic": ((lead or "").lower() in SYNTHETIC_LEADS
                      or (lead or "").lower().endswith(SYNTHETIC_DOMAINS)),
        # ours
        "our_category": cp.get("__category"),
        "our_confidence": cp.get("__confidence"),
        "classify_ok": cp.get("__classify_ok"),
        "category_source": cp.get("__category_source"),
        "is_dnc": cp.get("__is_dnc"),
        "forwardable": cp.get("__forwardable"),
        # theirs (Smartlead's own labeller; empty when they have not labelled it)
        "native_category": nz.get("reply_category") or None,
        # what actually happened
        "forward_to": fr.get("__forward_to"),
        "forward_reason": fr.get("__forward_reason"),
        "category_written": "SL Category" in rd,
        "category_skipped": "Skip SL Category" in rd,
        "tokens": usage.get("total"),
        "model": usage.get("model"),
    }


def ingest(limit_pages=40):
    seen = set()
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seen.add(json.loads(line)["exec_id"])
    added, cursor, pages = 0, None, 0
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        while pages < limit_pages:
            pages += 1
            q = f"/api/v1/executions?workflowId={WF2_ID}&limit=250"
            if cursor:
                q += "&cursor=" + cursor
            page = api(q)
            rows = page.get("data") or []
            if not rows:
                break
            for ex in rows:
                if ex["id"] in seen:
                    continue
                try:
                    detail = api(f"/api/v1/executions/{ex['id']}?includeData=true")
                except urllib.error.HTTPError:
                    continue
                rec = extract(ex["id"], detail)
                seen.add(ex["id"])
                if rec:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    added += 1
            cursor = page.get("nextCursor")
            if not cursor:
                break
    return added, len(seen)


def load():
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]


def bucket(c):
    if c is None:
        return "none"
    for lo in (0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.5):
        if c >= lo:
            return f">={lo:.2f}"
    return "<0.50"


def is_synthetic(r):
    """Derived at REPORT time, not read from the stored field.

    The stored flag reflects whatever rule was in force when the row was ingested, so widening the
    rule (e.g. adding .invalid probe domains) would otherwise never apply to rows already banked.
    Same principle as category resolution: keep the ledger raw, normalise when reporting.
    """
    lead = (r.get("lead_email") or "").lower()
    return lead in SYNTHETIC_LEADS or lead.endswith(SYNTHETIC_DOMAINS)


def report(rows):
    usable = [r for r in rows if not is_synthetic(r) and not r["is_nurture"]]
    print(f"ledger: {len(rows)} replies recorded  |  usable for stats: {len(usable)}"
          f"  (excluded: {len(rows) - len(usable)} synthetic/nurture)")
    if not usable:
        print("\nnothing to calibrate yet - the ledger grows as organic replies arrive.")
        return
    print(f"target sample for a threshold decision: 30-50  ->  "
          f"{'REACHED' if len(usable) >= 30 else f'{30 - len(usable)} more needed'}")

    print("\n-- confidence distribution (ours) --")
    for b, n in sorted(Counter(bucket(r["our_confidence"]) for r in usable).items(), reverse=True):
        print(f"   {b:>7}  {'#' * n} {n}")

    print("\n-- where replies actually went --")
    def dest(r):
        if r["forward_reason"]:
            return r["forward_reason"]
        # No Forward Resolve. Attribute it correctly instead of calling it a gap: an Out Of Office
        # or Wrong Person reply is DELIBERATELY not forwarded, and lumping those in with genuine
        # dead-ends made half the sample look broken when it was working exactly as designed.
        if r.get("is_dnc"):
            return "dnc (no fwd)"
        cat = r.get("our_category")
        if cat and str(cat).strip().lower() not in forwardable_categories():
            return "not forwardable"
        return "no classification"
    for reason, n in Counter(dest(r) for r in usable).most_common():
        print(f"   {str(reason):<16} {n:>3}  ({100.0 * n / len(usable):.0f}%)")

    print("\n-- ours vs Smartlead native (only where they labelled it) --")
    both = [r for r in usable if norm_cat(r["native_category"]) and r["our_category"]]
    if both:
        agree = [r for r in both if str(r["our_category"]).strip().lower()
                 == str(norm_cat(r["native_category"])).strip().lower()]
        print(f"   comparable: {len(both)}   agree: {len(agree)} "
              f"({100.0 * len(agree) / len(both):.0f}%)")
        for r in both:
            if r not in agree:
                print(f"     DISAGREE {r['lead_email']}: ours={r['our_category']}"
                      f" ({r['our_confidence']}) vs native={norm_cat(r['native_category'])}")
    else:
        print("   none yet - Smartlead had not labelled any of these replies")

    print("\n-- threshold counterfactual: what each cutoff would do to this sample --")
    print(f"   {'cutoff':>7} {'to review':>10} {'auto-fwd':>9}  agreement among auto-forwarded")
    scored = [r for r in usable if isinstance(r["our_confidence"], (int, float))]
    for t in CANDIDATE_THRESHOLDS:
        review = [r for r in scored if r["our_confidence"] < t]
        auto = [r for r in scored if r["our_confidence"] >= t]
        cmp_ = [r for r in auto if norm_cat(r["native_category"]) and r["our_category"]]
        ag = [r for r in cmp_ if str(r["our_category"]).strip().lower()
              == str(norm_cat(r["native_category"])).strip().lower()]
        rate = f"{100.0 * len(ag) / len(cmp_):.0f}% of {len(cmp_)}" if cmp_ else "no comparable"
        mark = "  <- current" if abs(t - 0.70) < 1e-9 else ""
        print(f"   {t:>7.2f} {len(review):>6} ({100.0 * len(review) / max(1, len(scored)):.0f}%)"
              f" {len(auto):>8}  {rate}{mark}")
    print("\n   Read it as the trade: a lower cutoff sends less to Melisa but auto-forwards more"
          "\n   replies we were unsure about. Move the threshold only when the agreement column"
          "\n   still holds up at the looser cutoff.")

    tok = [r["tokens"] for r in usable if r["tokens"]]
    if tok:
        print(f"\n-- cost -- {len(tok)} classifications, mean {sum(tok) / len(tok):.0f} tokens"
              f", total {sum(tok)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true",
                    help="print from the ledger without querying n8n")
    a = ap.parse_args()
    if not a.report_only:
        for var in ("N8N_BASE_URL", "N8N_API_KEY"):
            if not os.environ.get(var):
                print(f"ERROR: {var} not set", file=sys.stderr)
                return 1
        added, scanned = ingest()
        print(f"ingested {added} new REPLIED execution(s) from {scanned} scanned\n")
    report(load())
    print(f"\nledger: {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
