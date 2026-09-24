# WF-2 self-service end-to-end smoke. Rerunnable harness.
#
# Creates a throwaway Smartlead campaign, sends ONE real email to a named recipient, waits for the
# reply, and verifies the whole WF-2 shadow pipeline against REAL Smartlead payloads. Then deletes
# the campaign.
#
# WHY the campaign name carries the nurture marker:
#   Make's reply scenario gates every CRM branch on  campaign_name NOT contains "lead nurturing"
#   (modules 19 / 26 / 124 / 67), so a nurture-marked campaign cannot cause Make to touch Pipedrive.
#   TRADE-OFF, measured: WF-2 detects nurture with the SAME substring (/lead nurtur/), so its own
#   nurture branch short-circuits to a Slack-only intent and the CLASSIFIER never runs. You cannot
#   get Make-CRM-safety and classifier coverage from one campaign. Use -NonNurture only with
#   explicit approval - Make will then write to Pipedrive for real and forward the reply to a
#   colleague's mailbox.
#   Make module 131 (slack -> C07LTD8UT70) has the INVERSE filter, so a nurture run DOES put one
#   message in the team channel, announcing a Pipedrive label that was never written.
#
# HARD RULES honoured: no Make hooks/scenarios touched, no other campaign touched, no account
# settings changed, WF-1/WF-2 versionIds untouched.
#
# Usage:
#   . wf1_env.ps1
#   ./wf2_selfservice_smoke.ps1 -Recipient pii-c61c7d08@example.invalid
#   ./wf2_selfservice_smoke.ps1 -Recipient pii-fd989748@example.invalid -SkipSend      # verify a prior run only
#   ./wf2_selfservice_smoke.ps1 -Recipient pii-fd989748@example.invalid -SentOnly       # FIRST EMAIL SENT contract only
#
# DIAGNOSTIC: every Smartlead payload carries webhook_id / webhook_name identifying WHICH
# registration delivered it. Ours is 703611 "N8n"; Make's is 151526. If an event type never
# arrives, check that entry's ticked events before suspecting the endpoint - a wrong-entry tick is
# what hid the missing EMAIL_SENT subscription.
param(
  [Parameter(Mandatory=$true)][string]$Recipient,
  [string]$CampaignName = "[Lead Nurturing] WF2 Shadow Test - API",
  [string]$Subject      = "WF2 shadow test",
  [string]$Body         = "<div>WF2 shadow test - reply anything</div>",
  [switch]$NonNurture,
  [switch]$SkipSend,
  [switch]$SentOnly,        # verify the FIRST EMAIL SENT contract only; no reply needed
  [switch]$KeepCampaign
)
$ErrorActionPreference = "Stop"
$SL = "https://server.smartlead.ai/api/v1"
$K  = $env:SMARTLEAD_API_KEY
$NB = $env:N8N_BASE_URL
$NH = @{ "X-N8N-API-KEY" = $env:N8N_API_KEY }
foreach ($v in @("SMARTLEAD_API_KEY","N8N_BASE_URL","N8N_API_KEY","PIPEDRIVE_API_TOKEN")) {
  if (-not [Environment]::GetEnvironmentVariable($v)) { throw "$v missing - source wf1_env.ps1 first" }
}
if ($NonNurture) {
  Write-Host "!! -NonNurture: Make WILL write to Pipedrive and forward the reply. Approval required." -ForegroundColor Red
  $CampaignName = $CampaignName -replace '\[Lead Nurturing\] ',''
}

