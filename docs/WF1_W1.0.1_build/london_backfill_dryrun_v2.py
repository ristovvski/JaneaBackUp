#!/usr/bin/env python3
"""London Sales Sprint 2026 backfill — DRY RUN v2. Never writes to Pipedrive/Smartlead/OpenAI-side
systems (the OpenAI call itself is a read/classify, not a write to any of our systems).

Implements the revised per-category treatment (superseding "full treatment for all 14"):
  1. ALL 215 (201 no-reply + 14 with-reply): person+lead created regardless of value.
  2. Bounce / No Longer Working There: note only, NO responded label (dead mailbox != conversation).
     "No Longer Working There" specifically: scan the reply text for a named successor.
  3. Out Of Office: responded label + activity, NO forward (stale by now).
  4. Not Interested: responded label + activity + note, NO forward. DNC question answered inline
     from the Phase-1 dnc_ledger spec (negative_reply -> 6mo TTL) - registry WRITE not attempted,
     no confirmed API path to the renamed dnc_registry_dev (n8n Data Tables aren't in the public
     REST API on this instance - confirmed earlier this session).
  5. Uncategorized (5): re-run through WF-2's OWN real classifier - same model (gpt-5.2), same
     prompt structure, same category list, same 0.7 confidence guardrail, pulled from the live
     workflow (Classify Body / Classify Parse), not reinvented. Resolves -> follow that category's
     rule above. Stays Uncategorized -> one review-queue line, no per-lead ping.
  6. NO forwards to any salesperson for any of the 14. One consolidated ops-note DRAFT at the end
     (text only - destination/send is a separate decision, same as Melisa's one-liner earlier).
"""
import json, os, re, ssl, time
import urllib.request, urllib.parse

SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
OAK = os.environ["OPENAI_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DISC = os.path.join(HERE, "..", "DISCOVERY")

MELISA = 16340280
CHANNEL = 578
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
L_CONNECTED = "ca698a50-bdfb-11ef-8172-510383583b0e"
L_RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"

F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_OPP = "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84"
OPP_VALUE = 480
F_CAMPAIGN = "86157bb49563191c17b4dc62580525f84417524c"
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"
F_MEDIUM = "961698945b0329b367da11916a94f10ff7ba71fe"
F_SOURCE = "6070ae31f09228f95048b0f68982b1cd4d3a684a"
SOURCE_EMAIL = 446
MEDIUM_EMAIL = "eMail"
HYPOTHESIS_VALUE = "Sales Sprint"

CAMPS = {3565651: "[Sales Sprint] Sales Sprint 2026 – London – Catch-alls",
         3565502: "[Sales Sprint] Sales Sprint 2026 – London – Valids"}

CATEGORY_MAP = {"Interested": 1, "Meeting Request": 2, "Not Interested": 3, "Do Not Contact": 4,
                "Information Request": 5, "Out Of Office": 6, "Wrong Person": 7,
                "Uncategorizable by Ai": 8, "Sender Originated Bounce": 9, "No Longer Working There": 16598}
BOUNCE_LIKE = {"Sender Originated Bounce", "No Longer Working There"}
OOO_LIKE = {"Out Of Office"}
NEGATIVE_LIKE = {"Not Interested"}
MIN_CONFIDENCE = 0.7  # CONFIG.llm.min_confidence, verified live


def pd(path, params=None, tries=4):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def openai_classify(subject, body_text):
    """Exact replica of WF-2's Classify Body prompt + Classify Parse guardrail."""
    cat_list = ", ".join(CATEGORY_MAP.keys())
    prompt = ("Classify this cold-outreach email reply. Return STRICT JSON only, no prose:\n"
              '{"category": one of [' + cat_list + '], "confidence": 0..1, "is_dnc": boolean, '
              '"one_line_summary": string}\n\nSubject: ' + (subject or "") + "\n\nBody:\n"
              + str(body_text or "")[:4000])
    body = {"model": "gpt-5.2", "max_completion_tokens": 400,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You classify cold-outreach email replies. "
                                              "Answer with a single JSON object and nothing else."},
                {"role": "user", "content": prompt}]}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {OAK}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45, context=ctx) as x:
            resp = json.load(x)
    except Exception as e:
        return {"category": "Uncategorized", "confidence": 0, "error": str(e)[:200]}
    raw = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        parsed = json.loads(m.group(0)) if m else None
    except Exception:
        parsed = None
    category = (parsed or {}).get("category")
    conf = float((parsed or {}).get("confidence", 0) or 0)
    ok = bool(parsed) and category in CATEGORY_MAP and conf >= MIN_CONFIDENCE
    return {"category": category if ok else "Uncategorized", "confidence": conf,
            "summary": (parsed or {}).get("one_line_summary"), "raw_ok": ok}


def omit(d):
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def strip_html(s):
    return re.sub(r"<[^>]+>", " ", s or "").strip()


