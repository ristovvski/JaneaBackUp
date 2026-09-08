# WF-1 lead-selection disagreement — settled, fixed, and swept

> **STATUS 2026-09-03: FIXED and verified. No repair needed — the bug never fired.**
> The one-line fix is deployed (WF-1 versionId `0c6fa377`), a class static now enforces the rule
> estate-wide and passes, and a 10,000-lead sweep covering 19 May – 3 Sep found **zero** damage.
> See §7–§9. The analysis below is what was found before the fix.

**2026-09-03. Read-only: every call was a `GET`. Nothing deployed.**

---

## The answer in four lines

1. **Yes, it is real.** Five named people in the current window where the two rules pick different leads.
2. **The campaign-match rule is correct.** Five of the six lead selectors in WF-1 use it; the label step is the only outlier.
3. **Exposure is small but not zero:** 13 people hold 2+ live leads in the visible window; **5 of them are actually divergent**; only **1** holds two campaign leads.
4. **The fix is one line** — and it deletes a duplicate implementation rather than adding one.

---

## 1. The two rules, from the live definition

`WF-1`, versionId `7e3e86cf`, 130 nodes. Both run on the **same** input — the response to
`GET /v1/leads?person_id={id}` — and both filter out archived leads. They differ only in which
survivor they pick.

**`M7 Build`** — feeds the alert, the reply activity, and the follow-up task:
```js
.filter(l => !l.is_archived)
.find(l => (l[_campKey] ?? null) === _want)      // W1.0.11 lead-per-campaign match
```

**`M7 Labels Compute`** — feeds the label PATCH:
```js
.filter(l => !l.is_archived)
.sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0]    // newest
```

So on a reply: **the activity and the Slack alert go to the campaign's lead; the labels go to
whichever lead is newest.** When those are not the same record, *3. Responded* — the handover
trigger — lands on the wrong lead, and the right lead never gets it.

## 2. Which rule is correct — not a judgement call

| Selector | Rule used |
|---|---|
| `Select Existing Lead` (invite path) | campaign-match |
| `M5 Labels Compute` (accepted path) | campaign-match |
| `M6 Build` (message path) | campaign-match |
| `M7 Build` (reply path) | campaign-match |
| **`M7 Labels Compute`** (reply labels) | **newest — the only one** |

**Five of six agree.** One lead per campaign is the estate's rule; the label step simply never got
it. The acceptance path (`M5 Labels Compute`) does the same job correctly, which is the cleanest
proof that the label step is the outlier and not a deliberate exception.

## 3. How far it goes in practice

Measured against the live CRM: a 4,000-lead window, newest-first, non-archived — **3,971 distinct
people**. The window rows already carry the campaign field, so this is an exact census within the
window, not a sample.

| | Count |
|---|---:|
| People with **2+ live leads** | **13** |
| …of whom hold **2+ campaign leads** | **1** |
| …1 campaign lead + at least one non-campaign lead | 8 |
| …no campaign value on any lead | 4 |
| **Confirmed divergent person + campaign combinations** | **5** (5 distinct people) |
| → labels would land on a **non-campaign** lead | 4 |
| → labels would land on a **different campaign's** lead | 1 |

### A false negative worth recording
A random sample of 250 people found 14 with 2+ live leads and reported **zero** divergence. That is
wrong, and the reason matters: **divergence needs at least one campaign-valued lead to compare
against**, and most multi-lead people have none — their leads were created by other systems that
leave the campaign field empty. The check had nothing to compare and returned a clean answer.

*A measurement that cannot see the failure reports success.* The exact census above replaced it.

### The five, by name

