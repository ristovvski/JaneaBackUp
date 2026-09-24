#!/usr/bin/env python3
"""READ-ONLY: locate 'Event name' and 'Marketing Hypothesis' custom fields on BOTH the lead and
person objects, fresh (not cached from earlier discovery). Get id/key, field_type, options."""
import os, json, ssl
import urllib.request, urllib.parse

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None


def pd(path, params=None):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
    with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
        return json.load(x)


def find_matches(fields, terms):
    out = []
    for f in fields:
        name = (f.get("name") or "").lower()
        if any(t in name for t in terms):
            out.append(f)
    return out


TERMS = ["event name", "marketing hypothesis", "hypothesis", "event"]

for entity, ep in (("lead", "/leadFields"), ("person", "/personFields")):
    data = pd(ep, {"start": 0, "limit": 500})
    fields = data.get("data") or []
    print(f"\n=== {entity.upper()} fields matching {TERMS} ===")
    for f in find_matches(fields, TERMS):
        print(json.dumps({
            "key": f.get("key"), "name": f.get("name"), "field_type": f.get("field_type"),
            "options": f.get("options"), "add_visible_flag": f.get("add_visible_flag"),
            "edit_flag": f.get("edit_flag"), "mandatory_flag": f.get("mandatory_flag"),
        }, indent=2, ensure_ascii=False))
