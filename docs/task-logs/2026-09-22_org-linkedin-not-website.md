# 2026-09-22 — a linkedin.com URL is not a website

## Done

| | |
|---|---|
| WF-1 `Org Create` guard + CONFIG key | `658bea85`, 140 nodes, ACTIVE |
| WF-1 + WF-2 alert labels | WF-1 `658bea85`, WF-2 `55a3c429`, 197 nodes, ACTIVE |
| Statics | **11/11** including two non-vacuity cases |
| Org count | **73 of 21,859** (0.33%), no repair |

### What was actually broken — measured before changing anything

**The alert, in both receivers.** WF-1 `M7 Build` printed `Company website: ` + HeyReach's
`lead.company_url`, which on a LinkedIn campaign is the company's LinkedIn **page**. Caught on the
wire pre-deploy — exec 65330, Person-3fa711ad / Novo Nordisk:

```
Company website: https://www.linkedin.com/company/novo-nordisk
```

WF-2 `Body Reply Alert` did the same with `n.lead.website`.

**WF-1 `Org Create`.** `body[cfg.org_website_field] = n.lead.company_url` with no test at all, and
`org_website_field` is the native `website`.

### What was NOT broken, so it was not touched

* **WF-2 `Body Org Create` already had this guard** — `W1.0.12`, and mutually exclusive:
  `if (w && !isLi(w))` writes the three website fields, `if (w && isLi(w))` writes
  `org_linkedin_lh`. Left alone; a post-deploy assertion checks it was not disturbed.
* **The three named orgs are clean in Pipedrive.** Brillio and PATHOMIQ carry real domains in
  `website` and LinkedIn URLs in the LinkedIn fields; Novo Nordisk carries only a LinkedIn field.
  So this is a forward guard plus an alert-label fix — the CRM was not showing the damage the alert
  implied.

### Field choice

`ed932dfc4870dcd72fa7b4eadb67da38d169299b` (`lh_linkedin_profile_url`) — the same field WF-2 writes,
so the two receivers agree. It went into WF-1's CONFIG as `org_linkedin_field` rather than being
hardcoded in the node, matching how `org_website_field` already works. Pipedrive's native `linkedin`
key is a read-only system field and cannot be written.

## The count — 73 of 21,859 organizations (0.33%)

Full cursor walk, 44 pages, cursor exhausted. All four website-ish fields checked.

| field | orgs |
|---|---|
| native `website` | 71 |
| `2064369b…` Website | 2 |
| `7ef47bd7…` Website URL | 2 |
| `c8c70fc5…` lh_website | 1 |

12 of the 73 already have the LinkedIn field populated as well.

**Two caveats before anyone repairs these**, both from reading the rows rather than the count:

1. **At least 2 are not errors.** Orgs 1056 and 16550 are *LinkedIn the company* —
   `careers.linkedin.com` genuinely is their website. A blind repair would blank a correct value.
2. **Several carry the WRONG COMPANY, not just the wrong field.** Scout AI →
   `linkedin.com/company/draper-associates`, PeopleReign → `augerai`, Myko AI → `genius-sheets`,
   Forum AI → `instagram`. Moving those values into the LinkedIn field would preserve a wrong fact
   in a tidier place. One (Frontify) holds a `linkedin.com/in/` **person** profile in an org field.

That is a different and worse defect than the one fixed today, and it is not mine to assume the
cause of. Recorded, not acted on.

## Pending

**Wire-proof on the next BioTechX lead.** All 70 BioTechX executions in retention pre-date the
deploy by minutes, so nothing has yet run on the new code. The pre-deploy evidence above is what the
next one should NOT look like: it should read `Company LinkedIn: …`.

## Improvable — mine

* My first patch wrote literal `\n` sequences into the `Org Create` jsonBody instead of real
  newlines, which put the whole guard inside one comment line — the body came back as
  `{"name":"Brillio"}` with no site field at all. The statics caught it before deploy. That is the
  fourth representation-mismatch of this class in recent sessions (escaped vs rendered, comment vs
  code); the pattern is always the same: asserting on, or writing, a *representation* of a string
  rather than the string.
