# T1 — weekend HeyReach replies vs Slack notifications (2026-08-08/09)

Read-only diagnosis. No fix deployed. Ground truth = HeyReach's own inbox
(`/inbox/GetConversationsV2`, 345 conversations pulled), not our executions.

Artifacts: `t1_weekend_reply_audit.py` / `.out.log` / `wf1-release-evidence/t1_weekend_reply_audit.json`,
`t1_verify.out.log`.

## Verdict: the channel hypothesis is REAL but explains only 1 of 4 replies

**5 inbound messages from 4 people. All but one processed. Only one Slack alert fired all weekend —
and it posted successfully to `C0B8GCVNR5W` (Nik's ops channel), which Melisa does not watch.**

Fixing the channel alone would have surfaced **exactly one** of the weekend's four replies to her.
There are three independent causes, not one.

| # | who | reply (UTC) | WF-1 | CRM | alert | why Melisa saw nothing |
|---|---|---|---|---|---|---|
| 1 | **Person-c9bb6bd1** | 08-09 03:40 | exec 14509 ✓ | reply activity ✓, **responded label WIPED** | **FIRED**, `ok:true` → `C0B8GCVNR5W` | **channel routing** |
| 2 | **Person-cee23a2f** | 08-08 18:17 | exec 14433 ✓ | labels ✓ activity ✓ | suppressed `already_alerted` | **by design** — 2nd reply; first alerted 08-05 14:10 |
| 3 | **Person-f4bb4705** | 08-09 21:22 (×2) | exec 14659 ✓ | labels ✓ activity ✓ | suppressed `already_alerted` | **by design** — 2nd/3rd reply; first alerted 08-06 22:55 |
| 4 | **Person-0ee7dfb2** | 08-08 02:42 | **NOT PROCESSED** | none | none | **real gap** |

### Cause 1 — channel routing (confirmed)
`WF-1 CONFIG.slack_channel_replies = C0B8GCVNR5W`, same as `slack_channel` and
`slack_channel_ops`. Lucas's alert posted with `ok:true, channel C0B8GCVNR5W, bot B0BFTUR5PJR`.
Melisa's old feed was Zap `274357187` → `C07LTD8UT70`, killed Wednesday. So the notification was
produced and delivered — into a channel she isn't in.

### Cause 2 — alert-gate suppression, and it is NOT a false suppression
Both suppressions are legitimate. Checked every retained execution per person: Aneel has a genuine
`first_alert` at 08-05T14:10 (posted `ok:true`), Eric at 08-06T22:55 (posted `ok:true`). Their
weekend messages were second replies, correctly suppressed by the W1.0.14a "first human reply per
lead" rule. **No false suppression of a first alert was found.**

Worth stating plainly: **routing the channel will not surface repeat replies.** If Melisa expects
to see every reply, the gate is the thing to change, not the channel — that is a separate decision.

### Cause 3 — Person-0ee7dfb2 was never processed (real gap)
HeyReach emits **two** webhook events per reply: `every_message_reply_received` (the actionable
path → M7 processing) and `message_reply_received` (routed to `NoOp` by design). For Vaughn only
the **NoOp variant** ever arrived:

```
2026-08-06T20:40:56Z  exec 13993  connection_request_accepted
2026-08-06T23:31:12Z  exec 14038  message_sent
2026-08-08T02:52:06Z  exec 14302  message_reply_received     -> NoOp, no processing
                      (no every_message_reply_received ever)
```

Lead `ac5dda00`: `responded=False`, activities are invite-sent + message-sent only. His reply —
*"Sorry i missed most of the conference. I'm not in need of SW dev services."* — is a Not
Interested, so the commercial loss is nil, but the event was lost and nothing flagged it. Compare
Lucas, who got **both** variants seconds apart (14509 + 14510). So this is HeyReach delivery being
inconsistent, not our routing.

## NEW FINDING — the responded label is being wiped ~34s after our write

Not part of the original question, found while verifying "processed ✓" rather than assuming it.

```
04:06:49Z  WF-1 M7 Labels Compute : before [1. Cold]  ->  patch [1. Cold, 3. Responded]
04:06:49Z  WF-1 M7 Lead Patch     : patched_label_ids [1. Cold, 3. Responded]   (confirmed in the execution)
04:07:23Z  lead update_time                                                     (+34 s, not us)
NOW        lead labels             : [2. Connected, 1. Cold]   <- Responded GONE, Connected ADDED
```

This is the documented label-clobber signature: an external writer replacing the **absolute** label
set. `+34s` sits exactly inside the `+16–35s` window recorded for Zap **`274318213`** (saved-filter
→ `[Connected, Cold]`, "the prime responded-wiper"). Wednesday's kill covered `274357187` only;
the other four were held.

**Not proven, and I am not asserting it:** Pipedrive exposes no per-update authorship for **leads**
via API (`/v1/leads/{id}/changelog` → 404; only person-level changelog exists). The timing and the
resulting label set match the signature, which is strong but circumstantial.

**Blocked on tooling:** Zapier MCP is disconnected and needs re-authorisation, so I cannot check
whether `274318213` is currently on. That needs either a reconnect or Nik reading it in the UI.

Consequence if confirmed: every LinkedIn reply's `3. Responded` label is being silently reverted,
which corrupts the label-based reporting Melisa reads and would make even a correctly-routed
notification disagree with the CRM. Aneel and Eric currently show `responded=True`, so it is not
hitting every lead — the conditions differ and are not yet established.

## For Melisa (one paragraph, per-reply evidence)

> Over the weekend four people replied on LinkedIn (five messages). Three were processed correctly
> — CRM labels and a "LinkedIn reply" activity were written within seconds: **Person-cee23a2f**
> (Sat 18:17 UTC), **Person-f4bb4705** (Sun 21:22 UTC, two messages) and **Person-c9bb6bd1**
> (Sun 03:40 UTC). The reason you saw no Slack notifications is that our alerts currently post to
> Nik's ops channel, not to #lead-processing — your previous feed was a Zapier zap that was
> switched off on Wednesday as part of the migration. Only one of the four would have notified you
> even so: Aneel and Eric had already been announced when they first replied earlier in the week,
> and the system deliberately alerts only on a lead's *first* reply. The fourth, **Person-0ee7dfb2**
> (Sat 02:42 UTC), was genuinely missed — HeyReach sent us only the non-actionable copy of his
> reply event, so nothing was written; his message was "not in need of SW dev services", so nothing
> commercial was lost, and we are backfilling it. Going forward reply notifications will be routed
> into #lead-processing so they reach you directly. Separately we found that the "Responded" label
> is being reverted on some leads a few seconds after we set it, by a Zapier automation still
> running from the old setup — that is being confirmed with Nik and is why a lead may look
> unresponded in Pipedrive even though the reply was recorded.

## Recommended actions (awaiting your word)

1. **Route reply alerts to `C07LTD8UT70`** per the routing spec — needs Nik's bot invite first,
   then `CONFIG.slack_channel_replies` switch under the deploy-window rule, ops/error alerts
   staying in `C0B8GCVNR5W`. Verification by read: zero non-reply Slack nodes pointing at the team
   channel.
2. **Backfill Person-0ee7dfb2** — responded label + LinkedIn reply activity with the message text.
   Small, same pattern as R1.
3. **Decide the repeat-reply question.** Today only first replies alert. If Melisa needs every
   reply, that is a gate change (`flags.alert_every_reply`), not a channel change.
4. **Resolve the label-wiper with Nik** — is `274318213` still on, and is it intended? Zapier MCP
   needs re-auth before I can check it myself.
5. **Add a HeyReach delivery-gap check** to the daily digest: inbox replies vs WF-1
   `every_message_reply_received` executions, with the delta as an alarm — the same
   truth-vs-processed shape as R3. Vaughn was invisible precisely because nothing compared those
   two.
