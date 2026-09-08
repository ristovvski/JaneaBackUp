# WF-2 parity conditions - re-extracted from the UI blueprint exports

Source: `make-blueprint-1-email-sent.json`, `make-blueprint-2-reply.json` (UI exports).
**Mechanics note:** Make stores a link filter on the **target module** (`module.filter`), not on the
router's `route` object. That is why the API export looked filter-less; the earlier
"conditions not extractable" caveat is void, as Nik stated.

## Scenario 1 - SENT
| gate (before module) | condition | WF-2 treatment |
|---|---|---|
| [28] regexp:Parser | `campaign_name notcontain:ci "lead nurturing"` | nurture -> no CRM (parity; WF-2 canon+nbsp-insensitive) |
| [29] CreatePersonV2 - "If name was not found" | `{{16.name}} notexist` | **replaced**: resolve by EMAIL, not name |
| [18] createLead - "If name was found" | `{{16.name}} exist` | **replaced**: email resolve + lead-per-campaign select |

## Scenario 2 - REPLIED
| gate (before module) | condition | WF-2 treatment |
|---|---|---|
| [25] router, [19] searchLeads, [26] searchPersons, [124] searchOrganizations, [67] sheets | `campaign_name notcontain:ci "lead nurturing"` | same nurture suppression, canon-based |
| **[131] slack:CreateMessage** | `campaign_name contain:ci "lead nurturing"` | **this is the NURTURE alert variant** (no Pipedrive link). Corrects the earlier guess that it was a no-lead variant. |
| [125] getOrganizationV2 - "If Org exists" | `{{124.name}} exist` | org find-or-create |
| [123] createOrganizationV2 - "If org doesn't exist" | `{{124.name}} notexist` | org find-or-create |
| [88/93/94/92/89/90/91/103/107/118/135/140/142/144] forward-email x14 | `{{67.` + "`1`" + `}} text:equal "<OwnerName>"` | **the Sheets lookup returns the OWNER NAME in column 1**; the 14 branches map name -> email |

### The real forward map (owner NAME -> owner email), from the 14 gates
| sheet column-1 value | forwards to | note |
|---|---|---|
| Toby | toby@janeasystems.com | |
| Andreas | andreas@janeasystems.com | |
| Mario | mario@janeasystems.com | |
| Mirza | mirza@janeasystems.com | |
| Melisa | melisa@janeasystems.com | |
| Can | can@janeasystems.com | |
| **Test** | melisa@janeasystems.com | explains the "duplicate melisa" - it is the `Test` owner row |
| Bill | bill.sanders@janeasystems.com | |
| Benedetto | benedetto.proietti@janeasystems.com | |
| Sergey | sergey@janeasystems.com | blueprint has a TRAILING SPACE -> trimmed in CONFIG |
| James | james@janeasystems.com | trailing space -> trimmed |
| Rune | rune@janeasystems.com | trailing space -> trimmed |
| Chrissy | chrissy@janeasystems.com | trailing space -> trimmed |
| Noah | noah@janeasystems.com | |

So the lookup chain is: `from_email` (sending inbox) -> Sheets col A match -> **col 1 = owner name** ->
name->email map. Since Sheets access is deferred (Nik's amendment 3), WF-2 uses
`CONFIG.forward_owner_map` (name->email, above, cleaned) as the PRIMARY source with
`forward_map_source=config`, plus `CONFIG.forward_inbox_map` seeded with the 10 sprint inboxes known to be
Toby's; any unknown inbox -> `forward_default` + ops warn. The Sheets node stays in the design, disabled.

## Event-model corrections from Nik's UI findings
| | Make (today) | WF-2 |
|---|---|---|
| SENT subscription | "Email sent, **First email sent**" | subscribe to **First email sent** (+ keep seq==1 gate as defense) |
| REPLY subscription | **LEAD CATEGORY UPDATED** (fires AFTER Smartlead's own GPT categorizes) | **EMAIL_REPLIED** (raw, earlier, GPT-independent) |

Consequences accepted: (i) our category POST lands after Smartlead's own -> ours wins (desired);
(ii) in SHADOW, Make fires on a *different event*, so the **diff harness must align by lead, not by
event type**; (iii) EMAIL_REPLIED must be verified to carry the reply body - defensive Normalize stands.
