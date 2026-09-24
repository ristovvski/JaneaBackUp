# The activity note: HTML, and why

The note the Clay table sends is written to the Pipedrive activity **verbatim**
— n8n renders nothing. So the formatting has to be right where the note is
built, in the table's formula column, and it has to be right in the one format
Pipedrive actually renders.

**It is HTML.** Measured on this account, not read from the docs.

---

## What Pipedrive does to an activity note

Ten probes, each written to activity 46845 with `PUT /v1/activities/{id}` and
read back with `GET /api/v2/activities/{id}`:

| sent | came back | reading |
|---|---|---|
| `<b>x</b>` | verbatim | **bold works** |
| `<strong>x</strong>`, `<i>x</i>` | verbatim | also allowed |
| `<br>`, `<p>…</p>`, `<ul><li>` | verbatim | allowed |
| `<div>a</div>` | `\n<div>a</div>` | allowed, reformatted |
| `<script>alert(1)</script>` | **`""`** | sanitiser drops it, and the note with it |
| `a < b and 5 > 3 & more` | `a &lt; b and 5 &gt; 3 & more` | **plain text is HTML-escaped** |
| `R&D team` | `R&amp;D team` | ampersands too |
| `a &lt; b` | verbatim | **already-escaped text is left alone** |
| `Header\r\n\r\nwhy` | `Header \n \nwhy` | CRLF is mangled — a space is inserted |
| `Header\n\nwhy` | verbatim | stored, but collapses on render |
| `— · × – ≥` | verbatim | unicode is safe |

The escaping row is the proof. Pipedrive escapes a stray `<` into `&lt;` on the
way **in**, which only makes sense if the field is rendered as HTML on the way
**out**. That is also why `\n` disappears: to a browser a newline is
whitespace.

### Two consequences for whoever writes the note

1. **Never `\n` or `\r\n` for layout.** `\n` survives storage and then collapses
   into one run-on paragraph — which is exactly the symptom. `\r\n` is worse:
   Pipedrive rewrites it to ` \n`, inserting a space.
2. **Escape nothing.** Pipedrive escapes stray `<`, `>` and `&` in classifier
   prose by itself, and leaves `&lt;` alone when it is already an entity — so
   escaping by hand would double-escape and a rep would read `&amp;lt;`.
   Concatenate raw sentences with `<b>` and `<br>` and it is correct.

---

## The layout

```
ICP B (62/100) · confidence medium          ← bold

Industry 7/10 · SaaS — Other                ← bold
Sells horizontal no-code workflow, …        ← the why, beneath

Type 10/10
Named cloud products, demos, …

Stage 3/10
With no recorded funding …

Geography 10/10
Headquarters is in Denver, Colorado …

Revenue 10/10 · $25M–$500M via apollo
Apollo estimates $55.3M, …

Hiring 0 eng open, 0 ≥60d, leaders: none
No job postings were provided, …

Activation Stable ×0.80
No recorded funding and flat annual headcount …

Score 78.0 × 0.80 = 62

(then Tier 2 / activation guard / conflict / buying signal, each only when
 there is something to say)
```

`<br><br>` between blocks, `<br>` between a header and its sentence.

---

## The replacement for the `note: [...]` block

Drop-in for the Clay formula column that builds the note. The eight names in
the first block are the values the column already computes — wire them to
whatever they are called there; everything below is self-contained.

```js
const b   = (s) => `<b>${s}</b>`;
const one = (n) => (n === null || n === undefined ? '—' : n);

// header + why, as one block. A component with no sentence still gets its
// header: a missing "why" is not a reason to hide the level.
const blk = (header, why) => (why ? `${b(header)}<br>${why}` : b(header));

const note = [
  b(`ICP ${grade} (${final}/100) · confidence ${confidence_overall}`),

  blk(`Industry ${one(industry_level)}/10 · ${industry_vertical}`, industry_why),
  blk(`Type ${one(type_level)}/10`,                                 type_why),
  blk(`Stage ${one(stage_level)}/10`,                               stage_why),
  blk(`Geography ${one(geo_level)}/10`,                             geo_why),
  blk(`Revenue ${one(revenue_level)}/10${revenue_band ? ` · ${revenue_band}` : ''}${revenue_source ? ` via ${revenue_source}` : ''}`,
                                                                    revenue_why),
  blk(`Hiring ${one(eng_open)} eng open, ${one(eng_open_60d_plus)} ≥60d, leaders: ${leader_titles.length ? leader_titles.join(', ') : 'none'}`,
                                                                    hiring_why),
  blk(`Activation ${activation_used} ×${multiplier.toFixed(2)}`,    activation_why),

  b(`Score ${composite.toFixed(1)} × ${multiplier.toFixed(2)} = ${final}`),

  // Optional tail. Each line appears only when it has something to say, so an
  // ordinary company's note ends at the score.
  tier2_candidate ? b('Tier 2 candidate') + '<br>Enterprise scale — a different motion, not a better or worse fit.' : null,
  guard_reason    ? b('Activation guard applied') + '<br>' + guard_reason : null,
  conflict_note   ? b('Sources disagreed') + '<br>' + conflict_note : null,
  buying_why      ? `Buying signal (not scored): ${one(buying_level)} — ${buying_why}` : null,
].filter(Boolean).join('<br><br>');
```

Notes on it:

- **`.filter(Boolean)` is what makes the tail optional.** A null entry vanishes
  and takes its separator with it, so there is never a trailing blank block.
- **`one()` prints `—` for a null level** rather than `null` or `0`. A level the
  table could not determine and a level of zero are different facts.
- **`multiplier.toFixed(2)`** keeps `×0.80` rather than `×0.8`, and
  `composite.toFixed(1)` keeps `78.0`, so the arithmetic on the Score line
  reads as arithmetic.
- **The order is Industry, Type, Stage, Geography, Revenue, Hiring,
  Activation** — the order a human reads a fit judgement in, not the order the
  rubric weights them.

---

## Verified end to end

The block above was run against the live Intellistack row's real values. It
produces **1,320 characters**, byte-identical to the note that then went
through the whole pipeline — Clay body → Path B → `ParseScored` →
`BuildActivity` → `POST activity` — and landed on **activity 47033** (org
22586, deal 2277):

```
note stored === note Clay sent:  true
tags survived the whole chain:   true
```

n8n does not touch it. `BuildActivity` writes `note` verbatim and a test
asserts byte equality against the event rather than a resemblance to it, so the
formatting a rep sees is decided entirely in the Clay column.