function SLGet($p) { Invoke-RestMethod -Uri "$SL$p`?api_key=$K" -Method GET -TimeoutSec 90 }
function SLGetQ($p,$q) { Invoke-RestMethod -Uri "$SL$p`?api_key=$K&$q" -Method GET -TimeoutSec 90 }
function SLPost($p,$obj) {
  Invoke-RestMethod -Uri "$SL$p`?api_key=$K" -Method POST -ContentType "application/json" `
    -Body ($obj | ConvertTo-Json -Depth 6) -TimeoutSec 90
}
function WF2Latest {
  $e = Invoke-RestMethod -Uri "$NB/api/v1/executions?workflowId=$script:WID&limit=5" -Headers $NH -Method GET -TimeoutSec 60
  if (-not $e.data) { return 0 }
  return [int](@($e.data) | Sort-Object { [int]$_.id } -Descending)[0].id
}

# ---- locate WF-2
$wfs = Invoke-RestMethod -Uri "$NB/api/v1/workflows?limit=100" -Headers $NH -Method GET -TimeoutSec 60
$wf2 = $wfs.data | Where-Object { $_.name -eq 'WF-2 Smartlead Receiver' }
if (-not $wf2) { throw "WF-2 is not deployed" }
$script:WID = $wf2.id
$cfg = ($wf2.nodes | Where-Object { $_.name -eq 'CONFIG' }).parameters.jsonOutput | ConvertFrom-Json
Write-Host "WF-2 $($script:WID)  WRITE_MODE=$($cfg.WRITE_MODE)  classify=$($cfg.classify_enabled)  model=$($cfg.llm.model)"
if ($cfg.WRITE_MODE -ne 'shadow') { throw "REFUSING: WF-2 is not in shadow mode - this harness assumes no real writes" }

# ---- baseline for the zero-writes assertion
$PD = $env:PIPEDRIVE_API_TOKEN
$pdBefore = @((Invoke-RestMethod -Uri "https://api.pipedrive.com/api/v2/persons/search?api_token=$PD&term=$Recipient&fields=email&exact_match=true&limit=5" -Method GET -TimeoutSec 60).data.items).Count
$before = WF2Latest
Write-Host "baseline: WF-2 latest exec=$before  Pipedrive persons for recipient=$pdBefore"

$cid = $null
if (-not $SkipSend) {
  # ---- pick a warmed sender with zero sends today
  $accts = @()
  foreach ($off in 0,100,200,300) {
    $r = SLGetQ "/email-accounts/" "limit=100&offset=$off"
    if (@($r).Count -eq 0) { break }; $accts += $r
  }
  $sender = $accts | Where-Object {
    $_.daily_sent_count -eq 0 -and $_.warmup_details.status -eq 'ACTIVE' -and
    $_.warmup_details.warmup_reputation -eq '100%' -and [int]$_.warmup_details.total_spam_count -eq 0 -and
    [int]$_.warmup_details.total_sent_count -gt 50
  } | Sort-Object { [int]$_.warmup_details.total_sent_count } -Descending | Select-Object -First 1
  if (-not $sender) { throw "no warmed sender with zero sends today" }
  Write-Host "sender: $($sender.from_email) (warmup sends $($sender.warmup_details.total_sent_count), today 0)"

  $c = SLPost "/campaigns/create" @{ name = $CampaignName }
  $cid = $c.id
  Write-Host "campaign $cid created: $CampaignName"
  SLPost "/campaigns/$cid/email-accounts" @{ email_account_ids = @($sender.id) } | Out-Null
  SLPost "/campaigns/$cid/leads" @{ lead_list = @(@{ email = $Recipient; first_name = "WF2"; last_name = "Smoke" }) } | Out-Null
  SLPost "/campaigns/$cid/sequences" @{ sequences = @(@{ seq_number = 1
      seq_delay_details = @{ delay_in_days = 1 }
      seq_variants = @(@{ subject = $Subject; email_body = $Body; variant_label = "A" }) }) } | Out-Null
  # min_time_btw_emails below ~5 is rejected with a bare 400
  SLPost "/campaigns/$cid/schedule" @{ timezone = "Etc/UTC"; days_of_the_week = @(0,1,2,3,4,5,6)
      start_hour = "00:00"; end_hour = "23:59"; min_time_btw_emails = 5; max_new_leads_per_day = 10 } | Out-Null
  SLPost "/campaigns/$cid/settings" @{ stop_lead_settings = "REPLY_TO_AN_EMAIL"; track_settings = @() } | Out-Null
  SLPost "/campaigns/$cid/status" @{ status = "START" } | Out-Null
  Write-Host "campaign STARTED - Smartlead's sender cron takes a few minutes"

  # ---- wait for the real send (statistics is the ground truth, not the webhook)
  $sent = $null
  foreach ($i in 1..30) {
    Start-Sleep -Seconds 20
    $st = SLGet "/campaigns/$cid/statistics"
    if ([int]$st.total_stats -gt 0) { $sent = @($st.data)[0]; break }
    Write-Host "  waiting for send ($i)..."
  }
  if (-not $sent) { throw "no send observed - check the sender and schedule window" }
  Write-Host "SENT at $($sent.sent_time) to $($sent.lead_email) stats_id=$($sent.stats_id)"
  Write-Host ""

  if ($SentOnly) {
    # SENT-contract mode: watch for the First Email Sent webhook with a generous window. Their
    # observed reply latency was ~36s; a SENT event that has not arrived in 12 minutes is absent,
    # not slow.
    $sentExec = $null
    foreach ($i in 1..48) {
      Start-Sleep -Seconds 15
      $now = WF2Latest
      if ($now -gt $before) {
        $d = Invoke-RestMethod -Uri "$NB/api/v1/executions/$now`?includeData=true" -Headers $NH -Method GET -TimeoutSec 90
        $ev = $d.data.resultData.runData.'Webhook'[0].data.main[0][0].json.body.event_type
        Write-Host "  exec $now event_type=$ev"
        if ($ev -match 'sent') { $sentExec = $d; break }
        $before = $now
      } elseif ($i % 4 -eq 0) { Write-Host "  waiting for SENT ($([int]($i*15/60)) min)..." }
    }
    if (-not $sentExec) {
      Write-Host "VERDICT: no SENT event in 12 minutes while the send is confirmed." -ForegroundColor Red
      Write-Host "         send was observed via /statistics, so this is platform behaviour, not our endpoint."
    } else {
      $rd = $sentExec.data.resultData
      $sb = $rd.runData.'Webhook'[0].data.main[0][0].json.body
      $sn = $rd.runData.'Normalize'[0].data.main[0][0].json
      Write-Host "VERDICT: SENT observed. event_type=$($sb.event_type)" -ForegroundColor Green
      Write-Host "  raw keys: $((($sb.PSObject.Properties.Name | Sort-Object) -join ', '))"
      Write-Host "  normalize: event=$($sn.event) sl_lead_id=$($sn.sl_lead_id) map=$($sn.sl_lead_map_id) inbox=$($sn.sender_inbox)"
      Write-Host "  nodes: $((@($rd.runData.PSObject.Properties.Name)) -join ', ')"
    }
    if ($cid -and -not $KeepCampaign) {
      SLPost "/campaigns/$cid/status" @{ status = "PAUSED" } | Out-Null
      Invoke-RestMethod -Uri "$SL/campaigns/$cid`?api_key=$K" -Method DELETE -TimeoutSec 60 | Out-Null
      Write-Host "campaign $cid paused + deleted"
    }
    if ($sentExec) { exit 0 } else { exit 2 }
  }

  Write-Host ">>> REPLY TO THAT EMAIL NOW from $Recipient <<<" -ForegroundColor Yellow
}