| Person | Reply arrives on | Activity + alert → | Labels → | The wrong target is |
|---|---|---|---|---|
| Person-f66730e9 | `[Events Visiting] [Ai4 2026] - Rune` | `726f7990…` | `e4ed9130…` | an inbound **website** lead |
| Person-d9edfa87 | `[Events Visiting] [Ai4 2026] - Mario` | `d0791bd0…` | `bdacf0a0…` | an inbound **website** lead |
| Person-520c7d97 | `[Events Visiting] [Ai4 2026] - Mario` | `79c6c610…` | `b04d3f10…` | the **Smartlead** lead (no campaign) |
| Person-55be653b | `[Events Visiting] [Ai4 2026] - Mario` | `b281a5d0…` | `94e3bab0…` | the **Smartlead** lead (no campaign) |
| Person-d7e943a5 | `[Events Visiting] [Ai4 2026] - Mario` | `269d1e00…` | `98e9f5b0…` | a **duplicate of the same campaign** |

**The worst shape is the first two.** A LinkedIn reply would put *3. Responded* on somebody's
**inbound website lead** — a record that has nothing to do with the campaign — and *Responded* is the
handover trigger. Meanwhile the campaign lead that actually received the reply keeps only *Cold*.

**Person-d7e943a5 is a second finding.** He holds **two live leads with the identical campaign value**,
created 27 July and 5 August. That breaks one-lead-per-campaign on its own, independently of this
bug, and it is why `find()` and "newest" disagree for him. Worth a separate look at how a duplicate
got created.

## 4. Has it actually fired?

I could not prove it either way. A divergence only bites when a **reply** arrives for one of these
people on the non-newest campaign, and the execution window is ~20 days while these leads span July
and August. What is certain is that the exposure is live right now: five people are in a state where
the next LinkedIn reply mislabels a lead.

## 5. The one-line fix

Do not re-select. The lead has already been chosen correctly one node earlier.

In `M7 Labels Compute`, replace the whole `selectLead` function and its call with:

```js
const lead = ($('M7 Lead Get').item.json.data || [])
  .find(l => l.id === $('M7 Build').item.json.lead_id) || null;
```

This makes the labels follow the same record as the activity and the alert **by construction**, and
it removes the sixth lead-selector from the workflow rather than adding a fifth copy of the right
one. Everything downstream — the `__invalid` / no-lead branch, the effective-rank calculation, the
union — is unchanged.

**Verification after deploy would be:** the same census re-run, expecting zero divergent
combinations, plus one execution on a two-campaign person showing the same lead id on the activity
and the PATCH.

**Deployed 2026-09-03**, WF-1 versionId `7e3e86cf` → `0c6fa377`, 130 nodes, still active.

## 6. Two things this leaves open for you

- **Person-d7e943a5's duplicate campaign lead.** One-lead-per-campaign was violated. Is that a
  historical artifact from before W1.0.11, or can it still happen?
- **The four people whose newest lead has no campaign at all.** Those leads come from other systems
  that leave the campaign field empty. That empty field is what makes them "newest and unmatched",
  and it is the same gap that makes several other measurements in this estate harder than they
  should be.


---

# 7. The fix, as deployed

`M7 Labels Compute` no longer re-selects. Its `selectLead` function is gone; in its place:

```js
const lead = ($('M7 Lead Get').item.json.data || [])
  .find(l => l.id === $('M7 Build').item.json.lead_id) || null;
```

WF-1 `7e3e86cf` → **`0c6fa377`**, 130 nodes, still active. Backup in
`WF1_LEADSELECT_FIX_2026-09-03/backups/`.

**One behaviour change worth stating plainly.** When there is no campaign-matching lead, this node
now writes **no labels at all**, where before it labelled whichever lead was newest. That is the
correct behaviour and it makes labels consistent with the reply activity, which already declines to
write in exactly that case — but it does mean a person whose only lead carries an empty campaign
field will no longer be labelled by the reply path. The root cause there is the empty campaign
field, not this node.

**Also observed on this deploy:** the write stripped `timeSavedMode` from the payload, and a
read-back shows **it is still present on the workflow**. That re-confirms trap B11 live — omitting
the key does not clear it server-side; it must be stripped on every single write.

# 8. The class static

New: `WF_SHARED/static_lead_selection.js` — *one lead decision per execution; nothing re-selects.*

It distinguishes **policy selection** (decides which lead the event is about — campaign match or
newest; at most one reachable per execution) from **id resolution** (looks up an id already decided
upstream — always allowed, and it is the fix).

