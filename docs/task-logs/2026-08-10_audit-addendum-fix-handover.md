# Audit addendum — fix handover payloads + three corrections to the dispatch

Auditor session, still read-only. Nothing here was applied. Companion to
`2026-08-10_independent-audit-pipedrive-smartlead.md`. Machine-readable payloads:
`scratchpad/a8_handover.json` (repairs + SENT bounds), `a5_numbers.json`, `a6_mech.json`.

---

## CORRECTION 1 — Marine is an out-of-office auto-reply. Do not backfill her as a reply.

The lost event's body, verbatim from exec 14966's `Normalize` output:

> "Thank you for reaching out. I am currently **out of the office until August 17** with limited
> access to email. I will review your message upon my return." — Person-d05f9f74, Airgas FIT PMO

Applying the R1-style recovery as dispatched — category, `3. Responded`, activity, forward,
**Handover rules** — would put a false positive in Melisa's queue and mislabel a cold lead as
engaged. Recommended handling instead: log the auto-reply, suppress until 2026-08-17, leave
`da6fce30` at `['1. Cold']`, **no Handover, no `3. Responded`, no `4. Positive Reply`**.

Two consequences worth naming:

- **P0-1's severity does not change.** The crash destroys *every* reply after 15:10:44Z; that this
  particular one happened to be an autoresponder is luck, not mitigation. The next one may be a
  meeting request.
- **A separate gap is now visible:** WF-2 has no auto-reply/OOO suppression, and
  `forward_on_uncategorized: true` with `forwardable_categories` not including any OOO class means an
  uncategorised autoresponder is forwarded by default. Had the node not crashed, this OOO would very
  likely have been forwarded and labelled. Add "OOO/auto-reply detection" to the open list.

**Forward routing, for the record:** sender inbox `pii-cbfdf4fb@example.invalid` → `forward_inbox_map`
→ **Mario** → `mario@janeasystems.com`. Not Melisa. (`forward_inbox_map` holds 710 entries;
`forward_default` = `melisa@janeasystems.com` is the fallback and was not what would have applied.)

## CORRECTION 2 — the SENT number has grown; sends are still running

The audit's "176 SENT today" was the 15:45Z snapshot. Re-read at ~15:57Z from
`/campaigns/{id}/statistics`, paginated past the blind page:

| campaign | total rows | WF-2S saw (oldest) | newest row it saw | **never seen** | span of never-seen | of which today |
|---|---|---|---|---|---|---|
| 3686181 | 806 | 500 | 2026-07-31T19:09:28Z | **306** | 2026-07-31T17:43:14Z → 2026-08-10T15:54:50Z | 66 |
| 3686184 | 633 | 500 | 2026-08-04T19:19:13Z | **133** | 2026-08-04T14:07:32Z → 2026-08-10T15:31:08Z | 44 |
| 3686187 | 662 | 500 | 2026-08-06T16:56:56Z | **162** | 2026-08-04T14:07:27Z → 2026-08-10T15:54:28Z | 66 |
| 3686193 | 716 | 500 | 2026-08-04T19:21:04Z | **216** | 2026-08-04T14:07:42Z → 2026-08-10T15:54:37Z | 66 |
| 3756410 | 16 | 16 | 2026-08-04T21:41:18Z | 0 | — | 0 |

**817 SENT rows have never been seen, 242 of them today** — and rows are still arriving (15:54:50Z).
These are the exact backfill bounds. Note the spans start *before* each campaign's page-500 boundary,
so a backfill keyed on "everything after the newest row WF-2S saw" is safe and slightly
over-inclusive; WF-2's dedupe absorbs the overlap.

## CORRECTION 3 — Zapier: 4 ON, and their configuration explains the damage pattern

Read via Zapier Manager *Find Zap* (read-only; no toggle called):

| zap | title | state | last paused |
|---|---|---|---|
| `274357463` | Add **"Connected"** label to lead if LH response is received | **ON** | 2026-07-17T13:45:38Z |
| `274354645` | Add **"Cold"** label to lead if LH connection request is sent | **ON** | 2026-07-17T13:45:40Z |
| `274318213` | Make.com replacement — LH connection already exists → **connected** tag | **ON** | 2026-07-17T13:45:24Z |
| `274316027` | Make.com replacement — LH connection accepted → **connected** tag | **ON** | 2026-07-17T13:45:15Z |
| `274357187` | Add **"Responded"** label to lead if LH response is received | **OFF** | **2026-08-05T11:28:42Z** by `mykyta@janeasystems.com` |

Your "4 remaining" is exact, and **all four write lead labels** — Connected ×3, Cold ×1 — so all four
meet your own kill criterion.

