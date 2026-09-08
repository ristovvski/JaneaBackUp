# WF-1 keys / identifiers reference

Non-secret identifiers for WF-1 "HeyReach Receiver" (n8n `2jdjKM2NJr473GdA`), live release W1.0.13.1 (versionId `da23d080-a0e0-4126-81c0-0cca60908435`). Source: deployed CONFIG (== production, verified DIFFS none).

> **NOT secrets.** These are Pipedrive field hashes, label UUIDs, channel ids, enum values and n8n ids - safe to share/commit. API tokens (Pipedrive / HeyReach / n8n) live ONLY in env and are NOT here. The HeyReach inbound-webhook token (part of the webhook path) is an auth secret and is REDACTED below.

## Person custom fields (Pipedrive personFields, all varchar)
| logical name | CONFIG.fields key | Pipedrive field hash |
|---|---|---|
| stage (LH stage) | `stage` | `f016efd8791291c591c1d49440018ab0bd23384d` |
| member_id (HeyReach lead id) | `member_id` | `010fc51128116e8c73ae2b33fd52fd4537451f2b` |
| public_id (LinkedIn slug) | `public_id` | `2339d1c7a7cda05651dff68ff82b2d56b20e241d` |
| li_url (lh_linkedin_profile_url) | `li_url` | `66f0af69bec838dc3f90bb3f16c7d6087d8dbb20` |
| company | `company` | `5a282f55e910cceeb960969460b8409b4c10d623` |
| position | `position` | `ab15ebd797c66ac010e47e543b7ec0226694d12b` |
| campaign (lh_campaign_name, person) | `campaign` | `86157bb49563191c17b4dc62580525f84417524c` |
| summary | `summary` | `f2a9a07d15d2890e45add72d8e86c76dcf080e51` |
| connected_at (date) | `connected_at` | `b03b86666936a46f063dfff6a922ef884fdefac4` |
| conversation | `conversation` | `f5c577e4f48daff068e577105897f5f44fb0072f` |
| source (enum) | `source` | `6070ae31f09228f95048b0f68982b1cd4d3a684a` |
| person_location (LinkedIn Location) | `person_location` | `db219a0b68aa164d0aed1f7791687c5ae788b7ae` |
| medium (W1.0.11) | `person_medium` | `961698945b0329b367da11916a94f10ff7ba71fe` |
| event_name (Event name, W1.0.13) | `person_event_name` | `ab5540d2ca45905dfb1434c0fe4971cc5790de3f` |
| marketing_hypothesis (W1.0.13) | `person_hypothesis` | `8bdae1a91272e92b335e9e99f668cde659b6daae` |

## Lead / deal custom fields
| logical name | CONFIG.fields key | Pipedrive field hash |
|---|---|---|
| Campaign (lead-per-campaign match key, W1.0.11) | `lead_campaign` | `1cd81dfcac8a5583935ff4b60e284d0e580db0b6` |

## Lead labels (deal-label UUIDs)
| label | UUID |
|---|---|
| cold | `a6d359b0-6a45-11ed-ab46-5b95b19fcb18` |
| connected | `ca698a50-bdfb-11ef-8172-510383583b0e` |
| responded | `c9d4b550-bcf3-11ef-a843-357f91e826ec` |

## Enums / values
| key | value | meaning |
|---|---|---|
| source_value | `446` | person Source enum = Cold Outreach |
| lead_channel | `578` | lead channel id |
| lead_channel_id_value | `HeyReach` | lead channel_id string |
| melisa_user_id | `16340280` | lead/activity owner |
| activity_type_msg | `linkedin_messaging` | LinkedIn message activity type |
| org_website_field | `website` | standard org field |
| create_assignment_task | `false` | M8 task kill-switch |
| stageRank | `{"Invited": 1, "Accepted": 2, "First follow-up sent": 3, "Replied to invite": 4, "Replied": 4}` | forward-only stage ranking |
| event_marker_canon | `{"events visiting": "Events Visiting"}` | bracket-content (lc) -> Marketing Hypothesis |

## Slack channels
| key | id | note |
|---|---|---|
| slack_channel_replies | `C0B8GCVNR5W` | reply alerts (temp = ops) |
| slack_channel_ops | `C0B8GCVNR5W` | warns/errors + event-marker warn |
| slack_channel (alias) | `C0B8GCVNR5W` | legacy alias |
| team channel (NOT used; W1.0.10 gate-blocked) | `C07LTD8UT70` | flip target once bot /invited |

## n8n / workflow ids
| item | id |
|---|---|
| workflow id | `2jdjKM2NJr473GdA` |
| live versionId | `da23d080-a0e0-4126-81c0-0cca60908435` (W1.0.13.1) |
| error workflow | `BbrXPABgOaaTJjD6` |
| n8n project id | `57BsS5BV36DRX0Cw` |
| production webhook path | `hr-<REDACTED>` (full path incl. HeyReach token is an inbound-auth secret; in n8n / reference doc) |
| Slack credential ref | `Udq1K604RpJqg1cR` ("Slack account 3") - credential REFERENCE, not the token |
| pipedrive_base | `https://janeasystems.pipedrive.com` |
| W1.0.13 node: IF Event Marker Bad | `0e130001-0000-4013-8000-000000000001` |
| W1.0.13 node: Event Marker Warn | `0e130002-0000-4013-8000-000000000002` |

