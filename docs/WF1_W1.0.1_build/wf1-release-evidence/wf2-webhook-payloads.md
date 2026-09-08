# Smartlead webhook payloads - RECOVERED REAL SAMPLES (closes the A3 "UNVERIFIED" gap)

Source: the `metadata.designer.samples` blocks inside the two Make blueprints I recovered earlier.
These are Smartlead's own payloads as captured by Make's webhook modules - not my assumptions.
Phase A listed payload shapes as **UNVERIFIED**; this closes that, and it immediately exposed B15.

## EMAIL_SENT (real, campaign 2876818)

```
app_url                "https://app.smartlead.ai/app/master-inbox?leadMap=2638146185"
ui_master_inbox_link   same value
campaign_id            2876818
campaign_name          "[Trigger-based Campaign] Newly Hired Heads of AI"
campaign_status        "ACTIVE"
event_type             "EMAIL_SENT"
event_timestamp        "2026-01-28T14:44:39.932+00:00"
time_sent              same
from_email             "pii-d1f235df@example.invalid"     <- OUR sending inbox
to_email               "pii-070ffb72@example.invalid"
to_name                "Person-d03bd861"
sequence_number        1
sl_email_lead_id       "3244145308"        <- NOT `lead_id`
sl_email_lead_map_id   2638146185          <- the UI deep-link key
stats_id               "d704677d-7f9f-42c6-b4f9-99eafee478b5"
message_id             "<pii-dc182017@example.invalid>"
subject / custom_subject / sent_message{html} / sent_message_body / description
secret_key             <shared secret>
webhook_id             151526
```

**No `lead_data` at all.** Company, website, LinkedIn, location and title are simply absent on the
SENT event, which is why the enrichment call exists - and why B16 (enrichment discarded) turned
into a hard failure rather than a cosmetic gap.

## LEAD_CATEGORY_UPDATED (Smartlead's generic doc sample, campaign 10 "test")

```
event_type      "LEAD_CATEGORY_UPDATED"
lead_id         100                      <- this branch DOES use lead_id
lead_data       { email, website, category{...}, ... }
last_reply      { time, type, email_body, subject, stats_id, message_id }
history         [ { time, type, subject, stats_id, email_body, ... } ]
lead_category   { new_id, old_id, new_name, old_name }
app_url         master-inbox?leadMap=123
```

Note: `from_email` on this sample is the LEAD's address, not our inbox. It is Smartlead's synthetic
doc sample, so it may not reflect a real `EMAIL_REPLIED`. **Open item:** if real replies do not
carry our sending inbox, `sender_inbox` -> owner resolution degrades. `Ops Warn Unknown Inbox` is
the fail-safe and will surface it during shadow - do not "fix" it on a guess before then.

## B15 - what this changed in the code

`sl_lead_id` picked `b.lead_id`/`ld.id` only, so on a real EMAIL_SENT it was **null**. The dedupe
key is `campaign_id + sl_lead_id`, so every first-email in a campaign collapsed onto ONE key and
all but the first would have been discarded as duplicates. Now:
`pick(b.lead_id, b.sl_email_lead_id, ld.id, b.sl_lead_id)`, plus `sl_lead_map_id` and `sl_app_url`
captured, plus `last_reply.*` aliases for subject/body/stats/message id. Locked by PL1-PL5.

## Also worth a decision (not actioned)

The payload carries `secret_key`. WF-2's webhook URL is public and currently accepts any POST.
Validating `secret_key` against a credential would stop spoofed events from writing to the CRM.
Not in scope for this addendum - raising it for Nik.

---

# D - Smartlead deep link: DISCOVERY RESULT (awaiting click-proof)

**No construction needed in the normal case.** The webhook payload already contains the finished
link, in two fields: `app_url` and `ui_master_inbox_link`. That is strictly better than any format
I could infer, and it is what Make's own Slack messages used.

Format, when we must build it ourselves:

```
https://app.smartlead.ai/app/master-inbox?leadMap=<campaign_lead_map_id>
```

The key is the **campaign-lead map id** (`sl_email_lead_map_id` in the webhook,
`campaign_lead_map_id` in `GET /campaigns/{id}/leads`) - NOT the lead id and NOT the campaign id.

## Links for click-verification (real data, campaign 3565502)

| lead | link |
|---|---|
| Person-6fe1a561 <pii-9569b1b9@example.invalid> | https://app.smartlead.ai/app/master-inbox?leadMap=3318190611 |
| Person-e44b6aa0 <pii-50a6073f@example.invalid> | https://app.smartlead.ai/app/master-inbox?leadMap=3318190612 |

The first is the one to click. Two are given so you can confirm they open *different* conversations
rather than a generic inbox - a link that ignores the parameter would look like a success on one.

**The hypothesis being tested:** that `campaign_lead_map_id` from the REST API is the same
identifier as the webhook's `sl_email_lead_map_id`. The format itself is already evidenced; this
equivalence is not, which is why the link is not wired yet.

Once confirmed, wiring is small and additive: `Normalize` already captures both `sl_app_url` and
`sl_lead_map_id`, so the alert gains
`sl_app_url || (base + '?leadMap=' + sl_lead_map_id)` as an "Open in Smartlead" link next to
"Open lead", with the same LK-group assertions (no id -> no link).
