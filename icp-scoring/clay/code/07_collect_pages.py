# 07 Collect page text
#
# The scrape node runs once per URL, so its output is a list of four results in
# whatever envelope Clay's list mode puts them. This node flattens that into one
# labelled block of text and one explicit reachability line, so the summarizing
# agent downstream receives a string and never has to reason about Clay's list
# envelope.
#
# It also caps the text. Four full page bodies can run to hundreds of kilobytes;
# an uncapped prompt is a cost and latency risk with no classification value,
# because what the rubric needs from a website is what the company says it does,
# which is near the top of each page.

MAX_CHARS_PER_PAGE = 6000
PAGE_LABELS = ["homepage", "/about", "/product", "/careers"]

# The four URLs are constructed from the domain, not discovered from the site's
# own links, so a company that files its about page under /company/about serves
# a 404 at /about. A soft 404 returns 200 with the site chrome and a "not
# found" line, which would otherwise be reported as a reachable page and fed to
# the summarizer as if it said something. These are the phrases that give it
# away; a page matching one is reported unreachable, which is the truth.
NOT_FOUND_MARKERS = (
    "page can't be found", "page can\u2019t be found", "page cannot be found",
    "page not found", "404 not found", "error 404", "nothing was found at this location",
    "the requested url was not found", "we can't find that page",
    "this page doesn't exist", "this page does not exist",
)


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # Clay list-mode envelopes seen so far nest under one of these keys;
        # anything else falls through to "no pages", which is reported honestly
        # rather than guessed at.
        for key in ("results", "entries", "items", "output"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
    return []


def _looks_not_found(text):
    head = text[:1500].lower()
    return any(marker in head for marker in NOT_FOUND_MARKERS)


def _body_of(entry):
    """Pull the scraped text out of one list entry, whatever it is wrapped in."""
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return None
    scope = entry
    for key in ("result", "output", "data"):
        inner = scope.get(key)
        if isinstance(inner, dict):
            scope = inner
            break
    for key in ("bodyText", "description", "title"):
        value = scope.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def handler(context):
    entries = _as_list(context.get_input("pages")) or _as_list(context.get_input("pages_results"))

    blocks = []
    reachable = []
    unreachable = []

    for index, label in enumerate(PAGE_LABELS):
        entry = entries[index] if index < len(entries) else None
        body = _body_of(entry)
        if body and body.strip() and not _looks_not_found(body):
            reachable.append(label)
            blocks.append("### %s\n%s" % (label, body.strip()[:MAX_CHARS_PER_PAGE]))
        else:
            unreachable.append(label)

    return {
        "page_text": "\n\n".join(blocks) if blocks else None,
        "pages_reachable": ", ".join(reachable) if reachable else "none",
        "pages_unreachable": ", ".join(unreachable) if unreachable else "none",
        "any_page_reachable": bool(blocks),
    }
