# WF-2 Phase D - webhook registration instructions for Nik

Read the two blocking items first; the URL is not live until step 1 completes.

## BLOCKER - I need one value from you

n8n's Public API has **no credential-list endpoint** (`GET /api/v1/credentials` → 405), and a
credential that no workflow uses yet is invisible to workflow enumeration. So I cannot discover the
id of the new **Slack WF-2** credential.

Open it in the n8n UI and copy the id from the address bar:

```
https://janea-systems-2025.app.n8n.cloud/home/credentials/<THIS-PART>
```

16-ish characters, e.g. the existing Slack one is `Udq1K604RpJqg1cR`. Send me that and I:
1. bind all 9 Slack nodes to it,
2. run the pre-deploy gate (post a test message through **that** credential to `C0B8GCVNR5W`) -
   note the n8n bot was `channel_not_found` on the team channel in W1.0.10, so this gate is real,
3. deploy WF-2 ACTIVE in shadow and hand you the live URL.

Until then WF-2 is built and green but **not deployed**, because deploying it on the HeyReach
identity is exactly what item E was about, and ops warns DO post during shadow.

## Production webhook URL (live once step 1 above is done)

```
https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}
```

The path is fixed by the builder and deterministic - it does not change between rebuilds.

## Smartlead UI registration

Account-level, not per-campaign: Smartlead exposes no API for account webhooks (verified again
2026-07-29 - `/webhooks`, `/account/webhooks`, `/user/webhooks` all 404), so this is a UI-only step.

**Settings → Webhooks → Add Webhook**

| field | value |
|---|---|
| Name | `WF-2 n8n Smartlead Receiver` |
| URL | `https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}` |
| Association | **User** (account-level, so it covers every campaign incl. future ones) |
| Secret | **your own value** - keep it, do not send it to me (see below) |

**Events** - tick the four whose payload `event_type` values are, verbatim from real payloads:

| ticked event | `event_type` WF-2 keys on |
|---|---|
| first email sent | `EMAIL_SENT` |
| email replied | `EMAIL_REPLIED` |
| email bounced | `EMAIL_BOUNCED` |
| lead unsubscribed | `LEAD_UNSUBSCRIBED` |

I have the **event_type strings verified** from recovered real payloads, but I have never seen this
UI, so match by meaning if the labels read differently. WF-2's event discriminator is deliberately
loose (regex on `first.*sent|email.?sent`, `repl`, `bounce`, `unsub`), so minor label wording does
not matter - what matters is that exactly these four fire and nothing else. If you see a
**Lead category updated** event, leave it OFF: that is Make's trigger, and WF-2 maps it to a
no-op precisely so the two systems cannot double-process.

### About the secret

Set any value you like and keep it. WF-2 stores only a **SHA-256 hash**, so the plaintext never
reaches me or the repo. Right now the check ships **unarmed**
(`webhook_secret_sha256: null` → traffic accepted, ops warned once an hour) so shadow is not
blinded. To arm it later, generate the hash yourself and send me only that:

```bash
node -e "console.log(require('crypto').createHash('sha256').update('YOUR-SECRET').digest('hex'))"
```

## Then tell me "registered"

I will verify, without touching anything:
- first real executions arriving,
- `Normalize` fully populated (event, campaign, lead, marker trio),
- `Shadow Log` recording intended actions,
- **zero real writes** - asserted against Pipedrive, not assumed from `WRITE_MODE`.

## What is already prepared

- `wf2_diff_harness.py` - runs on demand/daily, aligns **by lead** (Make triggers on
  category-updated, we on raw replied), marks classifier-dependent lines **DEGRADED**, and reports
  the `Ops Warn Unknown Inbox` count, the app_url-vs-constructed link check and the daily classify
  counter. Smoke-run today: reports "WF-2 is not deployed" rather than inventing numbers.
- `build_wf2h.py` → `wf2h-built.json` (9 nodes, deterministic, inactive) - daily Smartlead stats,
  label/DNC/bounce counters, one ops digest.

### One spec item I could not build as written

"SL webhook health (ours enabled; disabled → re-enable attempt + 🚨)" is **not implementable**:
Smartlead has no API to read or re-enable account-level webhooks (re-probed today, all 404). A
health check that cannot observe the thing it reports on would be worse than none, so instead the
diff harness does **silence detection** - Smartlead activity in the window with zero WF-2
executions raises the alarm, and a human checks the UI. The 5-fail disable policy still shapes the
design: rejected posts are dropped behind an already-sent 200, never a 500.
