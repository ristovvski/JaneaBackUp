# Operator runbook

For someone taking over the GTM automation estate who has **never talked to Nik**. It says what to
look at, how to tell healthy from broken, how to change something without breaking production, and
what never to do. Everything here is written from the live estate as of 2026-09-24.

Read [`ACCESS_MAP.md`](ACCESS_MAP.md) first — it lists what you can and cannot see, and some of the
checks below need access you may not have yet.

---

## 1. What the estate is, in one screen

Prospects are contacted through two outbound tools. Everything they do comes back as a webhook and
is turned into CRM records, Slack alerts and suppression-registry rows.

| workflow | trigger | what it does |
|---|---|---|
| **WF-1 HeyReach Receiver** | webhook | LinkedIn events (invite, accept, reply) → Pipedrive person/lead/activity, alert, DNC row |
| **WF-2 Smartlead Receiver** | webhook | email events (sent, reply, bounce, unsubscribe) → same, plus an LLM reply classifier |
| **WF-2S** SENT reconciler | every 15 min | Smartlead never sends `EMAIL_SENT` to us — this polls for sends and replays them into WF-2 |
| **WF-2R** REPLY reconciler | every 15 min | replays replies WF-2 missed (outages, drops) |
| **WF-2H** Health & Digest | 07:15 | health summary for the Smartlead side |
| **dnc_morning_digest** | 07:00 | the one-screen daily status of the whole estate |
| **WF-ERR** Error Handler | on error | every workflow's failures land here and are posted |
| **dnc_*** (≈18) | mixed | the DNC suppression registry: capture, projections into Pipedrive/Smartlead, Supabase mirror, pruning |
| **WF-ICP-Score [DEV]** | webhook | company ICP scoring, Phase 1 — DEV only, see `icp-scoring/` |

Shared state lives in the n8n **data table** `euyostwJYfJefItC` (the "claims table"). Workflow
staticData is **not** safe for anything that runs concurrently — see §5.

The definitive technical reference is
[`docs/WF1_W1.0.1_build/wf1-system-reference.md`](docs/WF1_W1.0.1_build/wf1-system-reference.md).
The standing rules are [`docs/RULEBOOK.md`](docs/RULEBOOK.md). The decision history — why things are
the way they are — is [`chat-history/RULINGS_AND_INSTRUCTIONS.md`](chat-history/RULINGS_AND_INSTRUCTIONS.md).

---

## 2. Every morning (≈10 minutes)

Do these in order. **A missing post is itself a failure** — the digest is designed to post every day
including a wholly green one, so silence means the job did not run.

1. **The morning digest** — Slack channel `C0BTP6VHP1B`, posted 07:00. One line per area; each line
   is green / amber / red. It prints `unreadable` instead of a number when it could not measure —
   treat `unreadable` as red, never as zero.
2. **`#alerts`** (`C0BTUHSSM3K`) — system alarms from WF-1 / WF-2 / WF-ERR. One webhook-secret
   notice a day is expected and known (`CONFIG.webhook_secret_sha256` is unset). Anything else is
   worth opening.
3. **WF-ERR** — every error from every workflow. If the same node errors every run, it is a defect,
   not noise: five digests were once lost to a single dangling node reference, and WF-ERR reported
   all five.
4. **WF-2H** (07:15) — the Smartlead-side health line.
5. **`#lead-processing`** (`C07LTD8UT70`) — the team's live lead alerts. You are not the audience,
   but glance: an alert whose reply line reads
   `[no text — manually check the inbox; could be an attachment or an empty connection-accept]`
   is **by design** — open the conversation in HeyReach and decide (§6).

If the digest is missing entirely, open `dnc_morning_digest`'s latest execution first (§3).

---

## 3. How to read an execution

In the n8n UI: workflow → **Executions** tab → click one. Each node shows its input and output
items. Three traps catch everyone:

* **The unfiltered execution list lies.** It omits crashed executions and under-reports successes
  (measured: 4 listed vs 172 real errors). Filter by status (`error`, `running`) explicitly. On
  2026-09-08 a live sweep was absent from the default list while running for 11 minutes.
* **`$json` does not survive an HTTP node.** After any HTTP request, the item is the API response;
  every field you set before it is gone. Nodes recover context by name — `$('Node Name').item.json`.
  If a field is "missing", check which node was supposed to own it.
* **A node with two inputs fires once per input**, not once merged. `Merge (append)` is not a
  barrier. If something ran twice, look for a node fed from two places.

Via the API (for scripting): `GET /api/v1/executions?workflowId=<id>&status=<s>` then
`GET /api/v1/executions/<id>?includeData=true`. Node outputs are at
`data.resultData.runData["<Node Name>"][0].data.main[0]`.

---

## 4. How to deploy a change

This is the process. Do not shortcut it: every step exists because skipping it once caused an
incident, and several of those are written up in `docs/task-logs/`.

1. **DEV copy.** Duplicate the workflow in n8n as `DEV__<name>`, inactive, pointed at test channels.
   **Honest note:** as of today no `DEV__` copy of WF-1 or WF-2 exists — the only DEV workflow is
   `WF-ICP-Score [DEV]`. Your first change will need to create one.
2. **Statics.** A patch script that (a) reads the live workflow, (b) edits it, (c) runs the edited
   node code in `node` against realistic fixtures **before** any write. Every static suite must
   include a **non-vacuity** case — the OLD code must fail the test — or a green result proves only
   that the harness is lenient. Patterns: any `p_*.py` in `docs/WF1_W1.0.1_build/`.
   **Fixtures must be copied from a real payload on the wire**, never reconstructed from what the
   code expects. A synthetic attachment fixture once certified a gate that silenced a real reply.
