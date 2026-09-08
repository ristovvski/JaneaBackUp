# DNC BUILD — HeyReach RemoveFromCampaign probe: investigation, not executed

**Status: BLOCKED — reporting back per explicit instruction, not improvising.**

## What was asked
Use Nik Krivosheia (pii-c61c7d08@example.invalid) as a HeyReach LinkedIn fixture, check if he already
exists as a lead in a HeyReach campaign, add him to a paused campaign if needed, run the
RemoveFromCampaign probe, and have Nik verify webhooks fire before/after via a real LinkedIn
message. Explicit instruction: "If adding a lead to a paused HeyReach campaign isn't possible via
API, report that and we design a different probe — don't improvise on real data."

## What happened
1. **No LinkedIn URL for Nik anywhere in the repo** (confirmed by search — every prior fixture use
   of his identity is email-only, `pii-c61c7d08@example.invalid`). Needed to find or get it fresh.
2. **Found him already**: listed all 6 HeyReach campaigns (4 PAUSED, 2 FINISHED) via
   `POST /campaign/GetAll`, then pulled leads from each via `POST /campaign/GetLeadsFromCampaign`.
   He's already a lead, listed as **"Nik Kryvo"**, in BOTH paused campaigns `510736` ("Final TEST")
   and `510448` ("Final test "), at `https://www.linkedin.com/in/pii-0e746683`. **Needs his own
   confirmation this is really him** before using it as the fixture — I found this, I didn't invent
   it, but the instruction was he'd confirm the URL and I haven't gotten that confirmation yet.
3. **Real risk found on the "add to a paused campaign" path — confirmed via HeyReach's own help
   docs, not guessed**: *"Even if the campaign is paused, adding leads via API or integration
   directly into that campaign will activate the campaign."* Both paused campaigns Nik is already
   in are NOT empty test lists — `510736` has **314** other leads, `510448` has **70** other real
   people (Person-c4602881, Kamil Jałowiec, Person-02c76293, etc.). Adding a lead via API would
   have auto-resumed real outreach to all of them. This turned out moot since he's already in both
   — but it's a real trap worth remembering for any future HeyReach fixture work.
4. **Could not find a documented lead-removal endpoint in HeyReach's current public API.**
   Checked: the official campaign-API blog post (only lists Create/UpdateSettings/UpdateSequence/
   UpdateAccounts/UpdateSchedule/GetCampaignSequence — no lead-level add/remove at all), the
   Postman collection's intro page (loaded but the sidebar with the full endpoint tree didn't
   render for extraction), and the OpenAPI/swagger JSON (`/swagger/v1/swagger.json`,
   `/swagger.json`, `/openapi.json` — all 404 with a valid, working API key). No prior script in
   this repo has ever called a lead-removal endpoint either (confirmed by an earlier research
   pass) — the "HeyReach RemoveFromCampaign" name in this project's own memory/architecture notes
   traces to a past finding I could not independently re-verify the exact endpoint for today.

## Why this stopped here instead of guessing an endpoint and calling it
A mutating call against an unverified endpoint name/shape, on a lead that's live in two real
paused campaigns (314 + 70 other real people), is exactly the kind of "improvise on real data"
the instruction ruled out. Firing a guessed request could do something unintended and be hard to
diagnose or reverse.

## Next (needs the owner)
- Confirm `https://www.linkedin.com/in/pii-0e746683` really is Nik's profile.
- Either point me at the exact lead-removal endpoint (HeyReach support, a teammate with deeper API
  access, or the full Postman collection opened directly in a browser with its sidebar expanded),
  or confirm there may genuinely be no public-API lead-removal call and the UI is the only path —
  in which case the probe needs a human doing the removal manually in HeyReach's web app while I
  only handle the before/after webhook-log verification.
- Once the mechanism is confirmed, the sequence itself (baseline message → remove → second message
  → compare webhook logs) is straightforward and low-risk — the blocker is purely "what's the real
  removal call," not the test design.
