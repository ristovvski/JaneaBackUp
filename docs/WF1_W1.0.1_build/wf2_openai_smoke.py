"""OpenAI smoke harness for the classifier path (Phase D, provider switch).

I hold no OpenAI key - Nik's lives in the n8n credential "OpenAI API" - so every call must go through
n8n. This builds a THROWAWAY workflow that calls OpenAI with that credential and returns the raw
response, so the request/response contract is verified against the live API rather than against docs.

Deliberately NOT a generic proxy: the request bodies are baked in and selected by index, so the temp
webhook cannot be used to send arbitrary prompts with someone else's key. Delete it after use.

Probes:
  0  GET  /v1/models              - does `gpt-5.2` actually exist on this account?
  1  POST Interested-shaped reply - expect category Interested, confidence high
  2  POST DNC-shaped reply        - expect Do Not Contact + is_dnc true
  3  POST garbage                 - expect the guardrail path (unparseable / unknown -> Uncategorized)
  4  POST with temperature: 0     - does the flagship reject it? (the param question, answered live)

Each response is returned whole, so usage tokens and finish_reason are observable: finish_reason
'length' would mean max_completion_tokens truncates the JSON on a reasoning model, which shows up as
"every classification is Uncategorized" rather than as an error.

Usage:
  python wf2_openai_smoke.py build  <cred_id> out.json
  # then deploy out.json, POST {"probe": N} to the webhook, read the execution, delete the workflow
"""
import argparse
import json
import sys
from pathlib import Path

WEBHOOK_PATH = "openai-smoke-7c1f"
NAME = "TMP OpenAI smoke (DELETE AFTER)"

CATS = ["Interested", "Meeting Request", "Not Interested", "Do Not Contact", "Information Request",
        "Out Of Office", "Wrong Person", "Uncategorizable by Ai", "Sender Originated Bounce",
        "No Longer Working There"]

REPLIES = {
    1: ("Interested-shaped",
        "Subject: Re: Meet at AI4 in Las Vegas?\n\nBody:\nThanks for reaching out - this is "
        "relevant for us. Could you send over some times next week for a short call?"),
    2: ("DNC-shaped",
        "Subject: Re: quick question\n\nBody:\nPlease remove me from your list and do not contact "
        "me again. Unsubscribe me."),
    3: ("garbage",
        "Subject: \n\nBody:\n███ ~~~ ???  "),
}


def prompt_for(text):
    return ('Classify this cold-outreach email reply. Return STRICT JSON only, no prose:\n'
            '{"category": one of [' + ", ".join(CATS) + '], "confidence": 0..1, '
            '"is_dnc": boolean, "one_line_summary": string}\n\n' + text)


def chat_body(text, model="gpt-5.2", temperature=None):
    b = {"model": model,
         "max_completion_tokens": 400,
         "response_format": {"type": "json_object"},
         "messages": [
             {"role": "system", "content": "You classify cold-outreach email replies. "
                                           "Answer with a single JSON object and nothing else."},
             {"role": "user", "content": prompt_for(text)}]}
    if temperature is not None:
        b["temperature"] = temperature
    return b


PICK = """
// bodies are baked in; the webhook only chooses an index, so this cannot be used as an open proxy
const probe = Number(($('Webhook').item.json.body || {}).probe ?? 1);
const SPECS = %s;
const spec = SPECS[String(probe)] || SPECS['1'];
return [{ json: { __probe: probe, __label: spec.label, __is_models: probe === 0,
                  __body: spec.body ?? null } }];
"""


def build(cred_id):
    specs = {"0": {"label": "GET /v1/models"}}
    for i, (label, text) in REPLIES.items():
        specs[str(i)] = {"label": label, "body": chat_body(text)}
    specs["4"] = {"label": "temperature:0 probe", "body": chat_body(REPLIES[1][1], temperature=0)}

    cred = {"httpHeaderAuth": {"id": cred_id, "name": "OpenAI API"}}
    auth = {"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"}
    hdr = {"parameters": [{"name": "Content-Type", "value": "application/json"}]}

    nodes = [
        {"parameters": {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "lastNode",
                        "options": {}},
         "id": "s1", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [0, 0], "webhookId": "s1"},
        {"parameters": {"jsCode": PICK % json.dumps(specs, ensure_ascii=False)},
         "id": "s2", "name": "Pick Probe", "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [220, 0]},
        {"parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                                   "typeValidation": "strict", "version": 1},
                                       "conditions": [{"id": "sc",
                                                       "leftValue": "={{ $json.__is_models === true }}",
                                                       "rightValue": True,
                                                       "operator": {"type": "boolean",
                                                                    "operation": "true",
                                                                    "singleValue": True}}],
                                       "combinator": "and"}, "options": {}},
         "id": "s3", "name": "IF Models", "type": "n8n-nodes-base.if", "typeVersion": 2,
         "position": [420, 0]},
        {"parameters": dict({"method": "GET", "url": "https://api.openai.com/v1/models",
                             "sendHeaders": True, "headerParameters": hdr, "options": {}}, **auth),
         "id": "s4", "name": "Models", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": [620, -120], "credentials": cred, "onError": "continueRegularOutput"},
        {"parameters": dict({"method": "POST", "url": "https://api.openai.com/v1/chat/completions",
                             "sendHeaders": True, "headerParameters": hdr, "options": {},
                             "sendBody": True, "specifyBody": "json",
                             "jsonBody": "={{ JSON.stringify($json.__body) }}"}, **auth),
         "id": "s5", "name": "Chat", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": [620, 120], "credentials": cred, "onError": "continueRegularOutput"},
    ]
    conns = {
        "Webhook": {"main": [[{"node": "Pick Probe", "type": "main", "index": 0}]]},
        "Pick Probe": {"main": [[{"node": "IF Models", "type": "main", "index": 0}]]},
        "IF Models": {"main": [[{"node": "Models", "type": "main", "index": 0}],
                               [{"node": "Chat", "type": "main", "index": 0}]]},
    }
    return {"name": NAME, "nodes": nodes, "connections": conns,
            "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all",
                         "saveDataErrorExecution": "all"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("cred_id")
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    wf = build(a.cred_id)
    assert a.cred_id and a.cred_id != "TBD", "a real credential id is required"
    a.out.write_bytes((json.dumps(wf, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"smoke workflow -> {a.out} ({len(wf['nodes'])} nodes), webhook path /{WEBHOOK_PATH}")
    print("probes: 0=models  1=Interested  2=DNC  3=garbage  4=temperature:0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