| | Result |
|---|---|
| Before the fix | **FAIL** — 1 violation: `M7 Build (campaign-match)` vs `M7 Labels Compute (newest)` |
| After the fix | **PASS** |

**It found two false positives in itself first, and both are worth recording.** The first version
grouped nodes by an `M5`/`M6`/`M7` name prefix — WF-1's convention and nothing else's — which lumped
WF-2's four event branches into one bucket and reported four selectors racing when each is the only
selector on its own branch. It also reported the archived copy of WF-1 for ever. Both are fixed:
grouping now comes from the **graph** (two nodes reached from different outputs of the same gate can
never both run), and `ARCHIVE__*` workflows are skipped.

*A static whose grouping is a naming convention reports defects that are really spelling.*

### The sweep for other re-selection
Across all live workflows there are now **8 policy selectors**, every one campaign-match:

| Workflow | Selectors |
|---|---|
| WF-1 | `Select Existing Lead`, `M5 Labels Compute`, `M6 Build`, `M7 Build` |
| WF-2 | `Lead Select` (sent), `Lead Resolve` (reply), `B Lead Select` (bounce), `U Lead Select` (unsub) |

WF-2's four are mutually exclusive branches of one switch, confirmed from the graph — not a
violation. **No other re-selection exists in the estate.**

# 9. Repair — not needed, and here is the proof

The damage this bug writes has a specific signature: **a live lead carrying *3. Responded* with no
campaign value, whose person also holds a campaign lead.**

Swept over **10,000 leads, 2026-05-19 → 2026-09-03** (9,981 live leads with a person, 9,940 people):

| | Count |
|---|---:|
| Live leads carrying *3. Responded* | 199 |
| …with no campaign value | 103 |
| **…AND whose person also holds a campaign lead — the signature** | **0** |
| The five latent-divergent people: does the wrong target carry *Responded*? | **none of them** |

**The bug was latent. It never fired.** Every one of the 103 *Responded*-without-campaign leads
belongs to somebody who holds no campaign lead at all, so none of them can be this bug — they are
leads created by other systems that leave the campaign field empty.

**No §9f.2 repair artifact is needed and no labels need moving.** Had I gone straight to repair from
the five divergent people, I would have moved labels that were never wrong.

**Bounds on that claim:** the list endpoint cannot see archived leads (trap B13), so a mislabelled
lead that was later archived would not appear. And the window starts 19 May.

# 10. The duplicate-lead question — answered

**Census over the same 10,000-lead window: exactly one person holds two live leads with an identical
campaign value** — out of **2,132** campaign-bearing live leads. That is 1 in 2,132 over 3.5 months,
not a generator running hot.

**And it was not WF-1's create.** Both of Person-d7e943a5's leads carry the automation account and
WF-1's exact title convention, 27 July and 5 August — but:

| | 27 Jul | 5 Aug |
|---|---|---|
| `channel_id` | **`"HeyReach"`** | **`null`** |

WF-1's create sets `channel_id` from its settings on **every** lead it makes. The second one does not
have it, so it did not come from that node. Same title convention, same automation account, no
channel id — Make or a backfill is the likely author. **WF-1's guard held.**

**Can it still happen today? Yes, in principle — the guard is check-then-act.**
`Lead Search` reads the person's leads, `Lead Create Gate` decides "no campaign lead exists", and
`Create Lead` writes. Nothing is atomic between the read and the write, so two executions for the
same person and campaign that overlap will both read "none" and both create.

**How exposed is that?** Lower than it looks: only the invite branch creates leads, HeyReach's
same-second fan-out is per *message* rather than per invite, and the 48-hour duplicate guard drops
repeated correlation ids. **Observed instances attributable to it: zero.**

**The guard I would add** is the one already proven this morning on the alert registry: before
creating, claim `lead|{person_id}|{campaign}` in the claims table; a second concurrent execution
finds the claim and takes the existing-lead path instead. Same table, same pattern, atomic.

**Recommendation:** fold this into the WF-2 state-port work rather than doing it separately — it is
the same mechanism, and doing both at once means one migration and one set of statics. **Not
deployed; your call.**
