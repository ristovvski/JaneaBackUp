"""Direct OpenAI probes for the classifier switch. Reads OPENAI_API_KEY from the environment only.

Never writes the key anywhere, never prints it. Answers, from the live API rather than from docs:
  1. does CONFIG's llm.model actually exist on this account?
  2. does the exact request shape WF-2 sends get accepted?
  3. does `temperature: 0` get rejected by the flagship?
  4. what does one classification cost, in tokens?
  5. does max_completion_tokens truncate the answer (finish_reason == 'length')?
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://api.openai.com/v1"
CATS = ["Interested", "Meeting Request", "Not Interested", "Do Not Contact", "Information Request",
        "Out Of Office", "Wrong Person", "Uncategorizable by Ai", "Sender Originated Bounce",
        "No Longer Working There"]

REPLIES = {
    "Interested-shaped": "Subject: Re: Meet at AI4 in Las Vegas?\n\nBody:\nThanks for reaching out - "
                         "this is relevant for us. Could you send some times next week for a call?",
    "DNC-shaped": "Subject: Re: quick question\n\nBody:\nPlease remove me from your list and do not "
                  "contact me again. Unsubscribe me.",
    "garbage": "Subject: \n\nBody:\n### ~~~ ???",
}


def call(path, body=None, method="GET"):
    key = os.environ["OPENAI_API_KEY"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                headers={"Authorization": f"Bearer {key}",
                                         "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:                                        # noqa: BLE001
            return e.code, {"raw": raw[:400]}


def prompt_for(text):
    return ('Classify this cold-outreach email reply. Return STRICT JSON only, no prose:\n'
            '{"category": one of [' + ", ".join(CATS) + '], "confidence": 0..1, '
            '"is_dnc": boolean, "one_line_summary": string}\n\n' + text)


def chat(model, text, temperature=None, max_tok=400, key_name="max_completion_tokens"):
    body = {"model": model, key_name: max_tok,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system",
                          "content": "You classify cold-outreach email replies. "
                                     "Answer with a single JSON object and nothing else."},
                         {"role": "user", "content": prompt_for(text)}]}
    if temperature is not None:
        body["temperature"] = temperature
    return call("/chat/completions", body, "POST")


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not in environment", file=sys.stderr)
        return 2
    wanted = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.2"

    print("=" * 70)
    print("1. MODEL EXISTENCE")
    st, models = call("/models")
    if st != 200:
        print(f"   GET /models -> {st}: {json.dumps(models)[:300]}")
        return 1
    ids = sorted(m["id"] for m in models.get("data", []))
    print(f"   models visible: {len(ids)}")
    print(f"   '{wanted}' present: {wanted in ids}")
    fam = [m for m in ids if m.startswith(("gpt-5", "gpt-4.1", "o3", "o4"))]
    print(f"   flagship-ish available: {', '.join(fam[:24]) or '(none matched)'}")

    model = wanted if wanted in ids else None
    if model is None:
        print(f"\n   !! '{wanted}' is NOT available on this account - stopping before the")
        print("      classification probes, since they would only measure a fallback.")
        print(f"      candidates to choose from: {', '.join(fam[:24])}")
        return 3

    print("\n2. CLASSIFICATION PROBES (exact WF-2 request shape)")
    total_cost_tokens = 0
    for label, text in REPLIES.items():
        st, r = chat(model, text)
        if st != 200:
            print(f"   {label:20s} -> HTTP {st}: {json.dumps(r)[:220]}")
            continue
        ch = (r.get("choices") or [{}])[0]
        content = (ch.get("message") or {}).get("content") or ""
        fin = ch.get("finish_reason")
        u = r.get("usage") or {}
        total_cost_tokens += u.get("total_tokens") or 0
        try:
            parsed = json.loads(content)
            got = f"{parsed.get('category')} (conf {parsed.get('confidence')}, dnc {parsed.get('is_dnc')})"
        except Exception:                                        # noqa: BLE001
            got = f"UNPARSEABLE: {content[:80]!r}"
        print(f"   {label:20s} -> {got}")
        print(f"   {'':20s}    finish_reason={fin} tokens: prompt={u.get('prompt_tokens')} "
              f"completion={u.get('completion_tokens')} total={u.get('total_tokens')}")
        if fin == "length":
            print(f"   {'':20s}    !! TRUNCATED - max_completion_tokens too small for this model")

    print("\n3. TEMPERATURE PROBE (is temperature:0 rejected?)")
    st, r = chat(model, REPLIES["Interested-shaped"], temperature=0)
    if st == 200:
        print("   temperature:0 ACCEPTED (200) - omitting it is safe either way")
    else:
        msg = ((r.get("error") or {}).get("message") or json.dumps(r))[:200]
        print(f"   temperature:0 REJECTED ({st}): {msg}")
        print("   -> confirms omitting temperature was the right call")

    print("\n4. LEGACY PARAM PROBE (does max_tokens still work?)")
    st, r = chat(model, REPLIES["Interested-shaped"], key_name="max_tokens")
    if st == 200:
        print("   max_tokens ACCEPTED - but max_completion_tokens is the current name; keeping it")
    else:
        msg = ((r.get("error") or {}).get("message") or json.dumps(r))[:200]
        print(f"   max_tokens REJECTED ({st}): {msg}")
        print("   -> confirms the rename matters")

    print("\n5. COST")
    n = len(REPLIES)
    print(f"   {total_cost_tokens} total tokens across {n} classifications "
          f"(~{total_cost_tokens // max(n, 1)} tokens each)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
