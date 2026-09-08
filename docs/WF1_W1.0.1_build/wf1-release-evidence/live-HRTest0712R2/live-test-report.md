# WF-1 live test report — HRTest0712R2

- Test double ID: `NNOVii5ImjFKDSM0`
- Webhook path: `hr-test-hrtest0712r2-e89986b7`
- Generated at: `2026-07-12T20:57:37.077Z`

| Test | Result | Execution | n8n status | Webhook |
|---|---|---:|---|---:|
| T1 | **PASS** | 9920 | success | 200 |
| T4 | **FAIL** | 9921 | success | 200 |
| T7 | **FAIL** | 9922 | success | 200 |
| T8-setup | **PASS** | 9923 | success | 200 |
| T8 | **FAIL** | 9924 | success | 200 |
| TF10-setup | **PASS** | 9925 | success | 200 |
| TF10 | **FAIL** | 9926 | success | 200 |

## T1 — PASS
Fixture SHA-256: `c01b8dd22c4a53102984602b53847b31cb5582ba5aafdce5405d28047402d314`

Assertions:
- new-person create path and invite activity executed

Executed nodes:
```text
CONFIG
Create Activity
Create Lead
Dedupe
IF Company
IF Email Found
IF Email Present
IF Org Found
IF URL Found
Lead Create Gate
Lead From Create
Lead Search
Normalize
Org Create
Org From Create
Org Search
PID Resolved
Person Create
Person Search Email
Person Search URL
Respond to Webhook
Sent IF Lead ID
Switch
Webhook
```

## T4 — FAIL
Fixture SHA-256: `6a8d9853a584f7caa7d02de946719b1da457146a1bfe34a8bb389917756254bf`

Assertions:
- critical alert fired first with rendered reply text; reply activity, task, responded label; M8 Slack absent

Failures:
- critical alert posted text is not the rendered reply alert: ':speech_balloon: Reply from HR Test HRTest0712R2'

Executed nodes:
```text
CONFIG
Dedupe
M7 Build
M7 Critical Slack
M7 IF Email Found
M7 IF Email Present
M7 IF Lead ID
M7 IF Patch
M7 IF Reply Activity Lead
M7 Labels Compute
M7 Lead Get
M7 Lead Patch
M7 PID From Email
M7 Person Get
M7 Person Patch
M7 Person Search Email
M7 Reply Activity
M7 Reply Context
M8 IF Lead ID
M8 IF Transition
M8 Task
Normalize
Respond to Webhook
Switch
Webhook
```

## T7 — FAIL
Fixture SHA-256: `af91e2837918f840f559b674a50e5e05f982d6f5f8f1844fee03c65fc5d6d648`

Assertions:
- unknown reply: critical alert POSTED with actual reply text, M7 Slack Warn fired, zero Pipedrive writes

Failures:
- unknown-person critical alert POSTED text malformed: ':speech_balloon: Reply from HR Test HRTest0712R2'
- M7 Slack Warn POSTED text malformed: ':warning: WF-1: every_message_reply_received for'

Executed nodes:
```text
CONFIG
Dedupe
M7 Critical Slack
M7 IF Email Present
M7 IF URL Found
M7 Person Search URL
M7 Reply Context
M7 Slack Warn
Normalize
Respond to Webhook
Switch
Webhook
```

## T8-setup — PASS
Fixture SHA-256: `9d655d100845cf790ce3268a023f355ede2e0d3d183ffb3941a4f347229e6756`

Assertions:
- T8-setup: fresh person + lead created at Invited

Executed nodes:
```text
CONFIG
Create Activity
Create Lead
Dedupe
IF Company
IF Email Found
IF Email Present
IF Org Found
IF URL Found
Lead Create Gate
Lead From Create
Lead Search
Normalize
Org Create
Org From Create
Org Search
PID Resolved
Person Create
Person Search Email
Person Search URL
Respond to Webhook
Sent IF Lead ID
Switch
Webhook
```

## T8 — FAIL
Fixture SHA-256: `2024aab1e3cb9cadc917009bead624ad40909a347fe6017e9a0c5afc6a2aa095`

Assertions:
- reply-to-invite -> 'Replied to invite', responded label, task created, correct POSTED alert text

Failures:
- T8 critical alert POSTED text malformed: ':speech_balloon: Reply from HR Test HRTest0712R2'

Executed nodes:
```text
CONFIG
Dedupe
M7 Build
M7 Critical Slack
M7 IF Email Found
M7 IF Email Present
M7 IF Lead ID
M7 IF Patch
M7 IF Reply Activity Lead
M7 Labels Compute
M7 Lead Get
M7 Lead Patch
M7 PID From Email
M7 Person Get
M7 Person Patch
M7 Person Search Email
M7 Reply Activity
M7 Reply Context
M8 IF Lead ID
M8 IF Transition
M8 Task
Normalize
Respond to Webhook
Switch
Webhook
```

## TF10-setup — PASS
Fixture SHA-256: `7ee65e621898ed2ef4bf4390b4d59591bcedf31caf66eb0978359b8217748216`

Assertions:
- TF10-setup: fresh person + lead created at Invited

Executed nodes:
```text
CONFIG
Create Activity
Create Lead
Dedupe
IF Company
IF Email Found
IF Email Present
IF Org Found
IF URL Found
Lead Create Gate
Lead From Create
Lead Search
Normalize
Org Create
Org From Create
Org Search
PID Resolved
Person Create
Person Search Email
Person Search URL
Respond to Webhook
Sent IF Lead ID
Switch
Webhook
```

## TF10 — FAIL
Fixture SHA-256: `2d1d71e386d4ec80073e7bbd089dc54ab196d78a1aca3c50ad24ac3ccbdeda0d`

Assertions:
- no-lead reply: critical alert POSTED with reply text, M7 No Lead Warn fired, zero lead/activity/task writes

Failures:
- TF10 critical alert POSTED text malformed: ':speech_balloon: Reply from HR Test HRTest0712R2'
- M7 No Lead Warn POSTED text malformed: ':warning: WF-1: every_message_reply_received — p'

Executed nodes:
```text
CONFIG
Dedupe
M7 Build
M7 Critical Slack
M7 IF Email Found
M7 IF Email Present
M7 IF Lead ID
M7 IF Patch
M7 Labels Compute
M7 Lead Get
M7 No Lead Warn
M7 PID From Email
M7 Person Get
M7 Person Patch
M7 Person Search Email
M7 Reply Context
Normalize
Respond to Webhook
Switch
Webhook
```

## Interpretation

`PASS` means both the execution path and the evidence available through n8n satisfied the implemented assertion. 
`BLOCKED` means the path looked correct but a remote side effect could not be proven from retained execution data; verify it through Pipedrive/Slack directly. 
`FAIL` means an asserted path or invariant was violated.