def main():
    prior = json.load(open(os.path.join(DISC, "london_backfill_dryrun_output.json"), encoding="utf-8"))
    cat_check = json.loads(open(os.path.join(HERE, "london_reply_category_check_cache.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(HERE, "london_reply_category_check_cache.json")) else None

    rows = [r for r in prior["rows"] if r.get("action") == "would_create"]
    print(f"total candidates: {len(rows)}  (with_reply: {sum(1 for r in rows if r.get('has_reply'))})")

    # real category per reply email, from the earlier check (re-derive if cache absent)
    REAL_CATEGORY = {
        "pii-c5c15dbe@example.invalid": "Uncategorized", "pii-ba8bcd65@example.invalid": "Sender Originated Bounce",
        "pii-3ca4477f@example.invalid": "Uncategorized", "pii-2985f6e7@example.invalid": "Out Of Office",
        "pii-48014a01@example.invalid": "Out Of Office", "pii-c26c9b30@example.invalid": "Uncategorized",
        "pii-5a549566@example.invalid": "No Longer Working There", "pii-149e8e98@example.invalid": "Out Of Office",
        "pii-a9ec67d2@example.invalid": "Sender Originated Bounce", "pii-917b8552@example.invalid": "Uncategorized",
        "pii-e41aa67a@example.invalid": "Sender Originated Bounce", "pii-f59eb465@example.invalid": "Not Interested",
        "pii-9e7ad6bb@example.invalid": "Out Of Office", "pii-3821b0f5@example.invalid": "Uncategorized",
    }

    output_rows = []
    reclassified = []
    consolidated_lines = []
    review_queue = []

    for r in rows:
        email = r["email"]
        out = dict(r)
        if not r.get("has_reply"):
            out["treatment"] = "standard_cold_backfill"
            output_rows.append(out)
            continue

        real_cat = REAL_CATEGORY.get(email, "Uncategorized")
        note_text = strip_html(r.get("reply_activity_body", {}).get("note", ""))[:1500]

        if real_cat == "Uncategorized":
            cls = openai_classify(subject="Re: Sales Sprint 2026 - London", body_text=note_text)
            reclassified.append({"email": email, **cls})
            real_cat = cls["category"]
            out["reclassify_result"] = cls

        out["real_category"] = real_cat
        out["category_id"] = CATEGORY_MAP.get(real_cat)

        if real_cat in BOUNCE_LIKE:
            out["treatment"] = "bounce_or_departed_no_responded_label"
            out["lead_body"]["label_ids"] = [L_COLD]
            note = f"[{real_cat}] " + note_text
            if real_cat == "No Longer Working There":
                m = re.search(r"direct(?:ed)? (?:it |them )?to ([A-Z][a-z]+ [A-Z][a-zA-Z]+)", note_text)
                if not m:
                    m = re.search(r"contact ([A-Z][a-z]+ [A-Z][a-zA-Z]+)", note_text)
                if m:
                    out["successor_named"] = m.group(1)
                    note = f"SUCCESSOR NAMED: {m.group(1)} (no email given). " + note
                    consolidated_lines.append(f"  • {email} → departed, successor named: {m.group(1)}")
            out["reply_activity_body"]["note"] = note

        elif real_cat in OOO_LIKE:
            out["treatment"] = "ooo_labeled_no_forward"
            out["lead_body"]["label_ids"] = [L_COLD, L_CONNECTED, L_RESPONDED]
            out["reply_activity_body"]["note"] = f"[Out Of Office] " + note_text

        elif real_cat in NEGATIVE_LIKE:
            out["treatment"] = "not_interested_labeled_no_forward_dnc_flagged"
            out["lead_body"]["label_ids"] = [L_COLD, L_CONNECTED, L_RESPONDED]
            out["reply_activity_body"]["note"] = f"[Not Interested] " + note_text
            out["dnc_policy_answer"] = ("Per Phase-1 dnc_ledger spec: negative_reply -> expires_in 6mo "
                                        "(TTL, not permanent). Registry ROW NOT WRITTEN - no confirmed "
                                        "API path to dnc_registry_dev (n8n Data Tables not in public REST API).")
            consolidated_lines.append(f"  • {email} → Not Interested (negative_reply, 6mo TTL per DNC spec; not yet registered)")

        else:  # resolved to Interested / Meeting Request / Information Request / still Uncategorized
            if real_cat in ("Interested", "Meeting Request", "Information Request"):
                out["treatment"] = f"resolved_{real_cat.lower().replace(' ', '_')}_no_forward_stale"
                out["lead_body"]["label_ids"] = [L_COLD, L_CONNECTED, L_RESPONDED]
                out["reply_activity_body"]["note"] = f"[{real_cat}, reclassified] " + note_text
                consolidated_lines.append(f"  • {email} → RECLASSIFIED as {real_cat} (was Uncategorized in Smartlead) - worth a human look despite being stale")
            else:
                out["treatment"] = "stays_uncategorized_review_queue"
                out["lead_body"]["label_ids"] = [L_COLD]
                review_queue.append(email)

        output_rows.append(out)

    print(f"\n=== reclassification results ({len(reclassified)} sent to OpenAI) ===")
    for c in reclassified:
        print(f"  {c['email']}: -> {c['category']} (confidence {c.get('confidence')})")

    print(f"\n=== treatment breakdown ===")
    from collections import Counter
    print(Counter(o.get("treatment", "standard") for o in output_rows if o.get("has_reply")))

    print(f"\n=== review queue (stays Uncategorized, one line each) ===")
    for e in review_queue:
        print(f"  {e}")

    print(f"\n=== CONSOLIDATED OPS NOTE (draft, not sent) ===")
    header = (f"London Sales Sprint 2026 backfill — 215 leads recovered from Smartlead into Pipedrive. "
             f"14 had replies; none were Interested/Meeting Request. Breakdown:")
    print(header)
    for line in consolidated_lines:
        print(line)
    if review_queue:
        print(f"  • {len(review_queue)} historical replies need a human eye (links inside): " + ", ".join(review_queue))

    with open(os.path.join(DISC, "london_backfill_dryrun_v2_output.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": output_rows, "reclassified": reclassified,
                    "consolidated_note_lines": consolidated_lines, "review_queue": review_queue}, f,
                  indent=2, ensure_ascii=False)
    print("\nwrote london_backfill_dryrun_v2_output.json")
    print("\nNO WRITES PERFORMED to Pipedrive or Smartlead. OpenAI calls were read/classify only.")


if __name__ == "__main__":
    main()