**New corroboration of P0-3, and the reason the damage only became visible this week:** the four
surviving zaps collectively write exactly `{Cold, Connected}` — which is precisely the terminal label
set of all 11 wipes. The `Responded` zap was switched off on **2026-08-05T11:28:42Z**, and the first
wipe in evidence is **2026-08-07T09:38:51Z**. Before Aug 5 a wipe was partly self-healing (the
Responded zap re-added the label seconds later); after Aug 5 the overwrite is permanent. That is
independent confirmation of the mechanism from the Zapier side.

*Bound:* Find Zap returns title/state only. The literal `label_ids` each Update Lead step writes is
still unread (opening a step puts the Zap into a draft state), so "writes lead labels" rests on the
titles plus the observed terminal set, not on the step config.

---

## P0-1 — the exact fix, recovered from your own pre-deploy backup

`wf2_backup_before_gatefix_1786374640.json` (the 15:10:40Z snapshot) holds the working source.
The gate-fix edit deleted lines 24–26 **and the head of line 27**, which is where `alert_text` was
declared — leaving 28–29 dangling.

**Was (working, 15:10:40Z):**
```js
24| const cat = (() => { try { return $('Classify Parse').item.json.__category || null; }
25|                      catch (e) { return null; } })();
26| const catTxt = cat ? (' · *' + esc(cat) + '*') : '';
27| const alert_text = '💬 ' + who + paren + catTxt + ' · ' + esc(n.campaign_name)
28|   + ' · via ' + esc(n.sender_inbox) + ' — ' + link + slLink
29|   + ' · ✉️ ' + esc(n.lead.email);
```

**Is now (broken, 45637e70):**
```js
24|   + ' · via ' + esc(n.sender_inbox) + ' — ' + link + slLink   // ← orphaned expression statement
25|   + ' · ✉️ ' + esc(n.lead.email);
26| return [{ json: { ...$json, alert_text, ... } }];              // ← ReferenceError
```

**Minimal fix preserving the intended change (category line stays removed) — one line restored:**
```js
const alert_text = '💬 ' + who + paren + ' · ' + esc(n.campaign_name)
  + ' · via ' + esc(n.sender_inbox) + ' — ' + link + slLink
  + ' · ✉️ ' + esc(n.lead.email);
```

Two things the statics must cover, because this class shipped clean twice today:
1. **A syntax check is not enough** — lines 24–25 are *valid* JS, which is exactly why the deploy
   passed and the runtime died. The static must execute the node body and assert `alert_text` is a
   non-empty string.
2. **`Body Reply Alert` has no `onError`**, so it kills the execution, while its sibling
   `Reply Alert` swallows errors and returns `{"error":"invalid syntax"}` as output. Pick one policy
   deliberately; today the same defect class produced two different failure modes.

## P0-1b — agreed, and here is the precise line

`Dedupe`, line 21: `if (!duplicate) store.wf2_seen[key] = nowSec;` — the claim is written before any
work. Move it to after the terminal success node (WF-2R's claim-after-success shape). Until then,
every crashed event is permanently unreplayable, because `dedupe_max_age_sec` (48 h) ≥ WF-2R's
`lookback_minutes` (48 h).

## P0-3 — repair payloads, all 11 leads, verified still broken at 15:56Z

Union semantics (restore what was lost, never remove what exists). Full JSON with ready PATCH bodies
in `a8_handover.json`; `still_missing_now` is 11 of 11.

| lead | person | restore to | lost |
|---|---|---|---|
| `29413600-cf9d-11f0-904d-6781f0117a6d` | 61664 | Cold, Connected, **Responded, Positive Reply**, AUTOMATED LEAD NURTURING | 3 labels |
| `1574a9a0-6868-11f0-8e09-5f5e184f61a9` | 48704 | Cold, Connected, **Responded, Positive Reply**, AUTOMATED LEAD NURTURING | 3 |
| `da28dee0-a9e2-11f0-92f0-7987f138dd72` | 57950 | Cold, Connected, **Responded, Positive Reply**, AUTOMATED LEAD NURTURING | 3 |
| `c08d6860-d071-11f0-b21c-a7ca2e319bc7` | 61928 | Cold, Connected, **Responded, Positive Reply**, AUTOMATED LEAD NURTURING | 3 |
| `73f7e160-b735-11f0-9bac-b1a3fb5fe3e1` | 59899 | Cold, Connected, AUTOMATED LEAD NURTURING | 1 |
| `fd137710-8af4-11f0-a159-1d80e94b4a09` | 54622 | Cold, Connected, AUTOMATED LEAD NURTURING | 1 |
| `122445c0-aa09-11f0-92f0-7987f138dd72` | 58431 | Cold, Connected, **Responded** | 1 (Aug 9) |
| `5c898700-11ac-11f1-94be-1fa39739e256` | 67892 | Cold, Connected, AUTOMATED LEAD NURTURING | 1 (Aug 7) |
| `f80e30a0-b733-11f0-bd8d-cba7c4561fda` | 59894 | Cold, Connected, AUTOMATED LEAD NURTURING | 1 (Aug 7) |
| `c03c07c0-c141-11f0-818b-e1e80e99d2cb` | 60622 | Cold, Connected, AUTOMATED LEAD NURTURING | 1 (Aug 7) |
| `5c9b9980-c149-11f0-9c2a-916ad64d4a80` | 60645 | Cold, Connected, AUTOMATED LEAD NURTURING | 1 (Aug 7) |

**Ordering matters: kill the zaps first, repair second.** Repairing while the zaps are live means a
person-update on any of these 11 re-triggers the overwrite. Also expect the repair itself to fire
Melisa's `3. Responded` → Handover automation on the 5 leads regaining Responded (that automation is
what produced activity 43974) — decide whether that is wanted before patching.

