# 10 Read website summary
#
# Unwraps the OpenAI chat-completions reply from the tool node above. One
# concern: get the text out, or report honestly that there is none.
#
# A failed or empty call yields null, never a placeholder string. The
# classifier preamble tells the model to read a null fact as "enrichment did
# not find it"; a string saying "no summary available" would be read as content.

import json

MAX_CHARS = 4000


def _unwrap(raw):
    """The assistant message from a chat-completions response, whatever it is wrapped in."""
    body = raw
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (TypeError, ValueError):
            return None
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) and content.strip() else None


def handler(context):
    for key in ("response", "response_body", "response_results"):
        raw = context.get_input(key)
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        text = _unwrap(raw)
        if text:
            return {"website_summary": text.strip()[:MAX_CHARS], "summary_ok": True}
    return {"website_summary": None, "summary_ok": False}
