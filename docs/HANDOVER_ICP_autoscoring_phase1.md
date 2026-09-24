# Handover — ICP Auto-Scoring & Pipedrive Sync, Phase 1

Written 2026-09-09 by the duty (prod) session for whoever picks this up. Everything below is
sourced; record ids in brackets are from the Slack communication audit
(`COMMS_AUDIT_build/synthesis/03_RULEBOOK_MAP.md`), which is the only place this project is
specified at all.

## Read this first: the build is gated on a document that does not exist

> *"No ICP scope document appears anywhere in ingested material, and the whole Pipedrive ICP
> automation is gated on it."*

The rubric was **"version 5, still work in progress"** on 2026-07-10 and the per-option scores were
never delivered [R0642, R0645]. **ICP definition is owned by Chrissy; Lilla Szabo was a temporary
stand-in and expected to hand back** [R0639, R0653] — so the specification has no continuous owner.

**Do not invent the criteria.** A scorer built on guessed weights will produce bands that look
authoritative in Pipedrive and are not, and someone will route real outreach on them. If Phase 1
must ship before the scope doc lands, ship the *mechanism* with the rubric as configuration and
leave the weights unset — refuse to write a band rather than write a default one.

## What IS pinned down

**The model** [R0641, Lilla Szabo, 2026-07-10]: a composite **additive** rubric over six
components — industry, stage maturity, company type, geography, revenue range, buying signal.
Hidden per-option scores are summed and mapped to a band:

| band | meaning |
|---|---|
| A | strong fit |
| B | moderate fit |
| C | low fit |

**Only the band reaches Pipedrive — never the numeric score.** This is explicit in the definition.

**It is a COMPANY score, not a person score.** It is distinct from the existing 0–110 lead score,
which scores people. Do not conflate them and do not write into the same field.

**It must be reachable ad hoc by an individual salesperson** for a company from their own network,
not only as a batch enrichment path [R0643, Lilla Szabo]. This is the requirement that **rules out a
Clay-only, list-driven implementation** — a Phase 1 that only scores rows in a Clay table does not
satisfy the stated need.

## What is contested — do not resolve it yourself

* **The ICP boundary.** Melisa proposed Series B/C ("Maybe that's the line"); Sergey narrowed it to
  Series B/C companies hiring multiple engineers and declared stealth/pre-seed **out** of ICP as of
  2026-07-14 — while naming **Toby and Chrissy, not GTM, as the gatekeepers** [R0613, R0615, R0616].
  His own effort split was stated self-inconsistently and the authoritative document was never
  shared.
* **MQL vs SQL is undefined.** Asked of Nik *and* Sergey on 2026-07-10, answered by nobody [R0650],
  and absent from the whole Slack corpus. Both the reporting and the ICP-band work sit on top of it.

## Credentials

Do **not** ask anyone to paste API keys. Everything is already on this machine:

```
C:\Users\User\Desktop\Нова папка\.env          # 8 credentials + endpoints/ids
C:\Users\User\Desktop\Нова папка\load_env.ps1  # source this; it also regenerates the CA bundle
```

From PowerShell in the project root: `. .\load_env.ps1`. Relevant here: `PIPEDRIVE_API_TOKEN`,
`OPENAI_API_KEY`, `CLAY_PUBLIC_API_KEY`, `N8N_BASE_URL` + `N8N_API_KEY`. The file is gitignored and
the docs-export gate fails closed if any of its values appear in a staged tree — keep it that way.

## Estate constraints that will bite an ICP writer

These are all measured, all recorded in `WF1_W1.0.1_build/wf1-system-reference.md`:

* **Pipedrive labels are cumulative, never removed.** If the band is expressed as a label, union it;
  four Zaps once spent 24 days quietly stripping `Responded`, and a naive `PATCH label_ids` is how
  that happens. If the band is a custom field, a single-option field is the safer shape.
* **`/v1/leads` list reads are a 7-day horizon** and `archived_status` is ignored on every route
  including `person_id`. Only the search routes reach archived leads. Any "score everything" walk
  built on a list read will silently see a fraction of the estate.
* **An uncapped-looking list read is not uncapped.** Prove the ordering of anything used for
  counting; unsorted `/v1` returns the OLDEST page.
* **`$json` does not survive an HTTP node** in n8n. Recover context from the node that owns it, by
  name (B12).
* **staticData is one object persisted at execution end.** Do not keep scoring state in it under any
  concurrency; use the claims data table `euyostwJYfJefItC` (`mode:"id"` only — `mode:"name"` is
  unreliable).
* **Persons and organizations are different objects.** A company score belongs on the org, or on the
  lead with the org resolved — 34% of one sprint's prospects had no person at all.
* **Any batch write over 10 records pre-posts** to `#niks-channel` with counts, 3–5 real example
  rows and an artifact path, and the result replies in the same thread (§9f.2).

## Suggested Phase 1 that does not depend on the missing spec

1. **Rubric as data, not code** — the six components and their options in one config object, weights
   nullable, with a hard refusal to emit a band while any weight is unset.
2. **Resolve and enrich the company** — the ad-hoc path first (one company in, one band out), since
   that is the requirement a batch design fails.
3. **Write only the band**, to a dedicated single-option field, with the write idempotent and the
   prior value captured so a re-scoring is reversible.
4. **Leave MQL/SQL alone** until it is defined.

That gives Chrissy something to fill in rather than something to correct.

## Open questions for whoever owns this

1. Who signs off the rubric weights now — Chrissy directly, or Toby as gatekeeper?
2. Band on the **organization** or on the **lead**? The definition says company fit; the CRM
   surface people actually look at is the lead card.
3. Is a Clay column part of Phase 1 at all, given the ad-hoc requirement rules out Clay-only?
