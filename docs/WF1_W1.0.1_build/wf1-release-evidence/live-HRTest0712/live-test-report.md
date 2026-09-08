# WF-1 live test report — HRTest0712

- Test double ID: `q35d4IvWttJZDiyP`
- Webhook path: `hr-test-hrtest0712-9bd5a4ee`
- Generated at: `2026-07-12T20:21:37.455Z`

| Test | Result | Execution | n8n status | Webhook |
|---|---|---:|---|---:|
| T1 | **PASS** | 9909 | success | 200 |
| T2 | **PASS** | 9910 | success | 200 |
| T3 | **PASS** | 9911 | success | 200 |
| T4 | **PASS** | 9912 | success | 200 |
| T5 | **PASS** | 9913 | success | 200 |
| T6 | **PASS** | 9914 | success | 200 |
| T7 | **PASS** | 9915 | success | 200 |
| T8-setup | **PASS** | 9916 | success | 200 |
| T8 | **PASS** | 9917 | success | 200 |
| TF10-setup | **PASS** | 9918 | success | 200 |
| TF10 | **PASS** | 9919 | success | 200 |

## T1 — PASS
Fixture SHA-256: `e0f0424e58d9da35763608b78472e990654941e29fccb410e9ee214a310ab6cd`

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

## T2 — PASS
Fixture SHA-256: `e0f0424e58d9da35763608b78472e990654941e29fccb410e9ee214a310ab6cd`

Assertions:
- identical replay stopped at Dedupe with no write nodes

Executed nodes:
```text
CONFIG
Dedupe
Respond to Webhook
Webhook
```

## T3 — PASS
Fixture SHA-256: `bcea5e6dbfa8d3244b6c04d60b91e063b3ddbb3e0d6735bc5c808f2eb4aa5c7a`

Assertions:
- existing lead path executed without duplicate lead or false warning

Executed nodes:
```text
CONFIG
Create Activity
Dedupe
IF Company
IF Email Found
IF Email Present
IF Org Found
IF Rank Allows Invited
Lead Create Gate
Lead Search
Normalize
Org From Search
Org Search
PID From Email
PID Resolved
Person Get
Person Search Email
Respond to Webhook
Select Existing Lead
Sent IF Lead ID
Switch
Webhook
```

## T4 — PASS
Fixture SHA-256: `15773a7e867918414f49eedbca9f99a06ac14fe39d560d9855e5031c39549ab7`

Assertions:
- critical alert fired first (with reply text); reply activity, task, responded label executed; M8 Slack absent

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

## T5 — PASS
Fixture SHA-256: `c3f6c9e655474fbb9cc578f593b59064db04d1beeb3c06a7098d4f594af9feea`

Assertions:
- late accepted effective rank and label remain at replied state

Executed nodes:
```text
CONFIG
Dedupe
M5 IF Email Found
M5 IF Email Present
M5 IF Lead ID
M5 IF Rank Accepted
M5 Labels Compute
M5 Lead Get
M5 Lead Patch
M5 PID From Email
M5 Person Get
M5 Person Patch Accepted
M5 Person Search Email
Normalize
Respond to Webhook
Switch
Webhook
```

## T6 — PASS
Fixture SHA-256: `e84e5da0e07a569620d974ec0bff288eba0c8810388fd1da21c3697d692be40f`

Assertions:
- empty email bypassed email search and Person create completed

Executed nodes:
```text
CONFIG
Create Activity
Create Lead
Dedupe
IF Company
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
Person Search URL
Respond to Webhook
Sent IF Lead ID
Switch
Webhook
```

## T7 — PASS
Fixture SHA-256: `503aa0450ba416f4d89a6a076876435135c6c547ea530819ceb1cbf4a42f7103`

Assertions:
- unknown reply: critical alert with actual text fired, M7 Slack Warn fired, zero Pipedrive writes

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
Fixture SHA-256: `f68d89fe21dfc181577cd9031a08924fe2d771d344cc171027788e253ac66256`

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
Fixture SHA-256: `08dd5e5454923144b84098bdc1756e08b94d52f0fa4194105731c81ad9d9bc9b`

Assertions:
- reply-to-invite -> 'Replied to invite', responded label, task created, correct alert text

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
Fixture SHA-256: `b101f772dde6c0d604478e826f314112d9e5cf8952226a792497aac517029583`

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
Fixture SHA-256: `07cc7566d9269d63979388eebd93519f11c0e8f9a02ee27594a554913686ea68`

Assertions:
- no-lead reply: critical alert delivered, M7 No Lead Warn fired, zero lead/activity/task writes

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