Note Malachi (`7f91e3b0`) and Lucas (`d01a4d90`) are **not** in this list: their leads postdate my
Aug-5 baseline, so my sweep cannot see them. They still need repair from the earlier session's
evidence. **≥11 is a floor.**

## P0-2 — the auditor's recommendation

You asked which. **Neither tonight.** Recommended order:

1. **Pause the four Ai4 campaigns now** (3686181, 3686184, 3686187, 3686193). It stops the bleeding
   with zero deploy risk and zero reintroduced corruption — 242 sends today already have no CRM
   record and rows were still arriving at 15:54Z.
2. **Patch WF-2S tomorrow** onto `leads-statistics` `history[]` `type=SENT`. That surface is proven
   twice over: WF-2R uses it in production, and this audit walked all 117 campaigns on it with
   `hasMore` terminating cleanly and zero duplicate lead ids. Ship it with a live post-deploy
   verification, not statics alone.
3. **Do not re-enable Make 8557031.** It writes leads with an empty Campaign field, which breaks the
   W1.0.11 lead-per-campaign matching and duplicates leads — that is trading one corruption for
   another, at 242 records/day, and it undoes the thing the flip was for.

If sends must keep running tonight, then the honest framing is: you are choosing to accumulate
un-recorded sends (backfillable, bounds above) rather than to inject duplicate leads
(not cleanly reversible). Accumulating is the recoverable failure. That is the auditor's read; the
call is the fix owner's.

## Finding 4 — agreed

Replace the global page with a person-scoped read: `GET /v1/leads?person_id={id}` (already used
elsewhere in this audit, returns that person's leads directly), then match on the campaign field with
the existing title-prefix fallback. Current coverage is 500 of 57,602 leads (0.87%), 6.25 days deep,
and it already bit the one organic reply of the day: person 83623's only lead was created 2026-07-21
and came back `__no_lead: true`.

## The two questions you asked

**`slack_channel_replies_at_flip` — vestigial, not pending.** In WF-2 it is defined in CONFIG
(`C07LTD8UT70`) and **read by no node**; `slack_channel_replies` (`C0B8GCVNR5W`, identical to
`slack_channel_ops`) is what `Reply Alert` and `Nurture Alert` actually consume. So email reply alerts
and nurture alerts both land in Nik's ops channel; the flip-time switch was never wired. WF-1 is
different and matches its claim: its `slack_channel_replies` **is** `C07LTD8UT70` and is consumed by
`M7 Critical Slack` — though WF-1 ran zero executions today, so it is unexercised, not proven.

**Flip live-since = `2026-08-10T11:45:14.041Z`** — WF-2's own config stamp, echoed in every
write-mode alarm on the Slack wire. The 11:31:01Z backup and exec 14853 at 11:31:09Z are the deploy
and readback probe. "12:31Z" appears nowhere on the wire.

---

## Re-audit spot-check I will run when you say the fixes are in

Independent, from raw sources, no reuse of your verification:

1. `Body Reply Alert` — fire a real reply, then assert exec status `success`, `Reply Alert` →
   `ok:true`, and the message present in the channel via the Slack API.
2. `Dedupe` — assert the claim key is absent from static data after a deliberately failed run, i.e.
   a replay is *not* suppressed.
3. Zaps — re-read all 5 via Find Zap, assert `state: off` for every one that writes labels.
4. The 11 leads — re-read `label_ids` live and diff against the target sets above.
5. Wiper regression — force a person update on one repaired lead's person and confirm the label set
   is unchanged 5 minutes later.
6. SENT — after the WF-2S patch, assert `Find New Sends` emits a non-zero batch and that
   `__sent_seen_v2` starts recording; then reconcile the 817-row backfill against Pipedrive.
7. Fixture — assert activity 43974 is done/deleted, `72ec85c0` no longer carries `3. Responded`, the
   Responded population is 1,713 − 1 − (repairs re-added), and SL lead 4306240392 is suppressed.
