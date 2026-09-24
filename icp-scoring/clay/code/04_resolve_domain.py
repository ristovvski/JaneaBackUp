# 04 Resolve domain for enrichment
#
# Every remaining provider in the waterfall is keyed on a DOMAIN: scrape-website
# needs a URL, Apollo takes `domain`, all three PredictLeads actions take
# `unparsedDomain`. A request that arrived with only a LinkedIn URL therefore
# cannot reach any of them until the company profile lookup (node 03) hands back
# the company's website.
#
# Fill-if-empty only. clay_table_spec.md section 4: "never overwrite a value n8n
# sent, because n8n's value came from Pipedrive and Pipedrive is where a human
# typed it." A provider's domain is used ONLY when the webhook's was null.

PAGE_PATHS = ["", "about", "product", "careers"]


def _blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def _root_domain(value):
    """Reduce a provider-returned URL to a bare host.

    Deliberately minimal. Real normalization (public-suffix handling, IP
    literals, the non-company-host blocklist) lives in engine/normalize.mjs and
    runs in n8n before the request ever reaches Clay; duplicating it here would
    create a second definition of "domain" that could drift from the first.
    This only tidies the shape a provider happens to return — "http://akuvo.com/"
    -> "akuvo.com" — and it is never applied to a value n8n sent.
    """
    if _blank(value):
        return None
    text = str(value).strip().lower()
    for prefix in ("http://", "https://", "//"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    for separator in ("/", "?", "#"):
        text = text.split(separator)[0]
    text = text.split(":")[0].strip(".")
    if text.startswith("www."):
        text = text[4:]
    if "." not in text or " " in text:
        return None
    return text or None


def handler(context):
    from_webhook = context.get_input("domain")
    domain = None if _blank(from_webhook) else from_webhook
    domain_source = "pipedrive" if domain else None

    if domain is None:
        for key in ("profile_domain", "profile_website"):
            candidate = _root_domain(context.get_input(key))
            if candidate:
                domain = candidate
                domain_source = "company_profile_lookup"
                break

    return {
        "domain_for_enrichment": domain,
        "domain_source": domain_source,
        "has_domain": bool(domain),
        # One-element list for the same reason as node 01's: every
        # domain-keyed provider node runs in list mode so that its failure is
        # survivable. See clay/WORKFLOW.md.
        "domain_list": [domain] if domain else [],
        # The four pages clay_table_spec.md section 5 names: /careers is where
        # capacity pressure shows and /product is where software-native vs
        # software-dependent shows, so neither is optional.
        "page_urls": [
            "https://%s/%s" % (domain, path) if path else "https://%s/" % domain
            for path in PAGE_PATHS
        ] if domain else [],
    }
