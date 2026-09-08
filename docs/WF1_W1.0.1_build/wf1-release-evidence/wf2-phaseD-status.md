# WF-2 Phase D - shadow deployed (day 0)

## Deployed

| workflow | id | state |
|---|---|---|
| WF-2 Smartlead Receiver | `jp7rum9Z0YDJkQWv` | **ACTIVE**, 123 nodes |
| WF-2H Health & Digest | `nK3yIOqRcBearV8s` | **ACTIVE**, 9 nodes, daily 07:15 |

Shipping config, verified from the deployed artifact (not from the build script):
`WRITE_MODE=shadow` · `classify_enabled=false` · `webhook_secret_sha256=null` (accept + rate-limited
warn) · `slack_channel_replies=C0B8GCVNR5W` · `slack_channel_ops=C0B8GCVNR5W`.

Production WF-1 unchanged throughout: `da23d080-a0e0-4126-81c0-0cca60908435`, 95 nodes, active.

Live URL: `https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}` → **200**.

## The 404 window - and why it probably cost nothing

Registration happened before the workflow was deployed, so the endpoint returned **404** to anything
Smartlead sent in that window. Given Smartlead disables an endpoint after 5 failures, I deployed
immediately rather than waiting for the `Slack WF-2` credential id.

Measured afterwards: the four ACTIVE campaigns last sent on **2026-07-22** and have sent nothing in
the last 24h, so there was most likely no traffic to lose. Stating that plainly rather than claiming
a rescue - the risk was real, the loss probably was not.

| campaign | rows | last sent |
|---|---|---|
| 3686181 | 221 | 2026-07-22T15:53Z |
| 3686184 | 175 | 2026-07-22T15:53Z |
| 3686187 | 175 | 2026-07-22T15:10Z |
| 3686193 | 193 | 2026-07-22T15:10Z |

## Day-0 observations

One execution only - my own post-deploy probe. It exercised two things correctly:

- `Verify Secret` → `mode=unconfigured`, `ok=true`, `warn=true`: traffic accepted, ops told, exactly
  the designed unarmed behaviour.
- unknown `event_type` → `Ops Warn Unknown Event`, no branch taken, nothing written.

Writes: **zero**. No write node ran; `Shadow Log` has no entries because nothing was intended. The
one Pipedrive lead added today (`Ben Budde Lead`, 01:25Z) predates WF-2's deployment by six hours and
came from the incumbent path.

## The thing that will limit this phase

**A 48-72h shadow window will observe almost nothing while the campaigns are idle.** No sends in
seven days. Replies to the 764 already-sent emails can still arrive and would flow through, so the
REPLIED path may well get real data; the SENT path will not until someone sends.

Two ways to get signal, in ascending order of intrusiveness - both Nik's call:

1. **Smartlead's own webhook Test button** (if present on the saved webhook). It posts a real
   Smartlead-shaped payload carrying the real `secret_key`, which proves registration + URL + the
   auth path end-to-end without touching a campaign. Zero risk. Do this one regardless.
2. **One internal test lead added to an ACTIVE campaign** - produces a genuine `EMAIL_SENT` and,
   if answered from that inbox, a genuine `EMAIL_REPLIED`. This sends a real email, so I have not
   done it and will not without an explicit instruction naming the address to use.

## Slack identity - RESOLVED

The first id supplied (`Udq1K604RpJqg1cR`) was the existing credential, live-named **"Heyreach
Slack"** - i.e. the identity we were trying to leave. Reported rather than "swapped", because
rebinding to the same id would have been a no-op that read as success.

The second id (`F9CCCbTx8KB5b2OO`) is the real one. Gate-proven in a throwaway workflow before
touching anything: a post reached `C0B8GCVNR5W` as `app_id A0BLETEHYBF`, bot **"Smarlead"** - a
different app from HeyReach's `A0BFX7C664S`. The bot was already a channel member, so no `/invite`
was needed. n8n's API has no credential-read endpoint (405 on both list and by-id), so a live post
was the only way to confirm both the type and the identity.

Both workflows redeployed on it, and proven end-to-end from WF-2 itself (exec **11601**):
`Ops Warn Unknown Event -> ok=true, channel=C0B8GCVNR5W, bot=Smarlead, app_id=A0BLETEHYBF`.
Proof mattered here because Slack nodes are `continueRegularOutput`: a wrong credential would have
swallowed ops warnings silently rather than failing loudly.

Locked by static **A7** (all 9 Slack nodes on `F9CCCbTx8KB5b2OO`, never `Udq1K604RpJqg1cR`) and
mutant 34. Suite now **169 tests / 0 failures, 34 mutants all caught**.

Note: the Slack app's display name reads **"Smarlead"** (missing a `t`). Cosmetic, but it is the
sender name the team will see on every alert - worth fixing in the Slack app settings, and it needs
no change here.

## Still outstanding
- Everything else on the flip checklist (5 open, B19 now closed).

## Flip checklist

| # | item | status |
|---|---|---|
| 1 | bind `Anthropic API` credential + `classify_enabled: true` + one smoke classify | open |
| 2 | rename the 4 ACTIVE `[Events Visiting]` campaigns to two-bracket | open |
| 3 | set `webhook_secret_sha256` to arm authenticity | open |
| 4 | bind `Slack WF-2` credential (both workflows) | **CLOSED** - gate-proven, exec 11601 |
| 5 | `slack_channel_replies` → `C07LTD8UT70` **+ /invite the bot and prove a post** | open |
| 6 | B19 deleted-person guard | **CLOSED** - shipped |
| 7 | flip `WRITE_MODE` → `live` | Melisa's call, not in this task |


---

# Day 0, second pass - B20 / F2 / B22 / B19-completion / F5 / F1 shipped

Artifact: **143 nodes**. Suite **184 tests / 0 failures**, **41 mutants all caught**, byte-identical
rebuild. Redeployed shadow; WF-1 untouched (`da23d080-...`, 95 nodes). Zero real writes throughout.

## B20 - proven fixed, visibly

Every gate's false branch now passes through a `Skip <label>` node that records to `Shadow Log`
**and continues exactly where the live write goes**. 14 gates, 14 skips, asserted by SH1/SH2, plus
SH3 which walks the graph taking only shadow branches and requires the whole reply chain to be
reachable. SH4 keeps `Shadow Log` terminal so continuation stays the Skip node's job.

The day-0 diff shows the before/after in one table:

| campaign | intents recorded | note |
|---|---|---|
| 100 | **1** (`Reply Alert`) | the original Smartlead test, pre-fix |
| 101/102/103 | **5** (`Reply Alert`, `SL Category`, `SL Forward Email`, `Lead Labels Union`, `Reply Activity`) | post-fix |

## B19 - my "CLOSED" was wrong, now actually closed

`Carry Person Ctx`, `Merge Reply Ctx` and `Person Id Final` all still read the **unverified**
`$('Person Pick')` / `$('R Person Pick')`, so the deleted-person guard was bypassed on both paths -
and `Person Id Final` would have attached a new lead to the DELETED person's id. Same class as B18:
the tests checked the guard in isolation and the wiring, never that the DECIDERS consumed it.

All three now read the verified output with an explicit fallback. New invariant **DEL8** fails if any
node reads a pick node without consulting the verify first; DEL9/DEL10 cover the two consequences.

## F5 - Smartlead-native category driving real gating

`Classify Skipped` now shapes Smartlead's own `reply_category` like an LLM answer, so the existing
guardrail handles it unchanged: `category=Interested, ok=true, id=1, source=smartlead-native,
forwardable=true`. The shadow diff reports **`native-gated (Interested)`** instead of DEGRADED.
Unknown native categories are still rejected by the guardrail (NC5), and with no native category the
old fail-open path is untouched (NC4). `__category_source` survives into the parse output, so at flip
both values can be logged side by side for the accuracy comparison.

## F1 - event-alias learning, with an honest caveat

`event_alias` flags any raw string that routes to a branch while differing from
`CONFIG.canonical_events`, and `Event Alias Watch` warns once per new string then remembers it in
static data. Proven live: `email_replied` (my own wrong constant) was flagged, and a later post was
silent.

**Caveat:** two probes 363 ms apart BOTH warned - concurrent executions read n8n's static data
before either persisted it. It converges (the third was quiet), so the worst case is a duplicate
warn on a simultaneous first sighting, not a flood. Worth knowing that **Dedupe shares this
exposure**: two identical events arriving in the same instant could both pass. Harmless in shadow;
worth a decision before live if Smartlead ever bursts duplicates.

## New gap for item 4

The Make API now answers **403** on scenario logs (it worked for blueprints earlier in this
engagement). The harness reports that column as **UNAVAILABLE** rather than as zero activity, but it
means the "what Make actually did" side of the comparison is currently blind. A token with
scenario-log scope is needed before the flip comparison can be two-sided.

## F4 confirmed on real data

The link check caught Smartlead's own inconsistency: `app_url` says `leadMap=123` while
`sl_email_lead_map_id` is `1221`. Preferring the payload's own link remains the right call.


---

# Forward map - final registry ingestion

Source: `Janea All Inboxes for Make.com Auto-Forward Workflow - Janea All Inboxes (1.15.2025).csv`.
Full detail in `inbox-registry-report.md`, machine-readable in `inbox-registry.json`.

## Ingestion

| metric | value |
|---|---|
| data rows read | **699** |
| unique inboxes ingested | **696** |
| exact duplicates collapsed | **3** (same inbox, same owner) |
| conflicting owners | **0** |
| malformed rows | **0** |
| distinct owners | **14** |

| owner | inboxes |
|---|---|
| Mario | 104 |
| Toby | 78 |
| Sergey | 64 |
| Mirza | 61 |
| Andreas | 50 |
| James | 44 |
| Chrissy | 44 |
| Rune | 44 |
| Noah | 44 |
| Matt | 44 |
| Can | 43 |
| Bill | 42 |
| Benedetto | 20 |
| Melisa | 14 |

Mario (104) and Toby (78) are indeed the largest, in that order.