3. **safe_patch.** Deploy with `safe_patch_workflow()` from
   `docs/DNC_OBS_P1_build/patch_utils.py`. It diffs live against local in **both** directions and
   aborts on any node added or removed that the patch did not declare — live workflows drift between
   sessions. Always strip UI-only settings keys before a PUT (`n8n_deploy_util.put_body`): a rejected
   PUT **deactivates** the workflow, so a failed deploy is an outage, not a no-op.
4. **Verify live.** Re-read the workflow after the PUT; assert the change is present **in code, not
   in comments** (strip `//` lines before asserting — comments that name the old value have
   false-alarmed three times), node count as expected, workflow still ACTIVE.
5. **Wire-proof.** Wait for the next real event through the changed path, open that execution, and
   confirm the new behaviour. Until then the change is "deployed", not "working".
6. **Task log.** Every change writes `docs/task-logs/YYYY-MM-DD_<slug>.md`: done / partial /
   blocked / improvable. Not optional.

**Any write touching more than 10 records** (a backfill, a repair) pre-posts first: counts, 3–5 real
example rows, and the artifact path — then waits for a human go, then fires in chunks, then
post-verifies by reading the records back (§9f.2 in the rulebook).

---

## 5. The never-list

Each of these has cost something real.

* **Never post to `#infra-issues`.** Humans only. Not answers, not status, not one line.
* **Never read, react to, or post in `#agent-inbox`.** Tasks come from Nik directly.
* **Never delete a workflow involved in an incident.** Deactivate and keep it until it is audited.
* **Never enable `FIRE_SMARTLEAD`** on `dnc_projections_sweep` until the reason-based split exists.
  Its eligible set includes employee connections, and Smartlead unsubscribe cannot be undone.
* **Never derive a person's name from an email address.** Provider truth or nothing.
* **Never remove a Pipedrive label.** Labels are cumulative; always read-then-union. Four Zaps once
  spent 24 days silently stripping `3. Responded`.
* **Never keep concurrent state in workflow staticData.** It is saved as one object at execution end;
  overlapping executions overwrite each other. Use the claims table.
* **Never trust an unsorted Pipedrive `/v1` list read for counting.** It returns the OLDEST page
  first — 20,000 rows once came back spanning 2023–2025 with zero from the current fortnight.
  `/v1/leads` also ignores `archived_status` everywhere.
* **Never reference a data table by name** in a node (`mode: "name"`). Use `mode: "id"`.
* **Never fire an irreversible projection** (Smartlead unsubscribe, bulk label change) without a
  dry-run count taken the same day.
* **Never commit anything from `gtm_docs_export/_*`, `scrub.sed`, or a `.env`.** See `SECURITY.md`.

---

## 6. Recurring situations and what they mean

| you see | it means | do |
|---|---|---|
| alert `Reply: [no text — manually check the inbox…]` | a textless LinkedIn reply: usually a connection-accept surfacing as a reply, sometimes a real attachment | open the conversation in HeyReach (not the list — the list captions any textless message "Attachment(s)") and decide |
| a lead owned by **Melisa Bahonjic** | known: both receivers stamp one fixed owner (`CONFIG.melisa_user_id` / `CONFIG.owner_id`) on everything they create | not a regression; a decision for Nik |
| `Company LinkedIn:` in an alert | the company URL was a LinkedIn page, not a website | correct since 2026-09-22 |
| a new HeyReach campaign is silent | webhooks are scoped to a list of campaign ids | run `node ops/heyreach_webhook_scope.mjs --apply` — **after every new campaign** |
| digest line reads `unreadable` | the digest could not measure it | treat as red; open the digest's execution |
| a reply alert fired once for two replies | the alert is keyed per person per campaign — by design, first reply only | nothing |

---

## 7. Where each secret lives

**Names only.** No value appears in this repository — see `SECURITY.md` for how that is enforced.

| secret | where it lives | used by |
|---|---|---|
| Pipedrive API token | n8n credentials `Pipedrive account`, `Pipedrive API (DNC projections)`; local `.env` `PIPEDRIVE_API_TOKEN` | receivers, DNC projections, scripts |
| Smartlead API key | n8n credentials `Smartlead API`, `Smartlead API (DNC projections)`; `.env` `SMARTLEAD_API_KEY` | WF-2, reconcilers, projections |
| HeyReach API key | n8n credential `HeyReach API (DNC S4)`; `.env` `HEYREACH_API_KEY` | DNC S4, `ops/heyreach_webhook_scope.mjs` |
| n8n API key | n8n credential `n8n API (WF-2S watchdog)`; `.env` `N8N_API_KEY` | watchdogs, every deploy script |
| Slack bot tokens | n8n credentials `Smartlead Slack`, `Heyreach Slack` | every alert and digest |
| OpenAI API key | n8n credential `OpenAI API`; `.env` `OPENAI_API_KEY` | WF-2 reply classifier |
| Supabase | n8n credential `Supabase account` | DNC mirror (delta pusher, nightly reconcile) |
| Clay API key | `.env` `CLAY_PUBLIC_API_KEY` | ICP scoring, Clay CLI |
| Make API token | `.env` `MAKE_API_TOKEN` | legacy scenario audits only |
| **webhook paths** | n8n — each Webhook node's `path` | **the path IS the credential** for every webhook: anyone holding it can inject events. They appear here only as `{{WEBHOOK_…}}` placeholders. |
| webhook shared secret | `CONFIG.webhook_secret_sha256` in WF-2 — **currently unset** | would authenticate Smartlead's posts |

The local `.env` lives on the operator's machine only (`Нова папка\.env`) and is loaded by
`load_env.ps1`. It is gitignored and the export gate fails closed if any of its values reach a
staged tree.
