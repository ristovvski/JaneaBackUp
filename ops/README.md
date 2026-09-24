# ops

Operational scripts for the live GTM stack. Read-only unless a flag says otherwise.

## `heyreach_webhook_scope.mjs`

Keeps the HeyReach webhook subscriptions scoped to campaigns.

```
node ops/heyreach_webhook_scope.mjs            # report
node ops/heyreach_webhook_scope.mjs --apply    # add missing campaigns
```

**Run it after creating a campaign in HeyReach.** A campaign that is not in a
subscription's `campaignIds` does not deliver events at all, and nothing warns
you — the campaign simply never reaches the CRM.

### What went wrong, so the next person does not undo it

A HeyReach subscription with an **empty** `campaignIds` does not mean "no
campaigns". It means **everything**, including replies in a connected account's
private LinkedIn inbox, which carry no campaign at all.

All six of our subscriptions were created that way. Between **12 July and
22 September 2026** the `EVERY_MESSAGE_REPLY_RECEIVED` subscription delivered
**390 private replies** into Pipedrive as activities, across **201 people who
were in no campaign** — including personal conversations of Noah, Mario, Rune
and Sergey, whose LinkedIn accounts are connected as campaign senders.

It surfaced when Noah noticed his own private threads appearing in Pipedrive.

### The two layers now in place

1. **HeyReach**: all six subscriptions scoped to the campaign list. This is what
   stops private message content entering our infrastructure at all — before
   this, it was landing in n8n execution logs.
2. **n8n**: `WF-1 HeyReach Receiver` → node `Normalize` drops any event that
   arrives with no campaign, before any enrichment, patch, label, activity or
   Slack alert. It does not depend on the id list, so it also covers a campaign
   this script has not been run for.

Layer 1 can go stale (a new campaign). Layer 2 cannot, but only sees what
HeyReach chooses to deliver. Neither replaces the other.

### Do not "simplify" by emptying campaignIds

Emptying the list to avoid maintenance re-opens exactly the leak above. If the
maintenance is the problem, the fix is to run this script from a schedule, not
to widen the subscriptions.

### What this does not cover

HeyReach still **stores** the full LinkedIn inbox of every connected account —
901 conversations as of 22 September, with message text. Scoping the webhooks
stops delivery to us; it does not stop HeyReach holding them. Limiting that is a
vendor-side question (a "track all conversations" setting in their UI, or an
account-level request), not something this script can reach.
