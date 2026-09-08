# Impact of the AS-IS Map on Phase 1

Which shipped assumptions the verified map **confirms**, **breaks**, or leaves **at risk**.

## CONFIRMED ✅
- **Smartlead auth + base**: `api_key` query param, `server.smartlead.ai/api/v1` — every GET worked.
- **Lead categories are global** (not per-campaign) and `fetch-categories` returns them incl.
  `sentiment_type` — matches the observability design. The 3 forwardable categories Melisa named
  (Interested, Not Interested, Information Request) **all exist**.
- **WF-1 is the sole active ingest workflow**, and `lh_linkedin_profile_url` is real and ~99% populated
  on persons → the **1.1 tee's assumptions hold** (WF-1 resolves the LinkedIn URL + person id; the tee
  can consume them). The lead `Campaign` field (WF-1 lead-per-campaign key) is live at 32.6%.
- **DNC ledger identity model** is sound: LinkedIn URL is the dominant, high-quality identifier in
  Pipedrive (99.4%), so the linkedin-first waterfall matches reality.

## BROKEN / MUST-FIX ⛔

### 1. R4 delta logic — only a SUBSET of categories reaches Pipedrive (MANDATORY correction)
Shipped R4 compared **all replies** vs a categorization count. The map shows Smartlead has **10
categories**, of which only the **forwardable** ones create Pipedrive records — the rest (Out Of
Office, Wrong Person, Uncategorizable by Ai, Sender Originated Bounce, No Longer Working There, and
arguably Not Interested / Do Not Contact) **never create a Pipedrive lead**. Comparing *all* replies
to Pipedrive creations would show a permanent huge false-positive delta.

**Corrected R4 (proposed):**
```
forwardable_new  = replies in this window whose category ∈ CONFIG.forwardable   (already computed as forwardable_new)
pipeline_created = Pipedrive lead/person creations in the same window            (needs verified PD query — Q4/Q6)
R4 fires when:  forwardable_new - pipeline_created  >  r4_delta_threshold        (forwardable replies NOT landing in CRM = the real incident)
optional inverse:  pipeline_created - forwardable_new > threshold  ⇒ CRM creations from a non-Smartlead source (informational)
```
- Numerator becomes **`forwardable_new`**, NOT raw `replies` and NOT total `categorized`.
- Denominator (`pipeline_created`) requires a **verified Pipedrive creations-in-window query** — defer
  until Q6 forwarding rules + the query are confirmed. Interim: run R4 in Smartlead-internal mode
  (`forwardable_new` vs `categorized`) and label it provisional.
- **CONFIG.forwardable must be confirmed on the call** — does **Meeting Request** (positive) forward?
  Is **Not Interested** actually forwarded (Melisa listed it, but it's negative sentiment)? Lock the
  exact set (Q3).

### 2. Category-name matching bug (found via real data)
Real category names are Title Case with spaces (`"Not Interested"`), but the shipped `forwardable`
set uses snake_case (`"not_interested"`). `obs_v1.parseLeadsStatisticsV1` lowercases the category and
looks it up in `forwardableSet` — `"not interested"` ≠ `"not_interested"` ⇒ **forwardable_new would
under-count to ~0**. Fix: normalize both sides (`toLowerCase().replace(/[\s_]+/g,'_')`) or key the set
on the exact Smartlead names. Small, certain fix — pair it with the R4 correction.

### 3. `sentiment_type` casing
Live values are lowercase (`positive`/`negative`/`null`); the obs fixture used uppercase. Any logic
keying on sentiment must lowercase. (Already flagged as confirm-on-capture; now confirmed lowercase.)

## AT RISK / UNCONFIRMED ⚠️

### 4. Data Tables on prod n8n — the whole ledger storage layer
`GET /datatables` → **404** on prod's public API. We **cannot confirm** the data-table module/version
via API. If prod is < 1.113 or the module is off, `dnc_ledger`/`obs_state` **cannot be created** and
Phase 1 must fall back to the **Postgres-behind-contract** escape hatch. **Action: verify in the n8n
UI / `n8n --version` before any publish** (Q10). This is the single biggest Phase-1 risk the map
surfaced.

### 5. Smartlead has NO native webhooks — observability must stay POLL-based
Confirms the Build-5 decision to **poll** `leads-statistics` (there is nothing to subscribe to). Also
means the eventual R2/R3 (forward-gap / edge-category digest) cannot rely on a Smartlead webhook and
will need either polling of a message-history endpoint (still undocumented) or a hook into whatever
external mechanism actually moves Smartlead replies (Q1/Q2).

### 6. Single-campaign MVP is clearly insufficient — reinforces 5.1
There are **6 ACTIVE** AI4 campaigns (114 total). The shipped observability workflow polls **one**
campaign per execution (deviation D5-a). Multi-campaign iteration (postponed Build 5.1) is now
clearly required for real coverage — this map is its prerequisite, as intended.

### 7. Pipedrive → Make ("all events") interacts with the tee
Pipedrive streams **all** events to a Make scenario (opaque). When the 1.1 tee causes WF-1 to write to
Pipedrive, those writes will **also** fire the Make webhook. Before attaching the tee, confirm the
Make scenario won't loop/double-act on ledger-driven changes (Q6/Q7). No new risk from the DNC ledger
itself (it's a separate Data Table), but the tee's Pipedrive-adjacent context should be checked.

## Recommended sequence (post-call)
1. Resolve **Q10 (data-table support)** — unblocks or reroutes ledger storage.
2. Lock **forwardable set + forwarding rules (Q3/Q4)** — unblocks the corrected R4 + fixes #2.
3. Apply R4 correction + category-matching fix to `obs_v1.js`; re-run tests.
4. Then Build 5.1 (multi-campaign) on top of the corrected single-campaign logic.

## Follow-ups #2 / #3 status (this run)
- **#2 fail-loud schema guard** and **#3 Amendment 5 (`zz_probe_` on /datatables)**: not executed.
  Amendment 5's probe is **not applicable** — prod's public API has no `/datatables` endpoint (404),
  so a `zz_probe_` create/delete cannot run there; data-table support must be checked in the UI (Q10).
  The fail-loud schema guard can be added to `DNC__UpsertLedger__v1`/`CheckLedger` (a top-of-workflow
  Code node that hard-fails if the returned row is missing required columns incl. `norm_v`) — ready to
  implement on your go; it depends on Q10 being resolved first (need a real table to guard against).