# ---- wait for the reply webhook
$reply = $null
foreach ($i in 1..60) {
  Start-Sleep -Seconds 15
  $now = WF2Latest
  if ($now -gt $before) {
    $d = Invoke-RestMethod -Uri "$NB/api/v1/executions/$now`?includeData=true" -Headers $NH -Method GET -TimeoutSec 90
    $ev = $d.data.resultData.runData.'Webhook'[0].data.main[0][0].json.body.event_type
    Write-Host "  exec $now event_type=$ev"
    if ($ev -match 'repl') { $reply = $d; break }
    $before = $now
  } else { Write-Host "  waiting for reply ($i)..." }
}
if (-not $reply) { throw "no reply webhook observed" }

# ---- assertions
$rd = $reply.data.resultData
$b  = $rd.runData.'Webhook'[0].data.main[0][0].json.body
$n  = $rd.runData.'Normalize'[0].data.main[0][0].json
$vs = $rd.runData.'Verify Secret'[0].data.main[0][0].json
$ran = @($rd.runData.PSObject.Properties.Name)
$fail = @()
function Check($name, $cond, $detail) {
  if ($cond) { Write-Host "  PASS  $name" } else { Write-Host "  FAIL  $name :: $detail" -ForegroundColor Red; $script:fail += $name }
}
Write-Host ""; Write-Host "=== assertions ==="
Check "secret path ran"            ($vs.__auth_ok -eq $true) "auth_mode=$($vs.__auth_mode)"
Check "event routed to REPLIED"    ($n.event -eq 'REPLIED') "event=$($n.event) raw=$($n.raw_event)"
Check "from_email IS our inbox"    ($n.sender_inbox -eq $b.sl_senders_mailbox) "sender_inbox=$($n.sender_inbox)"
Check "lead email is the recipient" ($n.lead.email -eq $Recipient.ToLower()) "lead=$($n.lead.email)"
Check "app_url captured"           ([bool]$n.sl_app_url) "sl_app_url=$($n.sl_app_url)"
Check "app_url matches map id"     ($n.sl_app_url -like "*leadMap=$($n.sl_lead_map_id)") "url=$($n.sl_app_url) map=$($n.sl_lead_map_id)"
Check "reply body captured"        ([bool]$n.reply.body) "body empty"
Check "received_at from time_replied" ([bool]$n.reply.received_at) "received_at null"
Check "dedupe ran"                 ($ran -contains 'Dedupe') "no Dedupe"
Check "not treated as duplicate"   (-not ($ran -contains 'NoOp Duplicate')) "dropped as duplicate"
Check "Shadow Log recorded intent" ($ran -contains 'Shadow Log') "no Shadow Log"
$writes = $ran | Where-Object { $_ -in @('Lead Labels Union','Reply Activity','Person Create','Person Patch','Lead Create','Org Create','SL Category','SL Forward Email','SL Unsubscribe','Reply Alert','Nurture Alert') }
Check "ZERO real writes"           (@($writes).Count -eq 0) "ran: $($writes -join ', ')"
if ($n.is_nurture) {
  Check "nurture: Slack-only intent" ($ran -contains 'Body Nurture Alert') "no nurture alert"
  Check "nurture: no classifier"     (-not ($ran -contains 'LLM Classify')) "classifier ran on a nurture reply"
  Check "nurture: no CRM intent"     (-not ($ran -contains 'Body Lead Labels Union')) "CRM intent recorded"
} else {
  $cp = $rd.runData.'Classify Parse'[0].data.main[0][0].json
  Check "classifier ran"          ($ran -contains 'LLM Classify') "no LLM call"
  Check "category assigned"       ([bool]$cp.__category) "no category"
  Check "provenance = openai"     ($cp.__category_source -eq 'openai') "source=$($cp.__category_source)"
  $llm = $rd.runData.'LLM Classify'[0].data.main[0][0].json
  Write-Host "  classified '$($cp.__category)' conf=$($cp.__confidence) tokens=$($llm.usage.total_tokens) model=$($llm.model)"
  $fr = $rd.runData.'Forward Resolve'
  if ($fr) { Write-Host "  forward -> $($fr[0].data.main[0][0].json.__forward_to) ($($fr[0].data.main[0][0].json.__forward_reason))" }
}
$pdAfter = @((Invoke-RestMethod -Uri "https://api.pipedrive.com/api/v2/persons/search?api_token=$PD&term=$Recipient&fields=email&exact_match=true&limit=5" -Method GET -TimeoutSec 60).data.items).Count
Check "Pipedrive untouched"        ($pdAfter -eq $pdBefore) "persons before=$pdBefore after=$pdAfter"
if ($cid) {
  $ld = SLGetQ "/campaigns/$cid/leads" "offset=0&limit=5"
  Check "no SL category written"   ($null -eq @($ld.data)[0].lead_category_id) "category=$(@($ld.data)[0].lead_category_id)"
}
Write-Host ""; Write-Host "shadow intents:"
foreach ($r in @($rd.runData.'Shadow Log')) { foreach ($blk in $r.data.main) { foreach ($i in $blk) {
  Write-Host ("  {0,-40} would_write={1}" -f $i.json.node, $i.json.would_write) } } }

# ---- cleanup
if ($cid -and -not $KeepCampaign) {
  SLPost "/campaigns/$cid/status" @{ status = "PAUSED" } | Out-Null
  Invoke-RestMethod -Uri "$SL/campaigns/$cid`?api_key=$K" -Method DELETE -TimeoutSec 60 | Out-Null
  $all = SLGet "/campaigns"
  Check "test campaign deleted" (-not [bool](@($all) | Where-Object { $_.id -eq $cid })) "still present"
}
Write-Host ""
if ($fail.Count -eq 0) { Write-Host "ALL CHECKS PASSED" -ForegroundColor Green }
else { Write-Host "FAILED: $($fail -join ', ')" -ForegroundColor Red; exit 1 }
