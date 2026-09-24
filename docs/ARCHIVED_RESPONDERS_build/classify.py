#!/usr/bin/env python3
"""ARCHIVED RESPONDERS classification pipeline. READ-ONLY (Smartlead/HeyReach GET/search only).
1. Parse the CSV, exclude clearly-fake internal QA/test rows (judged on the PERSON's own name/
   company fields, not campaign name -- campaign names like "TEST2"/"Final TEST" turned out to
   carry real people, verified by real LinkedIn profiles + real replies).
2. Classify each real row: DO NOT CONTACT label -> explicit_opt_out directly. Everything else is a
   reply_dnc candidate, upgraded to explicit_opt_out only if the ACTUAL reply text (read live via
   Smartlead master-inbox search / HeyReach GetConversationsV3) contains real stop-contact language.
   Never guessed -- unreadable/unretrievable replies stay reply_dnc + human_review flag.
3. Identity: email (primary) -> LinkedIn (secondary) -> neither (honest unmatched/enrichment pool).
"""
import csv, json, os, re, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)

SL_KEY = os.environ["SMARTLEAD_API_KEY"]
HR_KEY = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
CTX = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else ssl.create_default_context()
UA = {"User-Agent": "janea-auditor/1.0", "Accept": "application/json"}

FAKE_PATS = ["hr test lead", "test company name", "flip gate", "zz ", "do not distribute", "john doe", "hr test company"]
OPT_OUT_PHRASES = [
    "unsubscribe", "remove me", "remove my", "stop contact", "stop emailing", "stop e-mailing",
    "stop reaching", "do not contact", "don't contact", "no longer contact", "take me off",
    "opt out", "opt-out", "please remove", "stop sending", "not to be contacted",
    "asked not to be contacted", "stop messaging", "stop reaching out", "remove from your list",
    "remove from this list", "take off your list",
]


def strip_html(s):
    return re.sub(r"<[^>]+>", " ", s or "")