The three collapsed duplicates were `pii-0a3c839e@example.invalid`,
`pii-0c26273b@example.invalid` and `pii-37cf60ff@example.invalid` - each listed twice with the
same owner, so dedupe was lossless. No inbox was claimed by two owners, so nothing needed flagging.

## Two premise corrections

**Row count: ~570 expected, 699 actual** (696 unique). The map is ~22% larger than the brief assumed.

**Owner count: 16 expected, 15 actual.** The registry contains 14 owner names. `forward_owner_map`
already held **James -> james@janeasystems.com** - the exact value specified - so that half of the
instruction was confirmatory rather than additive. The only genuinely new owner is **Matt**. Final
map: **15 keys** (14 blueprint + Matt). Counting James as new would double-count him.

`Test` remains mapped to melisa@ per the blueprint and owns zero inboxes - it is a placeholder in
the sheet's own owner-map column, not a sending identity.

## Independent cross-check

The sheet carries its own owner map in columns 8/9 of the first rows. Parsed separately, it
corroborates six mailboxes exactly - Andreas, Can, Mario, Melisa, Mirza, Toby - all matching
`forward_owner_map`. `Test` appears there with a blank mailbox, consistent with the above.

## Verification

Statics **190 / 0 failures**, **45 mutants all caught**, byte-identical rebuild. New **FM group**:

- **FM1** map loads at 696 with trimmed/lowercased keys
- **FM2** all 14 registry owners have a mailbox - nothing silently drops to default
- **FM3** three inboxes per owner (first/middle/last of each owner's sorted set = 42 chains) resolve
  end-to-end through the REAL `Forward Resolve` code: inbox -> owner name -> mailbox
- **FM4** unknown inbox -> `forward_default` **and** `__forward_miss: true`, and the miss provably
  takes the not-known branch that drives `Ops Warn Unknown Inbox`
- **FM5** no mailbox literal appears in any node outside CONFIG
- **FM6** Mario and Toby - 26% of the registry between them - resolve to their own mailboxes

Mutants added: registry truncated to 10 rows, an owner losing its mailbox, Mario/Toby swapped, and
the miss flag suppressed. All four are caught.

## Live resolution on the deployed build

| exec | inbox | owner | forwards to |
|---|---|---|---|
| 11607 | `pii-4d330955@example.invalid` | **Matt** | matt@janeasystems.com |
| 11608 | `pii-72319f4a@example.invalid` | **James** | james@janeasystems.com |
| 11605/11606 | `pii-e1200ff3@example.invalid` | Toby | toby@janeasystems.com |

All with `miss=false`, `source=config`. Artifact is 208 KB (the map is ~31 KB of it).

**Shadow is running on the new build**: WF-2 `jp7rum9Z0YDJkQWv` ACTIVE, 143 nodes, 696 inboxes,
15 owners, `WRITE_MODE=shadow`, `classify_enabled=false`, secret unarmed, all Slack to
`C0B8GCVNR5W` under the WF-2 app. WF-1 unchanged (`da23d080-...`).


---

# LLM provider switch: Anthropic -> OpenAI

Artifact **143 nodes**, suite **196 tests / 0 failures**, **49 mutants all caught**, byte-identical
rebuild, redeployed shadow. `classify_enabled` stays **false**, so the LLM node is unreachable in
production - the switch is inert until flip.

## What changed

| | before | after |
|---|---|---|
| `llm.provider` | (implicit anthropic) | `openai` |
| `llm.base` | `api.anthropic.com/v1/messages` | `api.openai.com/v1/chat/completions` |
| `llm.model` | `claude-sonnet-5` | **`gpt-5.2`** |
| `llm.model_fallback` | - | `gpt-4o-mini` (cost floor, one CONFIG line away) |
| token budget key | `max_tokens: 400` | **`max_completion_tokens: 400`** |
| temperature | (absent) | **still absent, deliberately** |
| request | single user message | `system` + `user`, `response_format: json_object` |
| response read | `content[0].text` | **`choices[0].message.content`** |
| headers | `anthropic-version` | Content-Type only; Authorization comes from the credential |

`Classify Skipped` (the Smartlead-native leg) was reshaped to the OpenAI response schema too, so the
native category and a real completion travel the *same* parse path - one contract, not two.

Token usage is now captured per classification: `__llm_usage {prompt, completion, total, model}`
plus `__llm_provider`, both surfaced on the Classify Parse output for the diff harness.

## Statics (new OA group) and mutants

- **OA1** provider/base/model/fallback in CONFIG, node URL still CONFIG-driven (no hardcoded host)
- **OA2** request shape: model, `response_format`, `max_completion_tokens`, **no** `max_tokens`,
  **no** `temperature`, system+user roles, and the full category dictionary present in the prompt
- **OA3** parses `choices[0].message.content`, captures usage
- **OA4** every guardrail survives: garbage / empty / unknown category / low confidence / no choices
  all land on `Uncategorized` with a null id and `is_dnc: false`
- **OA5** a DNC completion still drives the DNC branch
- **OA6** no Anthropic remnants anywhere (`anthropic`, `claude-`, `x-api-key`)

Mutants added and caught: parser left on the Anthropic shape (would have made **every** completion
read as empty -> silently Uncategorized forever), reverting to `max_tokens`, dropping
`response_format`, and reintroducing `temperature: 0`.

## BLOCKED: the smoke test needs the credential ID

Nik created the credential, but n8n exposes no credential-read endpoint (**405 on list AND by-id**),
and I hold no OpenAI key of my own, so I can neither bind the node nor call the API. Needed: the id
from the credential's URL, `/home/credentials/<id>`.

`wf2_openai_smoke.py` is written and dry-built (5 nodes). On receipt of the id it deploys a
throwaway workflow and runs five probes through Nik's credential:

| probe | question it answers |
|---|---|
| 0 | `GET /v1/models` - **does `gpt-5.2` exist on this account?** |
| 1 | Interested-shaped reply -> category + confidence |
| 2 | DNC-shaped reply -> `Do Not Contact` + `is_dnc` |
| 3 | garbage -> guardrail -> `Uncategorized` |
| 4 | `temperature: 0` - **is it rejected?** The param question, answered live |

It is deliberately not a generic proxy: bodies are baked in and chosen by index, so a temp webhook
carrying someone else's key cannot be used to send arbitrary prompts. Deleted immediately after.

### Two things the smoke must check that could bite quietly

1. **`gpt-5.2` may not exist on this account.** I have no independent knowledge of that model id, so
   I have configured it exactly as instructed and will report what the API says rather than assume.
   `model_fallback` makes the rollback one line.
2. **`max_completion_tokens: 400` may be too small.** On reasoning-class models, completion tokens
   include internal reasoning, so 400 can truncate the JSON. That surfaces as
   `finish_reason: "length"` and, because the guardrail is doing its job, as *every classification
   coming back `Uncategorized`* - a silent quality collapse rather than an error. The smoke returns
   whole responses so `finish_reason` and usage are visible.

## Flip checklist item 1 - updated

Was: *bind Anthropic credential + classify_enabled=true + smoke*.
Now: **bind the OpenAI credential id, run the smoke, then flip `classify_enabled=true`.** The
credential exists; the code path is built and statically proven; only the live verification and the
one-line flag remain.


---

# OpenAI switch - live verification (measured, not assumed)

Probes run directly against the API with Nik's key, using the **exact request shape WF-2 sends**.
Script: `wf2_openai_probe.py` (reads the key from the environment; never writes or prints it).

## 1. `gpt-5.2` exists

133 models visible; **`gpt-5.2` is present**. My caution was warranted but the model is real, so no
fallback was needed. Also available for reference: gpt-5, gpt-5-pro, gpt-5.1, gpt-5.1-codex-max,
gpt-4.1 family, gpt-5-mini/nano.

## 2. The request shape is accepted, and the rename was NOT optional

| probe | result |
|---|---|
| `max_completion_tokens` | **accepted** |
| `max_tokens` | **REJECTED 400** - *"Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."* |
| `temperature: 0` | **accepted (200)** |
| `response_format: json_object` | accepted; every answer parsed as strict JSON |

So the token-key rename was load-bearing - the old body would have failed outright on every call.
The temperature caution turned out **not** to apply to this model: it accepts `0`. I have still left
it omitted, because it buys nothing here (json_object + the closed dictionary do the work) and
omitting keeps the body portable across models that do reject it.

## 3. Classifications - correct, and one surprise worth a decision

| fixture | model's answer | confidence | tokens |
|---|---|---|---|
| Interested-shaped ("send some times next week") | **Meeting Request** | 0.95 | 195 |
| DNC-shaped ("remove me from your list") | **Do Not Contact** (`is_dnc: true`) | 0.99 | 182 |
| garbage (`### ~~~ ???`) | **Uncategorizable by Ai** | 0.66 | 169 |

Two things to notice.

**The "Interested" fixture came back as Meeting Request - and that is the better answer.** The reply
asks for times for a call. My fixture label was loose, not the model. Gating is unaffected:
Meeting Request is in `forwardable_categories`.

**Garbage did NOT fall to the guardrail.** The model confidently chose `Uncategorizable by Ai`,
which is a *real* category in `category_map` (id 8) with confidence 0.66 - just over the 0.6
threshold. So `__classify_ok` is **true**, the SL writeback fires with id 8, and because
`Uncategorizable by Ai` is **not** in `forwardable_categories`, **the reply is never forwarded to a
human**. Under the old guardrail path an unintelligible reply would have reached someone via
fail-open. This is a behaviour change, not a defect, and it is Nik's/Melisa's call:

- leave it: genuinely unintelligible replies get categorised and silently not forwarded;
- raise `llm.min_confidence` to ~0.70: 0.66 then fails the threshold -> `Uncategorized` ->
  `forward_on_uncategorized` -> a human sees it (one CONFIG line);
- or add `Uncategorizable by Ai` to `forwardable_categories` (also one line).

I have changed nothing here - flagging rather than deciding, since it trades noise against misses.

## 4. No truncation; cost per classification

`finish_reason: stop` on all three, completions ~43-47 tokens against a 400 budget - so
`max_completion_tokens: 400` is ample and the truncation risk I flagged did not materialise on this
model.

**546 tokens across 3 classifications - ~182 tokens each** (~137 prompt + ~45 completion). Prompt
size is dominated by the fixed category dictionary, so cost per reply is essentially flat regardless
of reply length (bodies are already capped at 4000 chars).

At observed volumes this is negligible: even 1,000 classified replies is ~180k tokens.

## Still needed to close flip item 1

The **n8n credential id** for "OpenAI API" (`/home/credentials/<id>`). The raw key must not go into
the workflow JSON - static AU4 forbids embedded credential values, and that rule is the reason a
leaked artifact has never been a risk in this project. Once the id lands: bind the node, redeploy,
flip `classify_enabled=true`.

## Security note

The key was pasted into chat, so it now exists in that transcript. It is stored only in the
scratchpad env file used for every other secret in this engagement - never in the repo, never in
evidence, never echoed. **Recommend rotating it once classification is live**, and note the order:
bind + verify first, then rotate, then update the n8n credential - rotating first would just mean
doing the binding twice.


---

# CLASSIFIER LIVE IN SHADOW - go-live report

Artifact **143 nodes**, suite **206 tests / 0 failures**, **55 mutants all caught**, byte-identical
rebuild. WF-2 `jp7rum9Z0YDJkQWv` ACTIVE. WF-1 unchanged (`da23d080-...`, 95 nodes).
Temp workflows and my duplicate credential removed - **0 probe/temp workflows remain**.

## 1. Credential binding - and a discrepancy worth naming

The brief said the credential was `httpHeaderAuth` with `Authorization: Bearer`. It is **not**:
binding it that way failed with

    Credential with ID "ltWhbdbiCcOBKnLn" does not exist for type "httpHeaderAuth"

Probed both hypotheses in a throwaway workflow before touching WF-2. `ltWhbdbiCcOBKnLn` resolves as
n8n's **native `openAiApi` type** - 133 models returned, `gpt-5.2` present. So the node now uses
`predefinedCredentialType` / `nodeCredentialType: openAiApi`, which is strictly better: n8n injects
Authorization itself, so no auth material can reach the workflow JSON (AU4) and no header literal
can drift.

I had earlier created my own credential to avoid a round trip. Nik's is the one bound;
**mine (`NmEfeiuZ5kCohCIS`) has been deleted** so exactly one credential holds the key and rotation
is unambiguous.

## 2. Three-way forward routing - live evidence, one probe per branch

Implemented in `Forward Resolve` rather than by duplicating the HTTP chain: reaching that node
already means "forwardable", so branch 3 is the *absence* of a forward.

| branch | probe reply | our category | conf | forward target |
|---|---|---|---|---|
| **1 owner** | "send times next week for a call" | Meeting Request | 0.94 | **toby@janeasystems.com** (`owner`) |
| **2 review** | `### ~~~ ???` | Uncategorized | 0.62 | **melisa@janeasystems.com** (`review`) |
| **3 no forward** | "out of office until August 12" | Out Of Office | 0.99 | **none** - resolver never ran |

Review-routed replies also produced the ops warn, carrying confidence, the reply text and an
**Open in Smartlead** link - an alert nobody can act on is just noise.

`min_confidence: 0.70` is doing exactly what it was raised for: the garbage reply scored 0.62 and
0.55 across runs, both of which would have been *accepted* at 0.6 and then silently not forwarded.

## 3. Two live gaps found and fixed during verification

**`__category_source` was empty on the classifier path.** Only the flag-off leg set it, so the
column the accuracy report keys off would have been blank for every real classification. Now
`openai` when the classifier runs, `smartlead-native` when the native leg supplies the category.
Locked by SRC1-SRC3.

**Shadow Log counted skipped writes as intended writes.** The Skip path records *both* "would write"
and "would skip" - so the diff harness would have overcounted. Entries now carry
`would_write` / `skipped_write`. Locked by SRC4. Visible immediately in the evidence above: on the
review branch, `SL Category` and `SL Forward Email` are recorded with `would_write=false`.

## 4. Accuracy report starts accumulating now

Every classified reply now records ours *and* Smartlead's side by side. In all three probes
Smartlead said `Interested` while our classifier said Meeting Request / Uncategorized /
Out Of Office - i.e. **the disagreement is already non-trivial on the first three samples**, which is
precisely the evidence Melisa wants. The diff harness reads `__category_source` + `reply_category`.

## 5. Token cost, measured in prod shadow

`gpt-5.2-2025-12-11`, `finish_reason: stop` on every call, completions well inside the 400 budget.

**541 tokens across 3 classifications - 180 per classification** (~137 prompt + ~43 completion).
Prompt is dominated by the fixed category dictionary, so cost per reply is effectively flat. Even
1,000 classified replies is ~180k tokens.

## Flip checklist

| # | item | status |
|---|---|---|
| 1 | OpenAI credential + `classify_enabled` + smoke | **CLOSED** - bound, probed, live in shadow |
| 2 | rename the 4 ACTIVE `[Events Visiting]` campaigns | open |
| 3 | arm `webhook_secret_sha256` | open |
| 4 | bind `Slack WF-2` | **CLOSED** |
| 5 | `slack_channel_replies` -> `C07LTD8UT70` + `/invite` + prove a post | open |
| 6 | B19 deleted-person guard | **CLOSED** |
| 7 | `WRITE_MODE` -> `live` | Melisa's call |

---

## FOR NIK - rotate the OpenAI key

The key passed through chat, so it exists in that transcript. Order matters:

1. **Done:** bound and verified (`ltWhbdbiCcOBKnLn`, live-probed).
2. **Rotate** on platform.openai.com - create a new secret key, revoke the old one.
3. **Update the VALUE** of credential `ltWhbdbiCcOBKnLn` in n8n. The id does not change, so
   **no rebuild and no redeploy** - the workflow references the credential, never the key.
4. Optional confirmation: one reply through the pipeline, or ask me to re-probe.

There is exactly one credential holding this key now, so there is nothing else to update.


---

# Self-service test campaign - REAL end-to-end run (option A)

Executed 2026-07-29. Campaign `3737501` "[Lead Nurturing] WF2 Shadow Test - API", created via API,
one real email sent, real reply verified, campaign deleted. Harness saved as
`wf2_selfservice_smoke.ps1` (182 lines, parses clean, rerunnable).

WF-1 `da23d080-...` unchanged. WF-2 143 nodes, active, shadow. No Make hooks/scenarios touched, no
other campaign touched, no account settings changed. 0 temp workflows left in n8n.

## Sender

Every one of **400 inboxes reported `daily_sent_count = 0`** - nothing had sent account-wide today -
so "lowest traffic" could not discriminate. Filtered on quality instead (warmup ACTIVE, 100%
reputation, 0 spam, >50 warmup sends): 49 qualified. Picked **`pii-4aa15de2@example.invalid`**
(163 warmup sends) over the marginally-more-warmed Toby inboxes, because Benedetto is a
lower-traffic recipient if any variant ever did resolve a forward.

## The send

| | |
|---|---|
| sent_time | 2026-07-29T15:18:22.756Z |
| to | pii-c61c7d08@example.invalid |
| subject | WF2 shadow test |
| stats_id | b97c697b-f4c2-4ad6-8927-56cf726c0198 |
| sender daily_sent after | 1 |
| lead status | COMPLETED |

Endpoint ground truth learned (now encoded in the harness): `POST /campaigns/create`,
`/{id}/email-accounts`, `/{id}/leads`, `/{id}/sequences`, `/{id}/schedule`, `/{id}/settings`,
`/{id}/status`. Two traps: `min_time_btw_emails` below ~5 gets a **bare 400 with an empty body**, and
`START` returns **500** if no schedule exists yet. Smartlead's sender cron took ~3.5 minutes.

## FINDING: the `EMAIL_SENT` event never arrives

The send happened at 15:18:22Z. The **only** webhook execution that followed was the REPLY, at
15:20:08Z. Reply latency was ~36s (reply 15:19:32Z), so an `EMAIL_SENT` would have been expected by
~15:19:00Z. Nothing arrived - then or later.

**Conclusion: "first email sent" is not enabled on the account-level webhook** (only the reply event
is). Consequences, and they matter for the flip:

* The entire **SENT branch has never been exercised by a real Smartlead payload** - person create,
  org create/reuse, lead create with the title convention. It is proven only against the recovered
  sample and synthetic probes.
* During the shadow window it will observe **zero SENT events**, so the diff harness cannot compare
  the SENT path at all.
* At flip, that branch would go live having never seen a real payload for its own event type.

Not fixable from the API - Smartlead exposes no webhook read/write endpoints (re-probed). **Nik: tick
the "first email sent" event on the existing webhook, then re-run this harness.**

## The reply - full pipeline on a REAL payload

Execution **11746**. Raw `event_type = EMAIL_REPLY`.

| check | result |
|---|---|
| secret path | `__auth_ok=true`, mode `unconfigured` (accepted + warn throttled). Source hint `16.176.213.221 / axios/0.19.2` - real Smartlead sender |
| event routing | `email_reply` -> REPLIED, `event_alias` null (canonical) |
| **`from_email`** | **`pii-4aa15de2@example.invalid` = OUR SENDING INBOX** |
| new field | **`sl_senders_mailbox`** = same value - an explicit sending-inbox field not present in the recovered samples |
| lead identity | `to_email` / `sl_lead_email` / `leadCorrespondence.replyReceivedFrom` all = pii-c61c7d08@example.invalid |
| ids | `sl_email_lead_id=4258441026`, `sl_email_lead_map_id=3459538085` |
| `app_url` | `...?leadMap=3459538085` - **matches** the map id (unlike Smartlead's own test fixture) |
| `reply.received_at` | populated from `time_replied` - the F2 fix, proven on real data |
| full_name | `Кривошея Микита` - Cyrillic from Gmail, survived canonicalisation intact |
| dedupe | ran, not a duplicate |
| nurture | `is_nurture=true` -> Slack-only |
| Shadow Log | exactly **one** intent: `Nurture Alert` / `slack:replies`, `would_write=true` |
| CRM intents | **zero** |
| classifier | did not run - as predicted for a nurture campaign |
| **real writes** | **ZERO** |

### F3 is now settled

Smartlead's doc sample put the lead's address in `from_email`, which threatened forward-owner
resolution. On a **real** reply it is unambiguously our sending inbox, and there is a second,
more explicit field (`sl_senders_mailbox`) carrying the same value. The campaign-based fallback
resolver stays design-only, permanently unless something changes.

Worth a small follow-up: add `sl_senders_mailbox` as the FIRST alias for `sender_inbox`, ahead of
`from_email`. Same value today, but it is the field that means what we need it to mean.

## Zero-writes assertions

* Pipedrive persons matching pii-c61c7d08@example.invalid: **0** (before and after)
* Pipedrive leads referencing the test campaign: **0**
* 84 leads were added to Pipedrive today - **all** from WF-1/HeyReach (`512995 -` / `513000 -`
  titles) plus three pre-existing Make leads. None ours.
* Smartlead `lead_category_id` on the test lead: **NULL** - no category writeback

## Cleanup

Paused, deleted, absent from the campaign list (116 campaigns, the original count).

## What the team saw

As predicted before the send: Make module 131 (`contains "lead nurturing"` -> `C07LTD8UT70`) fires on
a nurture reply, so the lead-processing channel received **one** message announcing a
*"New \"Responded\" Lead Label in Pipedrive!"* that was **never written** - modules 19/26/124/67 all
gated the CRM branches off. Pre-existing Make behaviour, surfaced rather than introduced.


---

# SENT event investigation - VERDICT

Run 2 executed with the events confirmed ticked. Campaign `3737617`, sender
`pii-c6426f78@example.invalid` (the harness re-picked automatically, correctly excluding
benedetto which now had 1 send today). Send confirmed at **15:32:08.123Z**,
`stats_id=26904f4f-aebf-4151-ba5a-7043499fd09d`. **No SENT event in 12 minutes.** Campaign paused,
deleted; 116 campaigns, both test campaigns gone.

## Verdict: SENT is observable, via `EMAIL_SENT` - but not on OUR webhook entry

There are **two** Smartlead webhook entries, and the reply payload names the one that delivered it:

| webhook_id | name | URL | receives |
|---|---|---|---|
| `151526` | Make.com webhook | Make's hook | **`EMAIL_SENT`** (and replies) |
| **`703611`** | **N8n** | `https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}` | `EMAIL_REPLY` only |

**Nik: open webhook entry `703611` ("N8n") specifically** and enable First Email Sent there. The
tick almost certainly landed on entry `151526`, or did not persist on `703611`.

### How each hypothesis was settled

**"Smartlead never emits SENT" - FALSE.** Pipedrive lead
`3565502 - [Sales Sprint] Sales Sprint 2026 - London - Valids - Person-6fe1a561` was created at
`2026-06-30T07:51:46.420Z`; Smartlead's send to her was `07:51:43.769Z`. A **2.7-second** gap is
Make's SENT scenario reacting to a live `EMAIL_SENT` webhook. Same for Person-e44b6aa0
(sent 15:23:19, lead created 15:23:22). So the event exists and fires on this account.

**"Fires once per lead lifetime" - FALSE.** After run 1's campaign was deleted,
`GET /leads/?email=pii-c61c7d08@example.invalid` returns **no account-level record**, so run 2 was a
first-ever send to a fresh lead identity - and still produced nothing.

**"Our endpoint is at fault" - FALSE.** The identical URL, secret path and workflow received the
`EMAIL_REPLY` for the same campaign 36 seconds after the reply.

**"Suppressed for nurture-named campaigns" - implausible, and now cheap to disprove.** Smartlead has
no notion of "lead nurturing"; that string is purely a Make-side filter. Formally untested because
testing it needs a NON-nurture campaign, which - per module 28's `notcontain` gate sitting ahead of
`CreatePersonV2`/`createLead` - would have Make create a real Pipedrive person and lead for the
recipient. Not worth a production write: once SENT is enabled on entry `703611`, re-running the
harness settles it for free.

## What the SENT branch subscribes to

**`EMAIL_SENT`** - the event name in the recovered real payload, and the one Make has been receiving.
No code change is needed: `Normalize`'s discriminator already matches `/first.*sent|email.?sent/`,
so both the UI label and the payload constant route correctly. The only outstanding action is the
UI tick on entry `703611`.

## Standing risk this exposes for flip day

Both `151526` (Make) and `703611` (n8n) are subscribed to replies **simultaneously**. That is the
expected shadow arrangement, but at flip it becomes double-processing unless Make's scenarios are
switched off in the same window. Already on the cutover-cleanup list; this is the first hard
confirmation that both entries are live, with ids to act on.

## Harness

`wf2_selfservice_smoke.ps1` gained **`-SentOnly`**: create -> send -> watch 12 minutes for the SENT
contract -> cleanup, no reply needed. Both modes are now exercised against the live platform.
Diagnostic tip encoded by this investigation: the payload's `webhook_id` / `webhook_name` identify
which registration delivered an event - the fastest way to tell a subscription problem from an
endpoint problem.


---

# SENT event - run 3, and a correction to my own diagnosis

Run 3 with all four events confirmed ticked on entry `703611`. Campaign `3737776`, sender
`pii-9d1457fa@example.invalid` (harness rotated senders again - both previous ones now
had a send today). Send confirmed **15:56:23.664Z**, `stats_id=15ea3522-...`.
**No SENT event in 12 minutes.** Campaign paused, deleted.

## My previous diagnosis was WRONG

I concluded the cause was a missing tick on entry `703611`. That is now disproven: the tick is
present and `EMAIL_SENT` still never arrives. Three sends - 15:18:22, 15:32:08, 15:56:23 - produced
**zero** webhook executions, while the reply on the very same entry and the very same campaign
arrived in 36 seconds.

## What is now established, by evidence

| fact | evidence |
|---|---|
| `EMAIL_SENT` exists and fires on this account | Pipedrive lead for Person-6fe1a561 created 2.7s after her Smartlead send (and Sudheendra, 3s) - Make's SENT scenario reacting to a live event |
| entry `703611` receives replies | exec 11746, `webhook_id=703611 (N8n)`, 36s latency |
| entry `703611` never receives sends | 3 confirmed sends, 12-minute windows, zero executions |
| it is not our endpoint | same URL, same secret path, same workflow accepted the reply |
| it is not per-lead-lifetime | run 2 was a first-ever send to a lead with no account-level record |
| **it is not the nurture name** | the reply that DID arrive was on `[Lead Nurturing] WF2 Shadow Test - API`. A name-based filter would have suppressed that too |
| it is not the tick | run 3, all four ticked |

## Remaining explanation

A **Smartlead-side per-event subscription defect on entry `703611`**: the UI shows First Email Sent
enabled, but the platform does not deliver that event type to this entry. Entry `151526`
("Make.com webhook") does receive it, so the capability is account-wide, not plan-limited.

The one variable still formally untested is a **non-nurture campaign name**. I have not tested it
because Make's SENT scenario gate (`module 28: notcontain 'lead nurturing'`) sits *ahead* of
`CreatePersonV2`/`createLead`, so a non-nurture test send would have Make create a real Pipedrive
person and lead for Nik's personal address. That needs explicit approval, and the reply evidence
above already argues strongly against a name-based cause.

## Recommended actions, cheapest first

1. **Delete and recreate the webhook entry** with all four events ticked from creation, then re-run
   `./wf2_selfservice_smoke.ps1 -Recipient <addr> -SentOnly`. A stuck subscription that was created
   reply-only is the most likely story, and recreation is the standard cure. Note the new entry will
   have a new `webhook_id` - the payload reports it, so verification is immediate.
2. If that fails, **Smartlead support**, quoting precisely: account-level entry `703611` delivers
   `EMAIL_REPLY` but never `EMAIL_SENT`; entry `151526` delivers `EMAIL_SENT`; three confirmed sends
   with `stats_id` b97c697b / 26904f4f / 15ea3522 produced no delivery.
3. **Architectural fallback, worth considering regardless.** The SENT branch exists to create the
   person / org / lead on first contact. That does not have to be event-driven: WF-2H already polls
   `/campaigns/{id}/statistics`, which is where all three sends *were* visible within ~3 minutes.
   A reconciliation pass over recent stat rows could create the same CRM records idempotently, with
   the webhook as an accelerator rather than a dependency. That removes a single point of failure we
   have now watched fail three times - and it is the only route that does not depend on a vendor fix.

## Consequence for the flip

**The SENT branch still has no real-payload verification, and the shadow window will observe only
replies.** The reply half is now thoroughly proven on real data; the send half is proven only against
the recovered sample and synthetic probes. That is a decision for flip day, not a blocker for the
watch window: shadow writes nothing either way.

Recommend adding to the flip checklist: **"SENT observability resolved (recreate entry, or ship the
statistics-poll fallback)"** - currently open.


---

# Run 4 - VERDICT: escalate. Fallback is now the primary SENT source.

Run 4 against the **recreated** entry. Campaign `3738259`, sender
`pii-b630d18c@example.invalid`, send confirmed **17:08:17.906Z**,
`stats_id=28cfadef-...`. **No SENT event in 12 minutes.** Campaign paused, deleted.

Recreating the entry did not fix it. Four sends, two entries, event ticked every time:

| send | entry | SENT delivered |
|---|---|---|
| 15:18:22 | 703611 | no |
| 15:32:08 | 703611 | no |
| 15:56:23 | 703611 | no |
| 17:08:17 | **704352 (recreated)** | no |

Meanwhile the same entries deliver replies in ~36s, and Make's entry `151526` demonstrably receives
`EMAIL_SENT` (Person-6fe1a561's Pipedrive lead, 2.7s after her send). Capability exists account-wide;
delivery to our entries does not.

## Escalation packet for Smartlead support

* Account-level webhook entry **704352 "N8n"** -> `https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}`
* All four events ticked at creation. `EMAIL_REPLY` and `EMAIL_BOUNCE` arrive normally.
* `EMAIL_SENT` has never arrived, on this entry or its predecessor `703611`.
* Four confirmed sends, each visible in `/campaigns/{id}/statistics` within ~3 minutes:
  `b97c697b-f4c2-4ad6-8927-56cf726c0198`, `26904f4f-aebf-4151-ba5a-7043499fd09d`,
  `15ea3522-4538-4956-b993-aa4894bec3a4`, `28cfadef-db15-44b0-9c0e-bf46739f62ac`.
* Entry `151526` ("Make.com webhook") on the same account DOES receive `EMAIL_SENT`.
* Ask: why is `EMAIL_SENT` not delivered to entry 704352 while other event types are?

## ORGANIC TRAFFIC HAS STARTED - and the shadow window is already earning its keep

While run 4 was in flight, real Ai4 replies and bounces began arriving (campaigns 3686181 / 3686184 /
3686193). These are NON-nurture, so the **full** reply chain ran on real prospects for the first time:

| exec | lead | ours | conf | Smartlead | forward |
|---|---|---|---|---|---|
| 11760 | pii-fadad451@example.invalid | Meeting Request | 0.98 | id 2 (= Meeting Request) | rune@janeasystems.com (owner) |
| 11761 | pii-c3153db8@example.invalid | Meeting Request | 0.92 | id 2 (= Meeting Request) | rune@janeasystems.com (owner) |

Both **agree** with Smartlead. Also proven on organic data: the 696-inbox forward map
(`pii-152a1b4a@example.invalid` -> Rune), lead resolution via the **title_prefix fallback**
(`how=title_prefix` - the Campaign field is empty on Make-created leads, exactly as designed for),
the first-reply gate (no alert on an already-Responded lead), and `would_write` accounting.

### DEFECT found by organic traffic: `reply_category` is a NUMERIC ID in the wild

Smartlead's test payload said `"Interested"`; real organic replies say `2`. Left unresolved this
would have (a) made the F5 native fallback reject every organic reply as an unknown category and
route it all to human review, and (b) made the accuracy report compare `"Meeting Request"` against
`2` and call it a mismatch. `Normalize` now reverse-maps ids through `category_map`, and an id it does
not recognise becomes `null` rather than an invented name. Locked by NC1b/NC1c + mutant 56.

Suite now **208 tests / 0 failures, 56 mutants all caught**, byte-identical rebuild, redeployed.

## WF-2S - the fallback, deployed and ACTIVE

`build_wf2s.py` -> `wf2s-built.json`, **16 nodes**, deterministic, id `6Y92ryBwYoy6z0Jx`, runs every
15 minutes.

It does **not** reimplement the SENT branch. It polls `/campaigns/{id}/statistics` for ACTIVE
campaigns, finds sends inside `lookback_minutes` that it has not seen, looks up the lead to obtain
`sl_email_lead_id` + the campaign-lead map id, synthesises the `EMAIL_SENT` payload Smartlead should
have sent, and POSTs it to WF-2's own webhook. Consequences:

* one implementation, one test suite - the SENT branch stays the only code path
* WF-2's Dedupe keys on `campaign_id + sl_lead_id`, so re-polling is idempotent even if WF-2S loses
  its own state
* payloads carry `__reconciled: true` / `__reconciled_by: WF-2S`, so Shadow Log and the diff harness
  can always distinguish a reconciled event from a genuine delivery
* `max_per_run` (25) bounds a cycle, and **anything dropped is posted to ops** - a silent truncation
  would read as "all caught up"

### One follow-up before the secret is armed

WF-2 validates `secret_key` in the request **body**, and n8n credentials can inject headers but not
body fields - so a replayer cannot carry the real secret without embedding it in the workflow JSON,
which AU4 forbids. When the secret is armed, add a header-based replay credential (`X-Replay-Auth`
against `CONFIG.replay_secret_sha256`). Until then the secret is unarmed and accept-all, so replay
works as built. Recorded here rather than left as a surprise at arming time.


---

# WF-2S DEPLOYED AND ACTIVE - SENT is observable again

`6Y92ryBwYoy6z0Jx`, 14 nodes, every 15 minutes, versionId `2f9c24b6`. Escalation to Smartlead stands
(entry 704352 still never delivers `EMAIL_SENT`), but SENT no longer depends on that being fixed.

## Proven on real traffic, 18:15 cycle

| | |
|---|---|
| campaigns scanned | 116 -> 4 ACTIVE |
| statistics rows considered | 891 |
| replayed into WF-2 | **100** |
| rejected | **0** |
| replayed without lead ids | **0** |
| beyond `max_per_run`, deferred | 27 (reported, retryable) |
| WF-2 executions produced | **100, all success** |
| Pipedrive persons/leads created | **0** (`success=true`, 100 rows each - a real answer, not an errored call) |

Sample no-person execution (11911, `pii-cbe3a822@example.invalid`): `__reconciled=true`,
`__reconciled_by=WF-2S`, `Lead List` did not run, `Lead List Skipped` returned `data_len=0`, and
Shadow Log holds the full intended `Lead Create` POST body with `would_write:true` /
`skipped_write:"Lead Create"`.

## Five defects the reconciler found - four in itself, one in WF-2

Cycle 1 crashed. That crash was worth more than a clean run, because two of the four defects it led
me to would never have thrown.

| id | defect | why it mattered |
|---|---|---|
| S1 | backward `.item` lookups across the HTTP fan-out | crashed cycle 1 (exec 11764) |
| **S2** | `Pick Active` read `$json` from a response n8n had **split into 116 items**, so it saw campaign #1, not the array | found zero ACTIVE campaigns and **would have idled forever, silently** - the worst possible failure for a fallback whose only job is to be the SENT source |
| **S3** | `Build SENT Payload` was run-once-for-all-items but read `$json` and returned one item | **one send replayed per cycle** regardless of batch size, silently |
| **S4** | sends marked seen *before* the replay was accepted | a transient WF-2 outage lost 100 sends permanently. Found the hard way (below) |
| **B23** | *in WF-2*: no Pipedrive person -> `person_id=0` -> Pipedrive 400 -> **SENT execution aborted** before Shadow Log recorded anything | blinded shadow observation for exactly the brand-new prospects it exists to observe. Never seen before because SENT had never arrived. 8 of the first 25 replays hit it |

B23 also exposed a parity gap: SENT's `Lead List` was the only one of the four (`Lead List`,
`R/B/U Lead List`) without `continueRegularOutput`, so any Pipedrive hiccup aborted the execution
instead of degrading. Now consistent.

### How S4 was found, and the outage it exposed

The 18:00 cycle reported `__failed: 100`. Cause: the cycle fired at 18:00:57, inside the
deactivate/PUT window of my own WF-2 deploy - `404 Active version not found`. Self-inflicted, not a
design fault. But it proved the design fault behind it: all 100 were already marked seen, so they
were gone for good. Marking now happens only for replays WF-2 accepted, the store is namespaced
`__sent_seen_v2` (abandoning the poisoned keys, which is how those 100 were recovered), and it is
pruned - at ~100 sends/cycle it would otherwise have grown ~10k keys/day forever.

**WF-2 was inactive from ~18:05 until I reactivated it at ~18:10.** The instance crashed at 18:00:03
(exec 11800) and my activation did not survive the restart. Impact, measured rather than assumed:
**zero replies** in that window across all four ACTIVE campaigns (checked `reply_time` directly).
Lost SENT replays were recoverable via the `_v2` reset. Operational lesson: after any PUT+activate,
re-verify `active` a minute later - a concurrent instance restart can silently drop the flag.

## Test position

| suite | result |
|---|---|
| WF-2 statics | **215 passed, 0 failed** (RC1-3 provenance, B23-1..4) |
| WF-2 mutants | **62/62 caught** |
| WF-2S statics | **41 passed, 0 failed** |
| WF-2S mutants | **23/23 caught** |

Both rebuild byte-identically. The WF-2S suite executes the real node code from `wf2s-built.json`
with `.item` deliberately wired to throw, so an S1 regression fails the same way production did.
One mutant escaped on the first pass (`cross-check made case-sensitive`) - a real hole: the fixture
only varied the lead side of the email comparison, so the row side was untested. Test fixed, not the
mutant.

## Still open for Nik

Unchanged from before, plus:
* **SENT observability**: WF-2S is the primary source. Smartlead support ticket still worth filing.
* **`max_per_run` is being hit** (27 deferred at 18:15). Harmless - deferred sends are retried inside
  the 180-minute lookback - but if Ai4 volume climbs, raise it rather than let the backlog ride.
* **Replay auth**: when the webhook secret is armed, WF-2S needs the header-based replay credential
  (`X-Replay-Auth`), because n8n credentials cannot inject a body field and AU4 forbids embedding the
  secret in the workflow JSON.


---

# LIVE WINDOW - 2026-07-29 18:34:03Z onward (WRITE_MODE=live)

Authorised by Nik's relay. Noted at the time: the standing gate said live requires **Melisa's**
explicit go relayed by Nik, and that go was not cited.

| setting | value |
|---|---|
| WF-2 | `WRITE_MODE=live`, versionId `6793502f` (after the B24 fix) |
| harness campaign | `3738616` "[Events Visiting] [WF2 Live Test 2026] - Nik - Valids" |
| B24 proof campaign | `3738811` (same name + " B24") - one extra send, no reply needed |
| sender | `pii-4c3584c0@example.invalid` - 0 sends today, 100% warmup |
| forward override | `Chrissy -> pii-c61c7d08@example.invalid` (window only) |
| replies channel | `C0B8GCVNR5W` (unchanged - bot not invited to lead-processing) |
| WF-2S | SCOPED to the two harness campaigns |

**Why the sender is Chrissy.** Forward routing resolves by *sending inbox* -> owner -> address. The
four ACTIVE campaigns belong to Rune and Mario, so remapping either would have redirected real
prospect replies to a personal Gmail. Chrissy owns 44 inboxes and no ACTIVE campaign, so the
override can only ever affect the harness. Proven in-window: the organic reply below still forwarded
to `rune@janeasystems.com`.

**Why WF-2S was scoped.** Wide open in live mode it replays a 180-minute backlog (~42 Ai4 sends/hour)
as fresh Pipedrive person+org+lead creations, for sends Make processed hours ago. That is a backfill
artifact, not "organic events during the window". Scoping is one CONFIG line and is reported in the
ops post, so a narrowed reconciler cannot read as a full one.

## B24 - THE GO-LIVE BLOCKER, found in the first live write

The SENT branch decided "does a lead already exist?" using the **Campaign custom field only**.
**Make never populates that field.** So the check could not see Make's lead, and WF-2 created a
second one:

| lead | created | Campaign field |
|---|---|---|
| `9d7a7590-...` (Make) | 18:37:55.945Z | `''` |
| `cf9d8370-...` (WF-2 live) | 19:00:48.551Z | `[Events Visiting] [WF2 Live Test 2026] - Nik - Valids` |

Identical titles, same person, same campaign, 23 minutes apart. **Going live with Make running would
have duplicated every single lead.**

The reply/bounce/unsub branches were never affected - `LEAD_RESOLVE` already falls back to the
`"{campaign_id} - "` title prefix, which is exactly how the organic reply below found its lead
(`how=title_prefix`). The SENT branch simply never got that fallback. The asymmetry *was* the bug.

**Fixed** by porting the same rule, same order, into `Lead Select`. **Proven on real data** with
campaign `3738811`: Make created its lead at 19:12:14, WF-2's reconciled SENT ran at 19:15 and
resolved `exists=true how=title_prefix lead_id=682d0920-...`, `Lead Create` did not run,
`NoOp Lead Exists` did. One lead for that campaign, not two. The duplicate from campaign 3738616 has
been deleted.

## S5 - every campaign's final batch of sends was unobservable

The harness campaign completed 3.5 minutes after its only send. WF-2S polled ACTIVE campaigns only,
so it never saw it - and since SENT arrives *only* via WF-2S, the tail of **every** campaign was
being lost, not just this test's. Now also polls non-ACTIVE campaigns whose `updated_at` is inside
the lookback. The rule is exact, not generous: a finished campaign stops sending, so if it was last
updated longer ago than the lookback, it cannot have in-window sends. Confirmed live - the cycle at
19:00:43 polled `3738616/COMPLETED` and reconciled the send.

Related honesty fix: the synthetic payload hardcoded `campaign_status: 'ACTIVE'`. It now reports the
real status (`COMPLETED` for both harness campaigns).

## Organic reply processed LIVE - exec 12037, 18:39:10Z

`pii-b9ee8bb5@example.invalid`, campaign `[Events Visiting] AI4 2026 - Rune - Catch-alls`. Every write real:

| step | result |
|---|---|
| classify | **Meeting Request**, confidence 0.84, `__category_source=openai` |
| lead resolve | `how=title_prefix` (Make's lead, empty Campaign field - B24's root cause from the reply side) |
| Smartlead category write | `{ok:true}` |
| forward | **`rune@janeasystems.com`** (`reason=owner`), `{ok:true, status:"success"}`, real messageId |
| Pipedrive activity | created, id `42850` |
| lead labels | **skipped, correctly** - `__skip: !changed`, the lead already carried all three labels; Shadow Log recorded it with `would_write:false` |

That last row is worth stating plainly: a skipped write in live mode is not a failure, it is the
no-op avoidance working, and the accounting still records the intent.

## Pipedrive state (clickable)

* person `Nik Krivosheia` - https://janeasystems.pipedrive.com/person/84799 (created by **Make** 18:37:55, WF-2 matched rather than duplicated)
* lead, campaign 3738616 (Make) - https://janeasystems.pipedrive.com/leads/inbox/9d7a7590-8b7c-11f1-83ed-ad8f7a16c1bf
* lead, campaign 3738811 (Make; WF-2 correctly matched it) - https://janeasystems.pipedrive.com/leads/inbox/682d0920-8b81-11f1-8879-2b3e65712e6b
* organic activity 42850 - https://janeasystems.pipedriveu.com/activities/list
* WF-2 duplicate from B24 - **deleted**

## Test position

WF-2 **221 statics / 65 mutants**, WF-2S **52 statics / 30 mutants**, all passing.

Two harness bugs fixed along the way, both the same false-pass class:
* the WF-2S mutation harness compared a re-serialised dict against raw file text, so formatting
  differences alone made every no-op mutation look applied. That is how a mutant aimed at code I had
  restructured reported a false pass. Now canonical-vs-canonical.
* the WF-2 `ships_live` mutant hardcoded `WRITE_MODE=live`, which during a live window is a no-op.
  It now flips relative to the baseline, so it always discriminates.

`validate()` still refuses to build live; `--allow-live` is an explicit, logged opt-in, and the
ship-state static needs `WF2_EXPECT_MODE=live` to accept it. Verified both directions.

## Revert checklist (one command each)

1. `build_wf2s.py`: `campaign_allowlist` -> `[]`  (restores organic SENT reconciliation)
2. `build_wf2.py`: `WRITE_MODE` -> `"shadow"`; rebuild WITHOUT `--allow-live`
3. `build_wf2.py`: `"Chrissy"` -> `chrissy@janeasystems.com`
4. pause + delete campaigns `3738616` and `3738811`; delete the two harness leads + person 84799 if wanted

WF-1 `da23d080-a0e0-4126-81c0-0cca60908435` unchanged throughout.


---

# WINDOW CLOSED - RESTORED TO SHADOW at 2026-07-30T07:00:10Z

Open 18:34:03Z -> 07:00:10Z (~12.5h; it ran overnight waiting on the reply). Nik's call: RESTORE.

## The reply, end to end - and two defects it exposed

Reply landed 06:46:03Z, exec 12099. What worked:

| step | result |
|---|---|
| execution | arrived, `success` |
| classification | gpt-5.2 returned **Interested / 0.62** -> below `min_confidence` 0.70 -> **Uncategorized**, `__category_source=openai` |
| lead resolve | `how=title_prefix` (Make's lead) |
| three-way forward gate | routed to **review** -> `melisa@janeasystems.com` |
| Smartlead category | **correctly NOT written** - the fail-safe refuses to POST a category we did not determine (`__skip`, recorded in Shadow Log) |
| reply activity | created **with the reply body**, id 42857 |
| labels union | PATCHed, 3 labels |

Two things did NOT work, and both were invisible until this run.

### B25 - the human-review forward was DEAD (the review routing never worked)

`Body SL Forward Email` spread `...$json` and never set its own `__skip`, so it **inherited**
`__skip` from `Body SL Category` upstream (`__skip: !__classify_ok`). Uncategorized always skips the
category write - therefore **every review-routed reply silently skipped its forward too.** The
routing to `forward_review_address` has never once delivered. It looked healthy in shadow because
shadow skips everything anyway, and the organic replies all classified above threshold (0.84, 0.92,
0.98) so they took the owner path where `__classify_ok` is true.

Fixed: the forward decides its own `__skip` (no recipient, or nothing to forward -> skip). Audited
every Body node for the same flaw. Correction to my first pass: `Body Person Create`,
`Body Lead Create` and `Body Nurture Alert` return a FRESH object without spreading `$json`, so they
were never vulnerable - the real rule is "spreads `$json` AND sets no `__skip`". Two latent cases
(`Body Reply Alert`, `Body SL Unsubscribe`) fixed too. Locked by B25-1, which fails if any Body node
ever inherits the flag again.

### B26 - the Slack reply alert has NEVER posted

`Reply Alert` and `Ops Warn Classify` both returned `{"error":"invalid syntax"}`.
`Ops Warn Bad Secret` posted fine on the same credential and channel.

Root cause, and it is embarrassing: in `OPS_WARN_TEXT_CLASSIFY` a bare `"` inside a Python
double-quoted string **terminated it**, Python concatenated the fragments, and the built expression
was no longer valid JavaScript. Slack rejected it. Nothing in 224 statics checked whether these
expressions even parsed.

Note also that `Reply Alert` is WRITE_MODE-gated, so it was skipped for the entire shadow phase.
This live window was its first real run in production, and it failed. **No reply alert has ever
reached Nik's channel.**

Fixed: the helper is rebuilt with `String.fromCharCode(34/39)` so no quote literal can break the
Python string again, and the reply is rendered as readable plain text (quoted original dropped, tags
stripped, entities decoded, capped at 300) instead of `&lt;div dir="ltr"&gt;...`. New statics
**SLKX1/SLKX2 parse every Slack text and channel expression as JavaScript** - the invariant that was
missing - plus SLKX3 asserting the rendered message contains the human sentence and no markup.

My first hypothesis (the raw reply body was the trigger) was wrong: `ALERT_TEXT` does not quote the
body at all. Both failing nodes do build Slack `<url|label>` links, which the working one does not -
but the proven, reproduced cause is the parse failure, and that is what the mutant asserts.

## Full live-window write audit - 5 executions, 11 real writes

| exec | event | lead | real writes |
|---|---|---|---|
| 12037 | REPLIED | pii-b9ee8bb5@example.invalid | SL Category, SL Forward Email -> rune@, Reply Activity 42850 |
| 12040 | SENT (replay) | pii-c61c7d08@example.invalid | Person Patch, **Lead Create** (the B24 duplicate) |
| 12042 | SENT (replay) | pii-c61c7d08@example.invalid | Person Patch only - **B24 fix proven** |
| 12077 | REPLIED | pii-d08614f0@example.invalid | SL Category, SL Forward Email, Reply Activity 42856 |
| 12099 | REPLIED | pii-c61c7d08@example.invalid | Lead Labels Union, Reply Activity 42857 |

Nothing else touched Pipedrive or Smartlead in 12.5 hours. Organic SENT was not reconciled while the
reconciler was scoped, and those sends have now aged past the 180-minute lookback - the cost I
flagged when the window opened, realised because it ran overnight. Unobserved, not lost: the sends
happened and Make processed them as usual.

## Restore executed

| item | state |
|---|---|
| `campaign_allowlist` | `[]` - organic SENT reconciliation resumed |
| `WRITE_MODE` | `shadow`, rebuilt **without** `--allow-live` (the guard is satisfied naturally again) |
| Chrissy mapping | `chrissy@janeasystems.com` |
| harness campaigns 3738616 / 3738811 | paused + **deleted** (0 remain) |
| WF-2 | active, versionId `ab1ef090` |
| WF-2S | active, versionId `df4d96d7` |
| WF-1 | `da23d080-a0e0-4126-81c0-0cca60908435` unchanged |

Test trails removed: activity 42857, both Make-created leads for the test campaigns, person 84799.
**Organic writes deliberately retained and verified intact** - activities 42850 and 42856, and
Person-602a4fea's lead.

Suites after the restore: WF-2 **227 statics / 69 mutants**, WF-2S **52 / 30**, byte-identical
rebuilds, all passing with the default (shadow) expectation.

## What the flip now needs, on top of the earlier list

* **Verify the reply alert actually posts.** B26 is fixed in code but unproven live, because
  `Reply Alert` is WRITE_MODE-gated and cannot fire in shadow. `Ops Warn Classify` is ungated, so the
  next low-confidence organic reply will prove the Slack path in shadow - watch for it.
* **B25 the same way**: the review forward is fixed but has never delivered a message. First live
  Uncategorized reply is the proof.
* min_confidence 0.70 sends a plainly positive "Sounds good, thanks for reaching out!" to human
  review at 0.62. Not a defect - but if that rate is typical, Melisa's review queue will be busier
  than the 90-95% pitch implies. Worth measuring during shadow with the native-vs-ours comparison.


---

# OWNER DECISIONS AFTER THE LIVE WINDOW (2026-07-30)

## 1. B25/B26 proof - flip-day smoke item ADDED

* `Ops Warn Classify` is ungated, so it proves the Slack fix on the next low-confidence organic
  reply. Watch for it, report when seen.
* The review-forward proof does NOT wait for random organic traffic: at flip-day smoke, one
  **scripted low-confidence reply through the harness** proves it live.

**FLIP CHECKLIST - new smoke item (S):** one scripted low-confidence reply, in live mode, asserting
three things that have never once worked in production:

1. the review forward actually DELIVERS to `forward_review_address` (B25 - never delivered)
2. `Ops Warn Classify` POSTS to Slack (B26 - never posted)
3. `Reply Alert` POSTS to Slack (B26 + it is WRITE_MODE-gated, so it is unprovable in shadow)

One scripted reply exercises all three, so this costs nothing extra.

### Why I would not rely on organic alone for B26

The calibration data below says **0 of 9 organic prospect replies scored under 0.70** - the lowest was
0.84. If that rate holds, a low-confidence organic reply may not appear for days or weeks, so the
`Ops Warn Classify` proof could sit open a long time. The scripted flip-day reply covers B26 as well
as B25 for free. Recommend treating organic as the bonus confirmation, not the primary proof.

## 2. Missed organic SENT window - CLOSED

Accepted as a known cost: Make processed those sends, observation is lost, no data lost. Closed.

## 3. Threshold 0.70 - calibration report is now RUNNING

`wf2_calibration.py` (read-only). For every organic reply it records
**ours (category + confidence) vs Smartlead native vs where it actually forwarded**, then prints the
confidence distribution and a threshold counterfactual.

**It persists to a ledger** (`wf2-calibration-ledger.jsonl`, keyed by execution id) because n8n
retains only ~13 hours of executions - 250 rows spanned 13.0h and were still paginating. Reading
on demand would keep losing the early half of the sample. Re-running is idempotent.

    python wf2_calibration.py                # ingest new executions + report
    python wf2_calibration.py --report-only  # report from the ledger only

### First reading - 9 genuine organic prospect replies

| | |
|---|---|
| confidence range | **all >= 0.80**, lowest 0.84 |
| below the 0.70 threshold | **0 (0%)** |
| routed to Melisa for review | **0** |
| forwarded to the campaign owner | 7 (78%) |
| deliberately not forwarded (Out Of Office) | 2 (22%) |
| agreement with Smartlead's own labeller | **7 / 7 = 100%** |
| cost | mean 904 tokens/classification |

**So 0.70 is not sending too much to Melisa - on real prospect replies it sends nothing.** The 0.62
"Sounds good, thanks for reaching out!" was Nik's own reply, and his read was right: it is atypically
terse, and it is the only sub-threshold score in the whole sample. 21 more replies to reach 30.

### The instrument was wrong three times before it was right - worth recording

Its first outputs would have misled exactly the decision it exists to inform:

* **50% agreement** was fabricated. Older rows store `reply_category` as the raw numeric id (they
  predate the id->name fix), so "Meeting Request" was compared against `2` and counted as a
  disagreement. Five of eight "disagreements" were actually agreements. Categories are now resolved
  through `category_map` at REPORT time, so rows already banked get corrected.
* **My own probe leads were in the sample** - `pii-ef1d7dcd@example.invalid` x5 and three `*@wf2test.invalid`.
  Excluded, and the exclusion is derived at report time too, so widening the rule reaches old rows.
* **"gate not reached 50%"** made half the sample look broken. Those were Out Of Office replies,
  which are deliberately not forwardable. Attribution now reads the `forwardable_categories` list
  from CONFIG and says "not forwardable" instead of implying a dead end.

General rule this settled: keep the ledger raw and normalise at report time. Every one of these fixes
reached data that had already been written.


---

# CLASS SWEEP + WF-2H REPAIR + S5 v2  (2026-07-30, 15:00-15:15Z)

## 1. The S1 class sweep - `wf_item_guard.py`

A shared, GRAPH-AWARE guard rather than a node patch. A blanket ban on `$('X').item` would have been
wrong: WF-2 uses it in **183 places** and has run correctly for thousands of executions, because its
chain is single-item (one webhook payload per run). The defect exists only DOWNSTREAM OF A FAN-OUT,
where n8n can no longer infer which upstream item a node is paired with.

So the guard: find nodes that emit multiple items without preserving pairing -> propagate "multi"
downstream -> flag `.item` inside that region. It is wired into `validate()` for WF-2, WF-2S and
WF-2H, so no builder can ship a carrier again.

| workflow | mode | verdict |
|---|---|---|
| WF-2 | enforce | clean (183 `.item`, none in a fan-out region) |
| WF-2S | enforce | clean |
| WF-2H | enforce | **was 5 violations** -> repaired -> clean |
| WF-1 | report-only | clean (114 `.item`, no fan-out anywhere) - the class does not exist there |

**The guard was wrong twice before it was right, and only calibration caught it.** First version
matched any `.map(` in a body and declared WF-2 a 162-violation disaster. Second version had an
off-by-one in its own string scan and reported EVERY workflow clean - including one I knew was
broken. The fix was to hold two empirical targets at all times: WF-2 must come out clean (proven
working), WF-2H must come out dirty (proven broken every run). A guard with no calibration target is
just an opinion.

## 2. WF-2H repaired - and it has now succeeded for the first time in its life

Two defect classes, both already found and fixed in WF-2S months of work earlier, never carried over:
* **S1** - `$('CONFIG').item` in `SL Stats`, `PD Leads`, `Quality Digest`, `WF-2H Digest` (and the
  Slack channel expression), all downstream of the `Pick Active` fan-out.
* **S2** - `Pick Active` read `$json` from the SPLIT `/campaigns` array, so it saw campaign #1 only.

`slack_first()` moved into the shared branch library; WF-2H now builds its Slack node from it.

**First successful execution: 12282.** Digest posted to `C0B8GCVNR5W` (`ok=true`,
ts 1785423023.004189):

```
:bar_chart: *WF-2H daily digest*
Smartlead ACTIVE campaigns: 4 · stat rows: 891
Pipedrive leads touched in the window: 0
labels — cold 0 · responded 0 · DNC 0
```

4 campaigns / 891 rows matches Smartlead ground truth exactly. Restored to the canonical daily
07:15 trigger afterwards (deployed trigger verified byte-equal to the built artifact).

### NEW defect found by that first digest - NOT fixed, outside the GO

`Pipedrive leads touched in the window: 0` is **not trustworthy**. `PD Leads` calls
`/v1/leads?limit=500&archived_status=all`, which returns the FIRST page in insertion order - the 500
oldest leads - and the node then filters them to the last 24h, which will essentially always yield 0.
This is the same pagination trap that made my earlier "0 new leads" zero-writes claim wrong. The
digest will keep reporting a confident, meaningless zero until the query is fixed (sort by add_time
descending, or filter server-side). Flagging rather than fixing: the GO covered two named repairs.

## 3. S5 v2 - previous-cycle tracking, plus a hard cap

v1 keyed the campaign tail on `updated_at within lookback`. Smartlead bumps that field in BULK - all
four ACTIVE campaigns carry the identical timestamp - so it dragged in up to **23 campaigns / 8219
statistics rows** per cycle, 5.75x the API calls and 9.2x the memory, every row stale and discarded.
Prime suspect for the worker OOM that also killed a concurrent WF-1 execution.

v2 asks the only question that matters: **was this campaign ACTIVE when we last looked?** State is
ours, so no bulk timestamp can inflate it. Recorded BEFORE the cap is applied, so capping can never
lose a tail (locked by CAP3).

`max_campaigns_per_cycle: 8` is OOM insurance independent of predicate correctness, ACTIVE campaigns
are ordered ahead of finished tails, and any overflow is REPORTED in the ops post - never silent.

**First cycle on the new build (12284): 4 campaigns polled, overflow 0** - down from 6 on the old
build in the immediately preceding cycle, and from 23 at its worst.

## 4. The guard gets a guard - WF-2H watchdog inside WF-2S

WF-2H is daily and cannot observe its own failure; it failed every run of its life and only a manual
sweep noticed. WF-2S runs every 15 minutes, so it now watches:

* `WF-2H Watch` -> n8n API, last SUCCESSFUL WF-2H execution (read-only, own credential
  `3dbKbrfihcGrOJck`, no key in the workflow JSON)
* hangs off **CONFIG**, not off the send-processing chain, so it runs on IDLE cycles too - a watchdog
  that only speaks when other work happens is not a watchdog (locked by WD4)
* **no successful run on record counts as STALE**, not unknown (WD1)
* threshold 48h -> Slack alarm that says what is now unprotected, not just that it fired
* the normal cycle summary carries `WF-2H last success: Xh ago`

Live proof in 12284: `{"__wf2h_last":"2026-07-30T15:00:24.428Z","__wf2h_hours":0,
"__wf2h_stale":false}` -> OK branch taken, no false alarm.

## 5. Test position

| suite | statics | mutants |
|---|---|---|
| WF-2 | 227 | 69 |
| WF-2S | **62** (S5 v2, CAP1-3, WD1-7) | **40** |
| WF-2H | **14 (new - it had none)** | **8 (new)** |

Deploy window respected throughout: WF-2S paused -> deploy -> WF-2 webhook verified 200 -> unpause,
for both the main deploy and the schedule restore. WF-2's built artifact hashed identical to what was
already deployed (`c9d0fd83...`), so it was NOT redeployed. WF-1 `da23d080` unchanged.


---

# WF-ERR v2 + WF-2H DIGEST FIX  (deployed 2026-07-30, one window)

## Banned class: unordered list reads used for counting  (THIRD STRIKE)

**RULE: any `/v1` list read whose result is COUNTED, filtered by time, or asserted on must prove its
ordering. An unsorted page is not a sample - it is the oldest page.**

Verified live 2026-07-30: `GET /v1/leads?limit=500&archived_status=all` returns rows starting at
`add_time 2023-05-02T20:58:13`. Adding `&sort=add_time%20DESC` returns `2026-07-30T10:09:43` first,
and the returned page was checked to be monotonically descending before this rule was written.

Three occurrences, all of them producing confident wrong answers rather than errors:
1. a 6000-lead Pipedrive sweep that was oldest-first and missed the entire Smartlead era
2. my "0 leads created since 17:25" zero-writes claim, which was read off the oldest page while
   three new leads demonstrably existed
3. WF-2H's digest line `Pipedrive leads touched in the window: 0` - wrong for the workflow's whole life

Also: a page where EVERY row falls inside the window is saturated, and the true count is higher.
Saying "500" then is the same quiet lie. WF-2H now appends "(page saturated - true count is higher)".
Locked by H-PG-1..4.

## WF-ERR v2 - actionable reports

12 nodes, deterministic, `9949e6e4`. v1 said what failed; v2 answers what happened, what is lost,
and what to do.

* **WHAT** - workflow, node, and the event behind it (type, campaign, lead) read from the failed
  execution's runData.
* **IMPACT** - which writes actually COMPLETED before the failure, plus the retry verdict for that
  source: WF-1 -> DELAYED (HeyReach retries 5x/24h), WF-2 -> **LOST** (we answer 200 before
  processing, so Smartlead never retries), WF-2S -> SAFE (marked seen only after a successful
  replay), WF-2H -> DELAYED.
* **ACTION** - from a documented `known_classes` dictionary: paired-item routes straight to
  `wf_item_guard.py`; OOM is named an instance event, not a workflow defect; 5xx says *no action*.

The Error Trigger carries no runData, which is precisely why v1 could never speak to impact. v2
fetches the failed execution through the read-only n8n API credential; if that fetch fails the report
says writes are **UNKNOWN** rather than inventing "no writes".

**Unknown classes** get an LLM hypothesis, always prefixed `:robot_face: hypothesis, not fact`, with
a concrete first check. HARD GUARDRAIL: the LLM node is `continueRegularOutput` and Compose degrades
to the plain report on any failure or bad parse - error reporting must never depend on the LLM being
up (E11, E12, and mutants 8/9).

**Privacy**: only node name, error text, event type and campaign name leave the workflow. No
payloads, no secrets (E13 + mutant 10).

**Burst**: one message per (workflow, node) per 15 minutes; the next window reports `+K more
suppressed`. The Lead List lavina would now be 1 message, not 24. Store pruned at 24h.

Tests: **22 statics / 15 mutants**, all passing. `node wferr_static_contract_tests.js --show`
prints the before/after gallery for all six historical fixtures.


---

# B27 duplicate-person selection + S5 v3  (deployed shadow 2026-07-31)

## B27 - the flip blocker, fixed

Pipedrive holds **3 person records** for pii-c61c7d08@example.invalid. All four resolvers took the first
search hit; `Person Pick` / `R Person Pick` at least verified the email, while **`B Lead Ctx` and
`U Lead Ctx` took `items[0]` with no email check at all** - a fuzzy match could have been a different
person entirely. The lead read was then filtered by that one person_id, so a lead hanging off a
different duplicate was invisible: 6 of 7 matrix replies lost their label union and activity, and the
first-reply gate failed open (T7) because it reads labels off the lead.

**Fixed, one call, no fan-out:**
1. the pickers stop deciding - they emit every email-verified candidate, oldest first
2. all four lead reads drop `person_id=` and add `sort=add_time DESC` (ordering rule)
3. the matcher takes this campaign's lead from among leads held by ANY candidate, then **ADOPTS**
   that lead's person_id - the lead is the authority, not an unstable search ordering
4. no lead anywhere -> oldest candidate stands (genuinely new prospects, T1-style)

Matching on campaign alone would have been wrong: the unfiltered page holds other people's leads for
the same campaign, so the rule is (campaign matches) AND (lead.person_id is one of our candidates).
Person search widened 5 -> 20, because a cap of 5 can hide duplicates.

This SELECTS among duplicates; it does not MERGE them. Deduplicating the base is a separate backlog
item - real dupes exist (Lule, Person-45bca53f).

## The guard blocked my own build twice, and was wrong both times

Worth recording because the guard is now load-bearing:
* it called a single-item return a fan-out because `cands.map(c => c.id)` appeared INSIDE the returned
  object - 183 false positives. Fixed: what matters is the number of TOP-LEVEL elements in the
  returned array, not expressions inside them.
* it matched `return` statements inside nested helper functions. Fixed: only the node body's
  top-level returns decide item count.
Calibration held throughout: WF-2 must be clean, WF-2H (pre-fix) must be dirty.

Also found a real harness gap: the WF-2 test stub implemented only `.item`, so any node using
`.first()` fell into its own catch and behaved as if the node were absent. Now supports
`.item`/`.first()`/`.all()`.

## S5 v3 - the T2 hole closed

v2 could only catch a campaign it had SEEN ACTIVE. Matrix T2 started AND completed at 07:10:30,
between the 07:00 and 07:15 polls, so it was never in `prevActive` and its SENT was never reconciled.
v3 also admits campaigns whose **`created_at`** is inside the lookback. `created_at` is immutable, so
unlike the bulk-bumped `updated_at` that v1 wrongly trusted it cannot drag in dead campaigns.

Tests: WF-2 **238 statics / 76 mutants**, WF-2S **66 / 43**. Guard: no carriers. Deployed in SHADOW.

## COMPLIANCE FINDING - production email has no unsubscribe link at all

Checked while preparing T12: the live Ai4 sequence carries only `{{first_name}}` and
`{{company_name}}` - **no unsubscribe merge tag** - and the campaign's `unsubscribe_text` is empty.
So no outbound Janea email currently offers an opt-out link. That is why Nik could not find a button
in the matrix emails: there is none, anywhere in production.

Two consequences:
1. **T12 cannot be exercised as specified.** A real link click needs a link. The UNSUBSCRIBED webhook
   path can still be proven synthetically (as the T11 bounce was), but that tests our handler, not the
   production email shape.
2. This is a deliverability and compliance question for the team, not a workflow defect - worth
   raising with Melisa/Nik separately.


---

# INCIDENT - live window left open ~72 hours (2026-07-31 08:43Z -> 2026-08-03 08:59Z)

I committed to "revert immediately after" the residual re-run and did not. The session ended with
the window open and I did not close it; it was closed only when the next task began, 72.25 hours later.

**What was live the whole time:** `WRITE_MODE=live`, `forward_owner_map.Chrissy -> pii-c61c7d08@example.invalid`,
`forward_review_address -> pii-c61c7d08@example.invalid`, WF-2S scoped to the 3 residual campaigns.

**Effect on real traffic:** 16 organic REPLIED executions processed LIVE with real writes
(SL Category, SL Forward Email, Reply Activity, Lead Labels Union). Those writes are legitimate work
WF-2 would do after the flip, so the CRM state is not wrong - but it happened without a supervised
window, and organic SENT went unreconciled the whole time because WF-2S stayed scoped to 3 test
campaigns.

**The part that is actually harmful:** `forward_review_address` pointed at a personal Gmail for 72
hours, so every low-confidence organic reply was forwarded there instead of to Melisa. Confirmed at
least twice: exec 12644 (confidence 0.62) and exec 12884 (0.61). Those prospect replies reached Nik's
personal inbox and did NOT reach Melisa's review queue.

**Owner-path forwards** resolve by sending inbox, and the Ai4 campaigns send from Rune/Mario inboxes,
so the Chrissy remap should not have diverted them - stated as expectation, NOT verified per-message.

**Process fix:** a live window must carry an expiry, not a promise. Either WF-2S posts a
"WRITE_MODE has been live for N hours" warning on every cycle (it already runs every 15 minutes and
already watches WF-2H, so this is a two-line addition to the same node), or the window is opened with
a scheduled revert. A commitment to remember is not a control.

## Silver lining - T7 proven

exec 12812: second reply on a FOUND lead (`lead_how=title_prefix`, `no_lead=false`),
`alert=false / reason=repeat_reply`, `Reply Alert` did NOT post, and CRM writes still happened
(SL Category, SL Forward Email, Reply Activity). **T7 passes** - and it only works because B27 makes
the lead findable, which is exactly why it failed last run.

# HeyReach send capability - partial recon

* `POST /inbox/SendMessage` **EXISTS**: it answered `404 {"errorMessage":"This conversation does not
  exist"}` - a semantic rejection, not a missing route. Compare `/inbox/GetConversations`, which
  returned a bare 404 with an empty body (route absent).
* So sending is keyed on a **conversation id**, which raises the real question for this blast: an
  accepted connection that has never been messaged has no LinkedIn conversation thread. Whether
  HeyReach can create one via API is UNANSWERED and is the gate for Phase 2.
* Confirmed working reads: `campaign/GetAll` (6 campaigns), `li_account/GetAll` (4 senders),
  `MyNetwork/GetMyNetworkForSender` (needs SenderId), `stats/GetOverallStats` (needs AccountIds +
  CampaignIds).
