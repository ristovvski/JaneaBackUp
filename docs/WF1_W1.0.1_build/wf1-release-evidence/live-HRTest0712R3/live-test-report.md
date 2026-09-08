# WF-1 live test report — HRTest0712R3

- Test double ID: `NNOVii5ImjFKDSM0`
- Webhook path: `hr-test-hrtest0712r2-e89986b7`
- Generated at: `2026-07-12T21:01:12.918Z`

| Test | Result | Execution | n8n status | Webhook |
|---|---|---:|---|---:|
| T1 | **PASS** | 9927 | success | 200 |
| T4 | **PASS** | 9928 | success | 200 |
| T7 | **PASS** | 9929 | success | 200 |
| T8-setup | **PASS** | 9930 | success | 200 |
| T8 | **PASS** | 9931 | success | 200 |
| TF10-setup | **PASS** | 9932 | success | 200 |
| TF10 | **PASS** | 9933 | success | 200 |

## T1 — PASS
Fixture SHA-256: `4acafccab13635ede2cd63289e74659ddde59029068fa33be4cec82754ebf169`

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

## T4 — PASS
Fixture SHA-256: `7a5a7a0b68c5c236ce17e6071e60fa9e17fd24c2ee08742b54d26e000802379f`

Assertions:
- critical alert fired first with rendered reply text; reply activity, task, responded label; M8 Slack absent

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

## T7 — PASS
Fixture SHA-256: `a29ab6de29662b6193fd273ef936597a519b0ef2b250bfc5426ef8e37a03eed0`

Assertions:
- unknown reply: critical alert POSTED with actual reply text, M7 Slack Warn fired, zero Pipedrive writes

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
Fixture SHA-256: `7e4e17afc4b8952f7c41b7901a86fdbe10151bca0f8ac0be0881b77ca4c55815`

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

## T8 — PASS
Fixture SHA-256: `c47dbe873fec7ec23e0850829e22e3431e18bf8ee2ef47416c3aa3e8fea45814`

Assertions:
- reply-to-invite -> 'Replied to invite', responded label, task created, correct POSTED alert text

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
Fixture SHA-256: `d387e4168a1f960f175d7c0b96410f828ce2fcae79168add841c5e1d8a217bf3`

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

## TF10 — PASS
Fixture SHA-256: `346f09a109a06bae397da94b1c6104c72675c31bf8d4330050e6a2503230bdfd`

Assertions:
- no-lead reply: critical alert POSTED with reply text, M7 No Lead Warn fired, zero lead/activity/task writes

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