QUOTE_MARKERS = [
    re.compile(r"\bOn\s.{5,80}?\swrote:", re.IGNORECASE),
    re.compile(r"-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE),
    re.compile(r"\bFrom:\s*\S+.{0,120}?\bSent:", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bFrom:\s*[\w.\-]+@[\w.\-]+", re.IGNORECASE),
    # German Outlook quote header, found live 2026-08-28 (Person-282ed032, Michal Mraz, Matthias
    # Sonderegger) -- "Von: <name> <email> Datum: ... An: ..." with no English marker at all. Bare
    # "Von:\s" (not requiring an email token right after it) -- the narrower email-anchored version
    # missed "Von:  Sergey Cujba <email>" (a display name sits between the colon and the address).
    re.compile(r"\bVon:\s", re.IGNORECASE),
    re.compile(r"\bGesendet:\s", re.IGNORECASE),
    # French Outlook quote header (Philippe Catirane's signature is French; same client family).
    re.compile(r"\bDe\s*:\s", re.IGNORECASE),
    re.compile(r"\bEnvoy[ée]\s*:\s", re.IGNORECASE),
]


def new_reply_only(text):
    """Real bug found live 2026-08-28: a plain substring scan over the WHOLE reply body catches
    our own outbound courtesy/compliance line ("if you'd prefer not to be contacted further...")
    the moment the lead's email client quotes the original message below their own short reply --
    e.g. Person-9c592fd0's actual reply was an ordinary polite decline, but the quoted original
    underneath it contained our own opt-out courtesy boilerplate, which got matched as if HE said
    it. Truncate at the first quote-boundary marker and scan ONLY the lead's own new text above
    it -- standard top-posting convention, verified against the real false-positive case."""
    earliest = len(text)
    for pat in QUOTE_MARKERS:
        m = pat.search(text)
        if m:
            earliest = min(earliest, m.start())
    return text[:earliest]


def norm_email(e):
    return (e or "").strip().lower()


def norm_li(u):
    u = (u or "").strip()
    if u.lower() in ("no linkedin profile found", "not found", "n/a", ""):
        return ""
    u = u.split("?")[0].rstrip("/")
    return u.lower()


def is_fake_identity(r):
    blob = " ".join([r.get("Lead - Title", ""), r.get("Person - Name", ""), r.get("Person - lh_current_company", "")]).lower()
    return any(p in blob for p in FAKE_PATS)


def has_dnc_label(r):
    return "DO NOT CONTACT" in r.get("Lead - Labels", "")


def sl_search(email, tries=4):
    url = f"https://server.smartlead.ai/api/v1/master-inbox/inbox-replies?api_key={SL_KEY}&fetch_message_history=true"
    body = json.dumps({"offset": 0, "limit": 20, "filters": {"search": email}}).encode()
    for i in range(tries):
        req = urllib.request.Request(url, method="POST", data=body,
                                      headers=dict(UA, **{"Content-Type": "application/json"}))
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read()).get("data") or []
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 + 2 * i); continue
            return {"__error__": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:
            time.sleep(2 + 2 * i)
    return {"__error__": "exhausted retries"}


def hr_search(profile_url, tries=4):
    url = "https://api.heyreach.io/api/public/inbox/GetConversationsV3"
    body = json.dumps({"limit": 5, "filters": {"leadProfileUrl": profile_url}}).encode()
    for i in range(tries):
        req = urllib.request.Request(url, method="POST", data=body,
                                      headers=dict(UA, **{"Content-Type": "application/json", "X-API-KEY": HR_KEY}))
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read()).get("items") or []
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 + 2 * i); continue
            return {"__error__": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception:
            time.sleep(2 + 2 * i)
    return {"__error__": "exhausted retries"}


def check_sl_optout(email):
    """Returns (evidence_text_or_None, error_or_None). Direction is judged by `from` matching the
    searched email, not just type != 'SENT' -- belt-and-suspenders after the quote-contamination
    bug (both checks must agree this is genuinely the lead's own words)."""
    data = sl_search(email)
    if isinstance(data, dict) and "__error__" in data:
        return None, data["__error__"]
    for lead in data:
        for m in lead.get("email_history") or []:
            if m.get("type") == "SENT":
                continue
            if norm_email(m.get("from")) != email:
                continue
            own_text = new_reply_only(strip_html(m.get("email_body") or ""))
            low = own_text.lower()
            for phrase in OPT_OUT_PHRASES:
                if phrase in low:
                    return own_text.strip()[:300], None
    return None, None


def check_hr_optout(profile_url):
    data = hr_search(profile_url)
    if isinstance(data, dict) and "__error__" in data:
        return None, data["__error__"]
    for convo in data:
        for m in convo.get("messages") or []:
            if m.get("sender") != "CORRESPONDENT":
                continue
            own_text = new_reply_only(m.get("body") or "")
            low = own_text.lower()
            for phrase in OPT_OUT_PHRASES:
                if phrase in low:
                    return own_text.strip()[:300], None
    return None, None


def main():
    with open(os.path.join(HERE, "leads-16340280-282.csv"), encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"parsed rows: {len(rows)} (expected ~324)")

    fake = [r for r in rows if is_fake_identity(r)]
    real = [r for r in rows if not is_fake_identity(r)]
    print(f"excluded fake/QA rows: {len(fake)}")
    print(f"real candidate rows: {len(real)}")

    results = []
    n = len(real)
    for i, r in enumerate(real):
        email = norm_email(r.get("Person - Email", ""))
        li = norm_li(r.get("Person - lh_linkedin_profile_url", ""))
        identity_key = email or li or None
        rec = {
            "lead_title": r.get("Lead - Title"), "person_name": r.get("Person - Name"),
            "email": email or None, "linkedin_url": li or None, "identity_key": identity_key,
            "labels": r.get("Lead - Labels"), "owner": r.get("Lead - Owner"),
            "campaign": r.get("Person - lh_campaign_name"), "company": r.get("Person - lh_current_company"),
        }

        if has_dnc_label(r):
            # the ONLY automatic opt_out path -- a literal CSV label, not an inference.
            rec["reason"] = "explicit_opt_out"
            rec["evidence"] = "CSV label: DO NOT CONTACT"
            rec["human_review"] = False
        elif not identity_key:
            rec["reason"] = "reply_dnc"
            rec["evidence"] = "no email/LinkedIn identifier in CSV; reply text unreachable"
            rec["human_review"] = True
        else:
            evidence, error = (check_sl_optout(email) if email else check_hr_optout(li))
            if evidence:
                # NEVER auto-promoted, even on a phrase hit -- found live 2026-08-28 that
                # top-posted email replies routinely quote our OWN outbound courtesy line
                # ("if you'd prefer not to be contacted further...") beneath the person's actual
                # short reply, and a plain substring scan cannot reliably tell "the lead said this"
                # from "the lead's client quoted our own message containing this phrase" across
                # every client/language quote-header format (English "From:"/"On...wrote:", German
                # "Von:"/"Gesendet:", etc. all seen live in this same batch). Every phrase hit is a
                # CANDIDATE for human confirmation, never an automatic classification.
                rec["reason"] = "reply_dnc"
                rec["evidence"] = "reply text checked, CSV label: " + r.get("Lead - Labels", "")
                rec["possible_opt_out_evidence"] = evidence
                rec["human_review"] = True
            elif error:
                rec["reason"] = "reply_dnc"
                rec["evidence"] = "reply text unreadable (" + error + "); CSV label only: " + r.get("Lead - Labels", "")
                rec["human_review"] = True
            else:
                rec["reason"] = "reply_dnc"
                rec["evidence"] = "reply text checked, no stop-contact language found; CSV label: " + r.get("Lead - Labels", "")
                rec["human_review"] = False
        results.append(rec)

        if (i + 1) % 20 == 0 or i == n - 1:
            print(f"  {i+1}/{n} processed", flush=True)
            with open(os.path.join(HERE, "classification_progress.json"), "w", encoding="utf-8") as f:
                json.dump(results, f, indent=1, ensure_ascii=False)
        time.sleep(0.25)

    excluded_records = [{"lead_title": r.get("Lead - Title"), "person_name": r.get("Person - Name"),
                         "company": r.get("Person - lh_current_company"), "email": r.get("Person - Email"),
                         "campaign": r.get("Person - lh_campaign_name")} for r in fake]

    out = {
        "total_parsed": len(rows), "expected": 324,
        "excluded_fake_qa_count": len(fake), "excluded_fake_qa": excluded_records,
        "real_candidate_count": len(real),
        "opt_out_count": sum(1 for r in results if r["reason"] == "explicit_opt_out"),
        "reply_dnc_count": sum(1 for r in results if r["reason"] == "reply_dnc"),
        "human_review_count": sum(1 for r in results if r.get("human_review")),
        "possible_opt_out_candidate_count": sum(1 for r in results if "possible_opt_out_evidence" in r),
        "unmatched_no_identifier_count": sum(1 for r in results if r["identity_key"] is None),
        "rows": results,
    }
    with open(os.path.join(HERE, "classification_final.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print()
    print(json.dumps({k: v for k, v in out.items() if k != "rows" and k != "excluded_fake_qa"}, indent=2))
    print("wrote classification_final.json")


if __name__ == "__main__":
    main()
