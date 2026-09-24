"""WF-2 Smartlead Receiver - deterministic builder (Phase B).

Emits `WF-2 Smartlead Receiver - built.json` + `... api-payload.json`.
Deterministic: fixed node ids, fixed webhook path, LF bytes, byte-identical on re-run.
Architecture: wf2-architecture.md SS1-SS6. Parity: wf2-parity-conditions.md.
Nik's amendments: no key rotation; forward map from CONFIG; First-email-sent + EMAIL_REPLIED;
org LinkedIn = lh_linkedin_profile_url; write standard person fields too ("fill as much as possible").
"""
import argparse, json, sys
from pathlib import Path

# the ops-warn Slack node for webhook auth reuses the branch library's factory
from wf_item_guard import violations as item_violations
from build_wf2_branches import slack

WEBHOOK_PATH = "{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}"          # fixed (deterministic); rotate only via a new release
ERROR_WORKFLOW = "BbrXPABgOaaTJjD6"
# E (Nik): WF-2 must post under its OWN Slack identity, not the HeyReach app. Nik creates a new
# Slack app + n8n credential named "Slack WF-2"; until it exists we stay on the shared identity.
# Swapping is a two-line edit here + rebuild + deploy - no graph change, no node rewiring.
# WF-ERR intentionally keeps the shared identity: it serves both workflows, and its header now
# names the failed workflow (addendum C), so the identity no longer implies which one broke.
# E RESOLVED: WF-2 posts under its own Slack app. Gate-proven 2026-07-29 - a post through this
# credential reached C0B8GCVNR5W as app_id A0BLETEHYBF (bot "Smarlead"), distinct from the
# HeyReach app A0BFX7C664S. The bot was already a channel member, so no /invite was needed.
# WF-ERR intentionally stays on the HeyReach credential: it serves both workflows and its
# header now names the failed workflow (addendum C).
SLACK_CRED_HEYREACH = {"slackApi": {"id": "Udq1K604RpJqg1cR", "name": "Heyreach Slack"}}
SLACK_CRED = {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Slack WF-2"}}

# ---------------------------------------------------------------- CONFIG
CONFIG = {
    "WRITE_MODE": "shadow",
    "pipedrive_base": "https://janeasystems.pipedrive.com",
    "pd_api": "https://api.pipedrive.com",
    "sl_api": "https://server.smartlead.ai/api/v1",
    "owner_id": 16340280,
    # Phase D: all posts land in Nik's channel until the flip. The team channel C07LTD8UT70 is
    # the flip-time value - and note the n8n bot was `channel_not_found` there in W1.0.10, so
    # the flip needs an /invite + post check, not just this one-liner.
    "slack_channel_replies": "C0B8GCVNR5W",
    "slack_channel_replies_at_flip": "C07LTD8UT70",
    "slack_channel_ops": "C0B8GCVNR5W",
    "fields": {
        # person - lh_ mirrors
        "position_lh": "ab15ebd797c66ac010e47e543b7ec0226694d12b",
        "title_std_cf": "0b72db8f36929631afc7c449de2914c3580df7ca",
        "title_linkedin": "f8edcb0113a9fe4082b4116a4b3d8e085b971eed",
        "company_lh": "5a282f55e910cceeb960969460b8409b4c10d623",
        "linkedin_lh": "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20",
        "linkedin_profile": "b59a7d0af178f3149381efd9a8476370b19ca3b5",
        "location_lh": "db219a0b68aa164d0aed1f7791687c5ae788b7ae",
        "campaign": "86157bb49563191c17b4dc62580525f84417524c",
        "hypothesis": "8bdae1a91272e92b335e9e99f668cde659b6daae",
        "medium": "961698945b0329b367da11916a94f10ff7ba71fe",
        "event_name": "ab5540d2ca45905dfb1434c0fe4971cc5790de3f",
        "source": "6070ae31f09228f95048b0f68982b1cd4d3a684a",
        # lead
        "lead_campaign": "1cd81dfcac8a5583935ff4b60e284d0e580db0b6",
        "lead_opportunity_type": "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84",
        # org
        "org_website_a": "2064369b47d625221e85093240d25b42110d8da4",
        "org_website_b": "7ef47bd78dae7bbf48da9d837c3fbda079a44de9",
        "org_website_lh": "c8c70fc525238b1c709857ea40f4d60cd2575d37",
        "org_linkedin_lh": "ed932dfc4870dcd72fa7b4eadb67da38d169299b",
    },
    # standard (non-custom) person fields we also fill - Nik's field-fill directive
    # B17: EMPTY on purpose. job_title (and postal_address/im/notes/birthday) are contact-sync
    # fields; this tenant has contact sync disabled and Pipedrive answers 403. Titles go to the
    # three custom-field mirrors instead. Do not re-add without checking the tenant setting.
    "std_person_fields": {},
    "pd_forbidden_std_fields": ["job_title", "postal_address", "im", "notes", "birthday"],
    "labels": {
        "cold": "a6d359b0-6a45-11ed-ab46-5b95b19fcb18",
        "connected": "ca698a50-bdfb-11ef-8172-510383583b0e",
        "responded": "c9d4b550-bcf3-11ef-a843-357f91e826ec",
        "dnc": "52a7c290-fc73-11f0-ad98-81d4703453f3",
    },
    "lead_channel": 578,
    "lead_opportunity_type_value": 480,
    "source_value": 446,
    "medium_value": "eMail",
    "marker_canon": {
        "sales sprint": "Sales Sprint",
        "events visiting": "Events Visiting",
        "trigger-based campaign": "Trigger-based Campaign",
        "client similarity": "Client Similarity",
        "lead nurture": "__NURTURE__",
        "lead nurturing": "__NURTURE__",
    },
    # Phase C1: pulled live from GET /leads/fetch-categories (2026-07-28). Names are the SL
    # writeback contract; an unknown/absent name -> null id -> the SL Category node skips (K1).
    "category_map": {
        "Interested": 1,
        "Meeting Request": 2,
        "Not Interested": 3,
        "Do Not Contact": 4,
        "Information Request": 5,
        "Out Of Office": 6,
        "Wrong Person": 7,
        "Uncategorizable by Ai": 8,
        "Sender Originated Bounce": 9,
        "No Longer Working There": 16598,
    },
    "forwardable_categories": ["Interested", "Meeting Request", "Not Interested", "Information Request"],
    "forward_owner_map": {        # sheet column-1 owner name -> mailbox (trailing spaces trimmed, Test->melisa)
        "Toby": "toby@janeasystems.com",
        "Andreas": "andreas@janeasystems.com",
        "Mario": "mario@janeasystems.com",
        "Mirza": "mirza@janeasystems.com",
        "Melisa": "melisa@janeasystems.com",
        "Can": "can@janeasystems.com",
        "Test": "melisa@janeasystems.com",
        "Bill": "bill.sanders@janeasystems.com",
        "Benedetto": "benedetto.proietti@janeasystems.com",
        "Sergey": "sergey@janeasystems.com",
        "James": "james@janeasystems.com",
        "Rune": "rune@janeasystems.com",
        "Chrissy": "chrissy@janeasystems.com",
        "Noah": "noah@janeasystems.com",
        # final ingestion: Matt Carothers is the only owner the registry added.
        # James (Jim Ash) was already mapped to this exact address, so that half of the
        # instruction is confirmatory - the map goes to 15 keys, not 16.
        "Matt": "matt@janeasystems.com",
    },
    # FULL registry ingested from "Janea All Inboxes ... (1.15.2025).csv" (see
    # wf1-release-evidence/inbox-registry-report.md): 699 rows -> 696 unique inboxes,
    # 3 exact duplicates collapsed, 0 conflicting owners, 0 malformed. 14 owners.
    # Keys are lowercased/trimmed; sorted here so the build stays byte-deterministic.
    "forward_inbox_map": {
        "pii-4cdf7db3@example.invalid": "Andreas",
        "pii-18613739@example.invalid": "Andreas",
        "pii-93f6b8a7@example.invalid": "Andreas",
        "pii-283b2bb5@example.invalid": "Andreas",
        "pii-d4b960a2@example.invalid": "Andreas",
        "pii-4cbed1b3@example.invalid": "Andreas",
        "pii-3d65214b@example.invalid": "Andreas",
        "pii-9b4ddda4@example.invalid": "Andreas",
        "pii-188f9256@example.invalid": "Andreas",
        "pii-d136a8ab@example.invalid": "Andreas",
        "pii-99dbf228@example.invalid": "Andreas",
        "pii-e81f2bc3@example.invalid": "Andreas",
        "pii-a5788372@example.invalid": "Andreas",
        "pii-d93a8548@example.invalid": "Andreas",
        "pii-2d0ea418@example.invalid": "Andreas",
        "pii-ff74a88e@example.invalid": "Andreas",
        "pii-42beeae2@example.invalid": "Andreas",
        "pii-0a4a9a94@example.invalid": "Andreas",
        "pii-a47491c1@example.invalid": "Andreas",
        "pii-faf68af6@example.invalid": "Andreas",
        "pii-5a75f5f1@example.invalid": "Andreas",
        "pii-849d37a0@example.invalid": "Andreas",
        "pii-ee99fc9c@example.invalid": "Andreas",
        "pii-417ad91f@example.invalid": "Andreas",
        "pii-11cb47cd@example.invalid": "Andreas",
        "pii-7ce070ed@example.invalid": "Andreas",
        "pii-3dab62cc@example.invalid": "Andreas",
        "pii-c276214d@example.invalid": "Andreas",
        "pii-67ccd74e@example.invalid": "Andreas",
        "pii-a3f0e37b@example.invalid": "Andreas",
        "pii-ef8929e9@example.invalid": "Andreas",
        "pii-3112e2ce@example.invalid": "Andreas",
        "pii-6c5c53b9@example.invalid": "Andreas",
        "pii-b28cbbee@example.invalid": "Andreas",
        "pii-7cf7b40f@example.invalid": "Andreas",
        "pii-3abc6214@example.invalid": "Andreas",
        "pii-772aea73@example.invalid": "Andreas",
        "pii-3855d66e@example.invalid": "Can",
        "pii-eb0ce9df@example.invalid": "Can",
        "pii-622be12f@example.invalid": "Can",
        "pii-b60c2ca2@example.invalid": "Mirza",
        "pii-42fb3a5e@example.invalid": "Melisa",
        "pii-bf305533@example.invalid": "Mirza",
        "pii-d1d03eae@example.invalid": "Mirza",
        "pii-320ef801@example.invalid": "Melisa",
        "pii-6e9ec482@example.invalid": "Melisa",
        "pii-f897ed2b@example.invalid": "Melisa",
        "pii-54f6419b@example.invalid": "Melisa",
        "pii-638c01fd@example.invalid": "Melisa",
        "pii-0664535b@example.invalid": "Mirza",
        "pii-bce996fc@example.invalid": "Mirza",
        "pii-ecbbd84a@example.invalid": "Mirza",
        "pii-7d78f32a@example.invalid": "Mirza",
        "pii-2997fe23@example.invalid": "Mirza",
        "pii-b0eeff8c@example.invalid": "Mirza",
        "pii-35094bc0@example.invalid": "Mirza",
        "pii-0b955375@example.invalid": "Mirza",
        "pii-60d37470@example.invalid": "Can",
        "pii-bf65c8aa@example.invalid": "Can",
        "pii-ed2c6af1@example.invalid": "Can",
        "pii-21576558@example.invalid": "Benedetto",
        "pii-cadf5a87@example.invalid": "Benedetto",
        "pii-681b72b8@example.invalid": "Benedetto",
        "pii-4aa15de2@example.invalid": "Benedetto",
        "pii-dc0ff998@example.invalid": "Benedetto",
        "pii-382db86c@example.invalid": "Benedetto",
        "pii-ba12d09f@example.invalid": "Benedetto",
        "pii-6a02848c@example.invalid": "Benedetto",
        "pii-070fb5cb@example.invalid": "Benedetto",
        "pii-e269022e@example.invalid": "Benedetto",
        "pii-94773456@example.invalid": "Benedetto",
        "pii-178a6b43@example.invalid": "Benedetto",
        "pii-7476b607@example.invalid": "Benedetto",
        "pii-63addf1e@example.invalid": "Benedetto",
        "pii-fd3b23cc@example.invalid": "Benedetto",
        "pii-c2de7514@example.invalid": "Benedetto",
        "pii-f4086ffd@example.invalid": "Benedetto",
        "pii-b0923b44@example.invalid": "Benedetto",
        "pii-c3702d51@example.invalid": "Benedetto",
        "pii-abd6bc5f@example.invalid": "Benedetto",
        "pii-fec7ad74@example.invalid": "Can",
        "pii-2865d35c@example.invalid": "Can",
        "pii-2ee9da8c@example.invalid": "Can",
        "pii-8e39a6a6@example.invalid": "Can",
        "pii-885da5c5@example.invalid": "Can",
        "pii-153b5937@example.invalid": "Can",
        "pii-3599476c@example.invalid": "Can",
        "pii-aa8167e6@example.invalid": "Bill",
        "pii-582d6f22@example.invalid": "Bill",
        "pii-46aa85d2@example.invalid": "Bill",
        "pii-cb7ce3c1@example.invalid": "Bill",
        "pii-8cf54059@example.invalid": "Bill",
        "pii-ffefd4b3@example.invalid": "Bill",
        "pii-47500ba2@example.invalid": "Bill",
        "pii-2144317b@example.invalid": "Bill",
        "pii-3c6dbc3e@example.invalid": "Bill",
        "pii-ddf28ac1@example.invalid": "Bill",
        "pii-a73743b4@example.invalid": "Bill",
        "pii-2a02c418@example.invalid": "Bill",
        "pii-8b1dc904@example.invalid": "Bill",
        "pii-0c21d444@example.invalid": "Bill",
        "pii-50f75a38@example.invalid": "Bill",
        "pii-e654c67a@example.invalid": "Bill",
        "pii-28d2c7e1@example.invalid": "Bill",
        "pii-20160eec@example.invalid": "Bill",
        "pii-50f267f5@example.invalid": "Bill",
        "pii-621de0e8@example.invalid": "Bill",
        "pii-a64b78e1@example.invalid": "Bill",
        "pii-0f133478@example.invalid": "Bill",
        "pii-13dc3137@example.invalid": "Bill",
        "pii-977cd51e@example.invalid": "Bill",
        "pii-4d69327f@example.invalid": "Bill",
        "pii-644836f7@example.invalid": "Bill",
        "pii-a8bbcd56@example.invalid": "Bill",
        "pii-2a032491@example.invalid": "Bill",
        "pii-78d019fa@example.invalid": "Bill",
        "pii-420d0e09@example.invalid": "Bill",
        "pii-8b3d3dfe@example.invalid": "Bill",
        "pii-d6103b5e@example.invalid": "Bill",
        "pii-29acec2e@example.invalid": "Bill",
        "pii-3d434315@example.invalid": "Bill",
        "pii-f01db5be@example.invalid": "Bill",
        "pii-519f94ac@example.invalid": "Bill",
        "pii-e84ca71f@example.invalid": "Bill",
        "pii-15e8c9e3@example.invalid": "Bill",
        "pii-9b8c0560@example.invalid": "Bill",
        "pii-7ff793b7@example.invalid": "Bill",
        "pii-3698801b@example.invalid": "Bill",
        "pii-98d8aa3b@example.invalid": "Bill",
        "pii-aded70fb@example.invalid": "Mirza",
        "pii-dec3d98e@example.invalid": "Melisa",
        "pii-328cb47b@example.invalid": "Mirza",
        "pii-0ab46ee3@example.invalid": "Can",
        "pii-d94d0ba1@example.invalid": "Can",
        "pii-ae5be964@example.invalid": "Can",
        "pii-107466ad@example.invalid": "Can",
        "pii-b1d78b68@example.invalid": "Can",
        "pii-72b9c951@example.invalid": "Can",
        "pii-da0e77c7@example.invalid": "Can",
        "pii-e7edb96b@example.invalid": "Can",
        "pii-1ab46e34@example.invalid": "Can",
        "pii-f378fae0@example.invalid": "Can",
        "pii-78191528@example.invalid": "Can",
        "pii-9db11a00@example.invalid": "Can",
        "pii-9160b6a3@example.invalid": "Can",
        "pii-ad1e0224@example.invalid": "Can",
        "pii-66b710e0@example.invalid": "Can",
        "pii-9c1e2531@example.invalid": "Can",
        "pii-35f0c569@example.invalid": "Can",
        "pii-d190afd1@example.invalid": "Can",
        "pii-8d67bd0c@example.invalid": "Can",
        "pii-b159b914@example.invalid": "Can",
        "pii-4bccd54f@example.invalid": "Can",
        "pii-7213cce4@example.invalid": "Can",
        "pii-cda9644e@example.invalid": "Can",
        "pii-efef61c6@example.invalid": "Can",
        "pii-9cb3fd0b@example.invalid": "Can",
        "pii-1fce0a99@example.invalid": "Can",
        "pii-f15727d7@example.invalid": "Can",
        "pii-948ea082@example.invalid": "Can",
        "pii-ca945b48@example.invalid": "Can",
        "pii-3a35b305@example.invalid": "Can",
        "pii-48f81b06@example.invalid": "Chrissy",
        "pii-95e179f0@example.invalid": "Chrissy",
        "pii-94f57d19@example.invalid": "Chrissy",
        "pii-b4622930@example.invalid": "Chrissy",
        "pii-f6f1f511@example.invalid": "Chrissy",
        "pii-52a483d6@example.invalid": "Chrissy",
        "pii-c6fb1ee9@example.invalid": "Chrissy",
        "pii-b4401398@example.invalid": "Chrissy",
        "pii-52b02f88@example.invalid": "Chrissy",
        "pii-45e8b0c8@example.invalid": "Chrissy",
        "pii-f7a73b91@example.invalid": "Chrissy",
        "pii-a9c0c4f7@example.invalid": "Chrissy",
        "pii-af61fc1d@example.invalid": "Chrissy",
        "pii-86314fed@example.invalid": "Chrissy",
        "pii-5d4c1752@example.invalid": "Chrissy",
        "pii-a197ad65@example.invalid": "Chrissy",
        "pii-cbe01d7d@example.invalid": "Chrissy",
        "pii-969484f9@example.invalid": "Chrissy",
        "pii-d7a9c01d@example.invalid": "Chrissy",
        "pii-27341ad0@example.invalid": "Chrissy",
        "pii-73f3a515@example.invalid": "Chrissy",
        "pii-7d0f8e37@example.invalid": "Chrissy",
        "pii-f06c1226@example.invalid": "Chrissy",
        "pii-8519edd9@example.invalid": "Chrissy",
        "pii-63e1e6b3@example.invalid": "Chrissy",
        "pii-4329a376@example.invalid": "Chrissy",
        "pii-d70a5454@example.invalid": "Chrissy",
        "pii-f7fe0941@example.invalid": "Chrissy",
        "pii-b37a3cad@example.invalid": "Chrissy",
        "pii-467013a5@example.invalid": "Chrissy",
        "pii-6e864061@example.invalid": "Chrissy",
        "pii-51c83baf@example.invalid": "Chrissy",
        "pii-7eb570e3@example.invalid": "Chrissy",
        "pii-1b1a8605@example.invalid": "Chrissy",
        "pii-4c3584c0@example.invalid": "Chrissy",
        "pii-ecad2da8@example.invalid": "Chrissy",
        "pii-7516f63f@example.invalid": "Chrissy",
        "pii-79a5058b@example.invalid": "Chrissy",
        "pii-60d9e198@example.invalid": "Chrissy",
        "pii-a695ef8a@example.invalid": "Chrissy",
        "pii-0607a07c@example.invalid": "Chrissy",
        "pii-552b8354@example.invalid": "Chrissy",
        "pii-c5f8728a@example.invalid": "Chrissy",
        "pii-7dd4aa6e@example.invalid": "Chrissy",
        "pii-564afaf8@example.invalid": "James",
        "pii-f35b78a1@example.invalid": "James",
        "pii-8f59564a@example.invalid": "James",
        "pii-b7a05c8a@example.invalid": "James",
        "pii-139cead9@example.invalid": "James",
        "pii-3f2447bc@example.invalid": "James",
        "pii-480edd8f@example.invalid": "James",
        "pii-28cc2e4f@example.invalid": "James",
        "pii-3d88c956@example.invalid": "James",
        "pii-4ceb18c8@example.invalid": "James",
        "pii-68638b0f@example.invalid": "James",
        "pii-ded95e02@example.invalid": "James",
        "pii-385a734a@example.invalid": "James",
        "pii-d804d5c9@example.invalid": "James",
        "pii-759d7169@example.invalid": "James",
        "pii-eae2071c@example.invalid": "James",
        "pii-eeb984e3@example.invalid": "James",
        "pii-7e06dc6c@example.invalid": "James",
        "pii-7efd318f@example.invalid": "James",
        "pii-d77046ac@example.invalid": "James",
        "pii-1603097f@example.invalid": "James",
        "james@workwithjaneasystems.com": "James",
        "pii-f0f13a39@example.invalid": "James",
        "pii-40f8e863@example.invalid": "James",
        "pii-cff61e3c@example.invalid": "James",
        "pii-9296e9bf@example.invalid": "James",
        "pii-a1b134ac@example.invalid": "James",
        "pii-1a1fb861@example.invalid": "James",
        "pii-81817340@example.invalid": "James",
        "pii-51be2e7a@example.invalid": "James",
        "pii-4906b0e9@example.invalid": "James",
        "pii-fc9dc464@example.invalid": "James",
        "pii-5f736be6@example.invalid": "James",
        "pii-3b4b7b7b@example.invalid": "James",
        "pii-7f5d3eb7@example.invalid": "James",
        "pii-6ab2c15c@example.invalid": "James",
        "pii-488cca99@example.invalid": "James",
        "pii-523a9b2d@example.invalid": "James",
        "pii-0a898949@example.invalid": "James",
        "pii-72319f4a@example.invalid": "James",
        "pii-aee696fe@example.invalid": "James",
        "pii-86eab66b@example.invalid": "James",
        "pii-05c973e5@example.invalid": "James",
        "jamesa@workwithjaneasystems.com": "James",
        "pii-16f472cd@example.invalid": "Andreas",
        "pii-3a126d76@example.invalid": "Andreas",
        "pii-b5b4762a@example.invalid": "Andreas",
        "pii-decb705a@example.invalid": "Andreas",
        "pii-eae6f2cf@example.invalid": "Andreas",
        "pii-06ea46a5@example.invalid": "Andreas",
        "pii-a93b28cf@example.invalid": "Andreas",
        "pii-2bd53b43@example.invalid": "Andreas",
        "pii-4fccc38d@example.invalid": "Andreas",
        "pii-20ea30fc@example.invalid": "Andreas",
        "pii-d7cbd86a@example.invalid": "Andreas",
        "pii-fc48ceaf@example.invalid": "Andreas",
        "pii-c543a565@example.invalid": "Andreas",
        "pii-cd2bb98c@example.invalid": "Mario",
        "pii-8e7b8130@example.invalid": "Mirza",
        "pii-49ac5713@example.invalid": "Melisa",
        "pii-4d8f38ce@example.invalid": "Mirza",
        "pii-35b5bee8@example.invalid": "Mario",
        "pii-27bb21a4@example.invalid": "Mario",
        "pii-dea817e7@example.invalid": "Mario",
        "pii-f8d284e2@example.invalid": "Mario",
        "pii-6c32b556@example.invalid": "Mario",
        "pii-c5058adf@example.invalid": "Mario",
        "pii-1ee93c13@example.invalid": "Mario",
        "pii-537efe24@example.invalid": "Mario",
        "pii-81b7a21a@example.invalid": "Mario",
        "pii-cbfdf4fb@example.invalid": "Mario",
        "pii-65b56232@example.invalid": "Mario",
        "pii-92f18a68@example.invalid": "Mario",
        "pii-f92e8d14@example.invalid": "Mario",
        "pii-332337be@example.invalid": "Mario",
        "pii-7491f677@example.invalid": "Mario",
        "pii-fa14fbd5@example.invalid": "Mario",
        "pii-a1dad567@example.invalid": "Mario",
        "pii-3c509af1@example.invalid": "Mario",
        "pii-2e3e98b3@example.invalid": "Mario",
        "pii-39dbfbe4@example.invalid": "Mario",
        "pii-846f95dd@example.invalid": "Mario",
        "pii-6c11e926@example.invalid": "Mario",
        "pii-940910d3@example.invalid": "Mario",
        "pii-2831843b@example.invalid": "Mario",
        "pii-a98edcff@example.invalid": "Mario",
        "pii-9d1457fa@example.invalid": "Mario",
        "pii-105db96b@example.invalid": "Mario",
        "pii-8f5b2e69@example.invalid": "Mario",
        "pii-b681caf5@example.invalid": "Mario",
        "pii-1f06971b@example.invalid": "Mario",
        "pii-66eeab1c@example.invalid": "Mario",
        "pii-e6eef3df@example.invalid": "Mario",
        "pii-068946b2@example.invalid": "Mario",
        "pii-77de3ab6@example.invalid": "Mario",
        "pii-4807e2b1@example.invalid": "Mario",
        "pii-91ff88fc@example.invalid": "Mario",
        "pii-4b3a9de4@example.invalid": "Mario",
        "pii-45f20ed9@example.invalid": "Mario",
        "pii-5093cd16@example.invalid": "Mario",
        "pii-dc89b3f0@example.invalid": "Mario",
        "pii-7483e649@example.invalid": "Mario",
        "pii-bc08973f@example.invalid": "Mario",
        "pii-c904d13d@example.invalid": "Mario",
        "pii-9aafce64@example.invalid": "Mario",
        "pii-d86f71d1@example.invalid": "Mario",
        "pii-7e260d0d@example.invalid": "Mario",
        "pii-0bc0efba@example.invalid": "Mario",
        "pii-9d0803d4@example.invalid": "Mario",
        "pii-ac7dc209@example.invalid": "Mario",
        "pii-50a17107@example.invalid": "Mario",
        "pii-8be63d47@example.invalid": "Mario",
        "pii-e6469ae5@example.invalid": "Mario",
        "pii-3d9fd73e@example.invalid": "Mario",
        "pii-d1810320@example.invalid": "Mario",
        "pii-4c1e0dd7@example.invalid": "Mario",
        "pii-d1f235df@example.invalid": "Mario",
        "pii-1a3d62a0@example.invalid": "Mario",
        "pii-93c21bc3@example.invalid": "Mario",
        "pii-7364f3f0@example.invalid": "Mario",
        "pii-d13b09f3@example.invalid": "Mario",
        "pii-63742942@example.invalid": "Mario",
        "pii-d4aae888@example.invalid": "Mario",
        "pii-f06d8290@example.invalid": "Mario",
        "pii-47d6297e@example.invalid": "Mario",
        "pii-b11bc06c@example.invalid": "Mario",
        "pii-44232812@example.invalid": "Mario",
        "pii-6b9f81bf@example.invalid": "Mario",
        "pii-a591e92a@example.invalid": "Mario",
        "pii-ba3d563a@example.invalid": "Mario",
        "pii-3740e234@example.invalid": "Mario",
        "pii-2b30e48f@example.invalid": "Mario",
        "pii-a1011384@example.invalid": "Mario",
        "pii-95534f2a@example.invalid": "Mario",
        "pii-92aef1a3@example.invalid": "Mario",
        "pii-24802629@example.invalid": "Mario",
        "pii-cfd46fe4@example.invalid": "Mario",
        "pii-f6e40946@example.invalid": "Mario",
        "pii-1203759e@example.invalid": "Mario",
        "pii-fe7df8c0@example.invalid": "Mario",
        "pii-b9ee41eb@example.invalid": "Mario",
        "pii-afe1c8f0@example.invalid": "Mario",
        "pii-e13cdc61@example.invalid": "Mario",
        "pii-6de300e0@example.invalid": "Mario",
        "pii-5e9a5a09@example.invalid": "Matt",
        "matt@gojaneasystems.com": "Matt",
        "pii-ebf17587@example.invalid": "Matt",
        "pii-f79fea0e@example.invalid": "Matt",
        "pii-cfc31e5e@example.invalid": "Matt",
        "pii-d9d38b42@example.invalid": "Matt",
        "pii-2543078c@example.invalid": "Matt",
        "pii-9f82d36c@example.invalid": "Matt",
        "pii-8f331694@example.invalid": "Matt",
        "pii-7f708643@example.invalid": "Matt",
        "pii-34a5c431@example.invalid": "Matt",
        "pii-2d9e1aa5@example.invalid": "Matt",
        "pii-550ea977@example.invalid": "Matt",
        "pii-189edb91@example.invalid": "Matt",
        "pii-a9de7b6e@example.invalid": "Matt",
        "pii-ddf1c25f@example.invalid": "Matt",
        "pii-a270fb13@example.invalid": "Matt",
        "pii-7f1576e6@example.invalid": "Matt",
        "pii-7a5a45c5@example.invalid": "Matt",
        "pii-dfbd348f@example.invalid": "Matt",
        "matt@teamjaneasystems.com": "Matt",
        "pii-f0c6811d@example.invalid": "Matt",
        "pii-4a2d1083@example.invalid": "Matt",
        "mattc@gojaneasystems.com": "Matt",
        "pii-a0ed5829@example.invalid": "Matt",
        "pii-39ef7844@example.invalid": "Matt",
        "pii-0a0d5350@example.invalid": "Matt",
        "pii-d4858217@example.invalid": "Matt",
        "pii-4d330955@example.invalid": "Matt",
        "pii-760b59d6@example.invalid": "Matt",
        "pii-9e741227@example.invalid": "Matt",
        "pii-5486e03a@example.invalid": "Matt",
        "pii-a4bd529f@example.invalid": "Matt",
        "pii-697a5098@example.invalid": "Matt",
        "pii-fde7f8af@example.invalid": "Matt",
        "pii-0fa0e5f2@example.invalid": "Matt",
        "pii-018e7e74@example.invalid": "Matt",
        "pii-e3efb15e@example.invalid": "Matt",
        "pii-bacd091c@example.invalid": "Matt",
        "pii-95b16bde@example.invalid": "Matt",
        "pii-732b7740@example.invalid": "Matt",
        "pii-ddb6facc@example.invalid": "Matt",
        "mattc@teamjaneasystems.com": "Matt",
        "pii-1a026e7b@example.invalid": "Matt",
        "pii-e9a55c5c@example.invalid": "Mirza",
        "pii-975a25de@example.invalid": "Mirza",
        "pii-c241e773@example.invalid": "Melisa",
        "pii-ee7fb298@example.invalid": "Mirza",
        "pii-fa1ed629@example.invalid": "Melisa",
        "pii-a6ebd7ec@example.invalid": "Melisa",
        "pii-7b736c0b@example.invalid": "Melisa",
        "pii-cdc5e8f0@example.invalid": "Melisa",
        "pii-99bab230@example.invalid": "Melisa",
        "pii-c45eaa90@example.invalid": "Mirza",
        "pii-352f72c2@example.invalid": "Mirza",
        "pii-0381ce6f@example.invalid": "Mirza",
        "pii-49e5e4f9@example.invalid": "Mirza",
        "pii-b6b96cc1@example.invalid": "Mirza",
        "pii-9cee8d69@example.invalid": "Mirza",
        "pii-ad7c5201@example.invalid": "Mirza",
        "pii-2eaccc39@example.invalid": "Mirza",
        "pii-e1d688bd@example.invalid": "Mirza",
        "pii-06d62201@example.invalid": "Mirza",
        "pii-86d242d2@example.invalid": "Mirza",
        "pii-0de9c5c2@example.invalid": "Mirza",
        "pii-9273be07@example.invalid": "Mirza",
        "pii-d4430304@example.invalid": "Mirza",
        "pii-01699dae@example.invalid": "Mirza",
        "pii-6123ea71@example.invalid": "Mirza",
        "pii-7e856857@example.invalid": "Mirza",
        "pii-c10a30c8@example.invalid": "Mirza",
        "pii-08c426d4@example.invalid": "Mirza",
        "pii-5f5e5408@example.invalid": "Mirza",
        "pii-f8418cb6@example.invalid": "Mirza",
        "pii-64f68426@example.invalid": "Mirza",
        "pii-1b468da3@example.invalid": "Mirza",
        "pii-0fa4a241@example.invalid": "Mirza",
        "pii-70ad9d40@example.invalid": "Mirza",
        "pii-1cf0abe7@example.invalid": "Mirza",
        "pii-1cdc2794@example.invalid": "Mirza",
        "pii-b64f359f@example.invalid": "Mirza",
        "pii-09556642@example.invalid": "Mirza",
        "pii-a6672ba4@example.invalid": "Mirza",
        "pii-676b2e51@example.invalid": "Mirza",
        "pii-f17b2cdf@example.invalid": "Mirza",
        "pii-87431248@example.invalid": "Mirza",
        "pii-340fbcd3@example.invalid": "Mirza",
        "pii-888a5a01@example.invalid": "Mirza",
        "pii-16599d9a@example.invalid": "Mirza",
        "pii-9005f307@example.invalid": "Mirza",
        "pii-1e77dca8@example.invalid": "Mirza",
        "pii-01f3e216@example.invalid": "Mirza",
        "pii-9b16d8a4@example.invalid": "Mirza",
        "pii-693fcc69@example.invalid": "Mirza",
        "pii-81a3da87@example.invalid": "Mirza",
        "pii-94b20fa1@example.invalid": "Mirza",
        "pii-82f6b16a@example.invalid": "Mario",
        "pii-80992526@example.invalid": "Mario",
        "pii-4e268dca@example.invalid": "Mario",
        "pii-51c8f2e9@example.invalid": "Mario",
        "pii-2fea4fa2@example.invalid": "Noah",
        "pii-43bb5464@example.invalid": "Noah",
        "noah@janeaaaisolutions.co": "Noah",
        "pii-99e65cad@example.invalid": "Noah",
        "pii-be477b9c@example.invalid": "Noah",
        "pii-40eeb759@example.invalid": "Noah",
        "pii-9ca167fe@example.invalid": "Noah",
        "pii-5e3bb6d1@example.invalid": "Noah",
        "pii-e0c9c927@example.invalid": "Noah",
        "pii-87cc3e51@example.invalid": "Noah",
        "pii-62d0a772@example.invalid": "Noah",
        "pii-ed7dd7e1@example.invalid": "Noah",
        "pii-16ec568a@example.invalid": "Noah",
        "pii-51cf6fa4@example.invalid": "Noah",
        "pii-9c1076a2@example.invalid": "Noah",
        "pii-f2834abc@example.invalid": "Noah",
        "pii-77e54d77@example.invalid": "Noah",
        "pii-6c822b6e@example.invalid": "Noah",
        "pii-0baacb1a@example.invalid": "Noah",
        "pii-95c02529@example.invalid": "Noah",
        "pii-af51dd78@example.invalid": "Noah",
        "pii-9b3ebffd@example.invalid": "Noah",
        "pii-e37b8d4e@example.invalid": "Noah",
        "pii-51e9a7f2@example.invalid": "Noah",
        "noahk@janeaaaisolutions.co": "Noah",
        "pii-53b1fddd@example.invalid": "Noah",
        "pii-a5c793b9@example.invalid": "Noah",
        "pii-15e07000@example.invalid": "Noah",
        "pii-a4c6d055@example.invalid": "Noah",
        "pii-2304b974@example.invalid": "Noah",
        "pii-51848c40@example.invalid": "Noah",
        "pii-8af9db61@example.invalid": "Noah",
        "pii-7905aa9a@example.invalid": "Noah",
        "pii-243b67bd@example.invalid": "Noah",
        "pii-87b5396e@example.invalid": "Noah",
        "pii-bcf82242@example.invalid": "Noah",
        "pii-19bdd2f9@example.invalid": "Noah",
        "pii-c3968f4d@example.invalid": "Noah",
        "pii-ff6b875b@example.invalid": "Noah",
        "pii-d0eae302@example.invalid": "Noah",
        "pii-6636ddde@example.invalid": "Noah",
        "pii-8945dbcf@example.invalid": "Noah",
        "pii-efde12fb@example.invalid": "Noah",
        "pii-6138106e@example.invalid": "Noah",
        "pii-cd18e5a9@example.invalid": "Toby",
        "pii-d05c6a17@example.invalid": "Toby",
        "pii-805067e4@example.invalid": "Toby",
        "pii-3129a960@example.invalid": "Toby",
        "pii-0ad9a460@example.invalid": "Toby",
        "pii-fdfc0170@example.invalid": "Toby",
        "pii-b43490c8@example.invalid": "Toby",
        "pii-16cccfb1@example.invalid": "Toby",
        "pii-cf0fd069@example.invalid": "Toby",
        "pii-77ff6bba@example.invalid": "Toby",
        "pii-eee0822e@example.invalid": "Toby",
        "pii-ae99e7b2@example.invalid": "Toby",
        "pii-0ce49b7e@example.invalid": "Toby",
        "pii-17432361@example.invalid": "Toby",
        "pii-a0a7e16d@example.invalid": "Toby",
        "pii-c459c6e4@example.invalid": "Toby",
        "pii-fe0a1a3e@example.invalid": "Rune",
        "pii-73879ad9@example.invalid": "Rune",
        "pii-30264cbb@example.invalid": "Rune",
        "pii-cb2ec78e@example.invalid": "Rune",
        "pii-5785efe4@example.invalid": "Rune",
        "pii-702ded3d@example.invalid": "Rune",
        "pii-ff581b90@example.invalid": "Rune",
        "pii-484683f3@example.invalid": "Rune",
        "pii-66bd7ec6@example.invalid": "Rune",
        "pii-ebbdc0a1@example.invalid": "Rune",
        "pii-95552f54@example.invalid": "Rune",
        "pii-daf29f59@example.invalid": "Rune",
        "pii-74556566@example.invalid": "Rune",
        "pii-07d05b2c@example.invalid": "Rune",
        "pii-0a3fd746@example.invalid": "Rune",
        "pii-52183e40@example.invalid": "Rune",
        "pii-ad5dd203@example.invalid": "Rune",
        "pii-00a63383@example.invalid": "Rune",
        "pii-403d49a3@example.invalid": "Rune",
        "pii-6b151735@example.invalid": "Rune",
        "pii-79dd6096@example.invalid": "Rune",
        "pii-b07bee2a@example.invalid": "Rune",
        "pii-b591162c@example.invalid": "Rune",
        "pii-d3bb9f58@example.invalid": "Rune",
        "pii-2776726f@example.invalid": "Rune",
        "pii-3a19b41c@example.invalid": "Rune",
        "pii-1b4c32a3@example.invalid": "Rune",
        "pii-c0a60695@example.invalid": "Rune",
        "pii-1510dc76@example.invalid": "Rune",
        "pii-435deea6@example.invalid": "Rune",
        "pii-d0b8b94f@example.invalid": "Rune",
        "pii-dd2dd076@example.invalid": "Rune",
        "pii-adb40562@example.invalid": "Rune",
        "pii-bf889671@example.invalid": "Rune",
        "pii-e3ca7534@example.invalid": "Rune",
        "pii-42f7196c@example.invalid": "Rune",
        "pii-269a7bdd@example.invalid": "Rune",
        "pii-8102b6cc@example.invalid": "Rune",
        "pii-fd59b6aa@example.invalid": "Rune",
        "pii-6d6205cf@example.invalid": "Rune",
        "pii-c7f504ba@example.invalid": "Rune",
        "pii-72aef0b6@example.invalid": "Rune",
        "pii-152a1b4a@example.invalid": "Rune",
        "pii-5b25f6d0@example.invalid": "Rune",
        "pii-7892a2bb@example.invalid": "Mario",
        "pii-0c3930b3@example.invalid": "Mario",
        "pii-407828e5@example.invalid": "Mario",
        "pii-f6dc6399@example.invalid": "Sergey",
        "pii-0994d14f@example.invalid": "Sergey",
        "pii-f0de8c2b@example.invalid": "Sergey",
        "pii-c694a8d3@example.invalid": "Sergey",
        "pii-db53361a@example.invalid": "Sergey",
        "pii-f5778902@example.invalid": "Sergey",
        "pii-0a3c839e@example.invalid": "Sergey",
        "pii-d363e899@example.invalid": "Sergey",
        "pii-f8efa3ac@example.invalid": "Sergey",
        "pii-f503852d@example.invalid": "Sergey",
        "pii-0c26273b@example.invalid": "Sergey",
        "pii-37cf60ff@example.invalid": "Sergey",
        "pii-9cf7fcfd@example.invalid": "Sergey",
        "pii-df157e47@example.invalid": "Sergey",
        "pii-82ecbbf6@example.invalid": "Sergey",
        "pii-a028900a@example.invalid": "Sergey",
        "pii-318e73f5@example.invalid": "Sergey",
        "pii-fa77e042@example.invalid": "Sergey",
        "pii-25d7d874@example.invalid": "Sergey",
        "pii-a2bafc04@example.invalid": "Sergey",
        "pii-95d25d0d@example.invalid": "Sergey",
        "pii-9254bbf9@example.invalid": "Sergey",
        "pii-f24089d0@example.invalid": "Sergey",
        "pii-6d8f522e@example.invalid": "Sergey",
        "pii-26975603@example.invalid": "Sergey",
        "pii-26b65847@example.invalid": "Sergey",
        "pii-4da7abc9@example.invalid": "Sergey",
        "pii-62a774c6@example.invalid": "Sergey",
        "pii-d18d6dfe@example.invalid": "Sergey",
        "pii-e61446e6@example.invalid": "Sergey",
        "pii-68ce6962@example.invalid": "Sergey",
        "pii-5ef4c819@example.invalid": "Sergey",
        "pii-8c3705a7@example.invalid": "Sergey",
        "pii-7134eb0c@example.invalid": "Sergey",
        "pii-569bef46@example.invalid": "Sergey",
        "pii-5f0a350a@example.invalid": "Sergey",
        "pii-e88897ae@example.invalid": "Sergey",
        "pii-9a924db0@example.invalid": "Sergey",
        "pii-a3675bd2@example.invalid": "Sergey",
        "pii-bef720a3@example.invalid": "Sergey",
        "pii-2e4dac17@example.invalid": "Sergey",
        "pii-4583e22a@example.invalid": "Sergey",
        "pii-d3607a9c@example.invalid": "Sergey",
        "pii-804107dd@example.invalid": "Sergey",
        "pii-f5522088@example.invalid": "Sergey",
        "pii-ac9981e9@example.invalid": "Sergey",
        "pii-42ea770c@example.invalid": "Sergey",
        "pii-e175b27a@example.invalid": "Sergey",
        "pii-8accf5ed@example.invalid": "Sergey",
        "pii-1a04065b@example.invalid": "Sergey",
        "pii-7cf50758@example.invalid": "Sergey",
        "pii-17753f6f@example.invalid": "Sergey",
        "pii-efdaafc5@example.invalid": "Sergey",
        "pii-bc547b02@example.invalid": "Sergey",
        "pii-7376b4f3@example.invalid": "Sergey",
        "pii-ef72c98d@example.invalid": "Sergey",
        "pii-c688f35d@example.invalid": "Sergey",
        "pii-c77d6f83@example.invalid": "Sergey",
        "pii-cc9bbe84@example.invalid": "Sergey",
        "pii-4234ed00@example.invalid": "Sergey",
        "pii-22e82c70@example.invalid": "Sergey",
        "pii-69822b63@example.invalid": "Sergey",
        "pii-14e4adbf@example.invalid": "Sergey",
        "pii-e7a9f289@example.invalid": "Sergey",
        "pii-88438111@example.invalid": "Mario",
        "pii-71073ed5@example.invalid": "Mario",
        "pii-e15081a1@example.invalid": "Mario",
        "pii-e8b7bf95@example.invalid": "Mario",
        "pii-144bfc50@example.invalid": "Mario",
        "pii-1194d3e8@example.invalid": "Mario",
        "pii-641523d1@example.invalid": "Mario",
        "pii-4ba9d821@example.invalid": "Mario",
        "pii-0d9d6cd1@example.invalid": "Mario",
        "pii-8a708449@example.invalid": "Mario",
        "pii-916e5a41@example.invalid": "Mario",
        "pii-df0377da@example.invalid": "Mario",
        "pii-d1138d9c@example.invalid": "Mario",
        "pii-5a223794@example.invalid": "Toby",
        "pii-ad32d19b@example.invalid": "Toby",
        "pii-4e26564f@example.invalid": "Toby",
        "pii-0142ace0@example.invalid": "Toby",
        "pii-7a1ac38d@example.invalid": "Toby",
        "pii-078c3cd7@example.invalid": "Toby",
        "pii-fe52d6e0@example.invalid": "Toby",
        "pii-e4e9b137@example.invalid": "Toby",
        "pii-d43cda95@example.invalid": "Toby",
        "pii-c6426f78@example.invalid": "Toby",
        "pii-4d73e139@example.invalid": "Toby",
        "pii-b630d18c@example.invalid": "Toby",
        "pii-9c1a9dec@example.invalid": "Toby",
        "pii-f1ede5d8@example.invalid": "Toby",
        "pii-e1200ff3@example.invalid": "Toby",
        "pii-d4181568@example.invalid": "Toby",
        "pii-c1d5596e@example.invalid": "Toby",
        "pii-01c69450@example.invalid": "Toby",
        "pii-db03c3aa@example.invalid": "Toby",
        "pii-2b443042@example.invalid": "Toby",
        "pii-2389f26b@example.invalid": "Toby",
        "pii-bd365f9d@example.invalid": "Toby",
        "pii-bb801e60@example.invalid": "Toby",
        "pii-72831c07@example.invalid": "Toby",
        "pii-d5596b0e@example.invalid": "Toby",
        "pii-bb38e7b6@example.invalid": "Toby",
        "pii-14f16cd7@example.invalid": "Toby",
        "pii-c159f880@example.invalid": "Toby",
        "pii-541631c3@example.invalid": "Toby",
        "pii-4cd157f8@example.invalid": "Toby",
        "pii-6c44432b@example.invalid": "Toby",
        "pii-7def7c76@example.invalid": "Toby",
        "pii-7058cafe@example.invalid": "Toby",
        "pii-8e27e998@example.invalid": "Toby",
        "pii-d57a8fd7@example.invalid": "Toby",
        "pii-79d751c8@example.invalid": "Toby",
        "pii-9a6c896d@example.invalid": "Toby",
        "pii-13c68305@example.invalid": "Toby",
        "pii-661b267e@example.invalid": "Toby",
        "pii-cc2cd38b@example.invalid": "Toby",
        "pii-4c49125a@example.invalid": "Toby",
        "pii-5984be6c@example.invalid": "Toby",
        "pii-0637c702@example.invalid": "Toby",
        "pii-0c8a6463@example.invalid": "Toby",
        "pii-4ae21e2d@example.invalid": "Toby",
        "pii-68d2e7a2@example.invalid": "Toby",
        "pii-a0babd5e@example.invalid": "Toby",
        "pii-64725098@example.invalid": "Toby",
        "pii-8a7a6eaa@example.invalid": "Toby",
        "pii-78094590@example.invalid": "Toby",
        "pii-91a4af61@example.invalid": "Toby",
        "pii-5fc420e3@example.invalid": "Toby",
        "pii-0ce1240a@example.invalid": "Toby",
        "pii-b52fdd9e@example.invalid": "Toby",
        "pii-6231c8c7@example.invalid": "Toby",
        "pii-a4938733@example.invalid": "Toby",
        "pii-f7be9de6@example.invalid": "Toby",
        "pii-6a04d620@example.invalid": "Toby",
        "pii-df342e19@example.invalid": "Toby",
        "pii-f3c232f2@example.invalid": "Toby",
        "pii-6a390883@example.invalid": "Toby",
        "pii-4d2f5c93@example.invalid": "Toby",
    },
    "forward_map_source": "config",
    "forward_default": "melisa@janeasystems.com",
    "forward_on_uncategorized": True,
    # Three-way forward routing (Nik). An unclassified reply must never be delivered as if it were
    # qualified, so it goes to a human reviewer instead of the campaign sender.
    "forward_review_address": "melisa@janeasystems.com",
    "sheets": {"spreadsheet_id": "1vrEutNXwQ1_avO7Xq2tAJKqHSqfpK4Ai8ORCDs2yGcE",
               "tab": "Janea All Inboxes (1.15.2025)", "cache_ttl_sec": 3600, "enabled": False},
    # Anthropic credential deferred (organizational). OFF = degraded-but-safe: no SL category
    # write, fail-open forwarding, no text-derived DNC. UNSUBSCRIBED-event DNC is unaffected.
    # Flipping to true is a release gate, NOT a config tweak - see the flip checklist.
    # LIVE in shadow: the classifier runs and its intent is recorded, but every write is still
    # gated, so nothing reaches Pipedrive/Smartlead until WRITE_MODE flips.
    "classify_enabled": True,
    # LLM provider: OpenAI (Nik's key; n8n credential "OpenAI API", httpHeaderAuth Bearer).
    # `max_completion_tokens`, not max_tokens: the current flagships renamed it. Temperature is
    # deliberately ABSENT - newer flagship models reject anything but the default, and determinism
    # comes from response_format=json_object plus the closed category dictionary in the prompt.
    # model_fallback is the cost floor; switching is this one line.
    "llm": {"provider": "openai",
            "base": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-5.2",
            "model_fallback": "gpt-4o-mini",
            "max_completion_tokens": 400,
            # 0.70 (Nik): the live probe returned 0.66 on genuine garbage, which at 0.6 would have
            # been accepted as a real category and then silently NOT forwarded, because
            # "Uncategorizable by Ai" is not forwardable. 0.70 sends that case to human review.
            "min_confidence": 0.70},
    "flags": {"create_assignment_task": False, "forward_enabled": True, "dnc_auto": True,
              "classify_with_history": False, "alert_every_reply": False},
    "dedupe_max_age_sec": 172800,
    # Webhook authenticity (Nik). The endpoint is public and performs CRM writes. Smartlead posts a
    # shared `secret_key`; we compare a SHA-256 DIGEST so no secret ever lives in this JSON (AU4).
    # null => UNCONFIGURED: traffic is accepted (dropping everything would blind the shadow phase)
    # but ops is warned, rate-limited. Setting the hash ARMS enforcement. Generate it yourself:
    #   node -e "console.log(require('crypto').createHash('sha256').update('<SECRET>').digest('hex'))"
    # D (click-verified by Nik: both leadMap links opened the exact named conversations).
    # The webhook ships the finished link as app_url / ui_master_inbox_link; this base is only the
    # fallback when we must construct one from sl_email_lead_map_id. No map id -> no link (LK rule).
    "sl_inbox_base": "https://app.smartlead.ai/app/master-inbox?leadMap=",
    # F1: canonical raw event_type per branch, lower-cased. ONLY `email_reply` is observed
    # (Smartlead test, 2026-07-29); the other three are still assumptions and are exactly what the
    # event-alias warn is meant to correct from live traffic. Update as each is confirmed.
    "canonical_events": {"SENT": "email_sent", "REPLIED": "email_reply",
                         "BOUNCED": "email_bounced", "UNSUB": "lead_unsubscribed"},
    "canonical_events_observed": ["email_reply"],
    "webhook_secret_sha256": None,
    "webhook_secret_warn_interval_sec": 3600,
}

# ---------------------------------------------------------------- code bodies
ALIAS_WATCH = r"""
// F1: warn ONCE per previously unseen raw event string, then remember it. An unknown-but-matching
// string means our canonical table is wrong, which is how EMAIL_REPLY slipped through as an
// assumption. Learning it in static data keeps the channel quiet after the first sighting.
const n = $('Normalize').item.json;
const alias = n.event_alias;
if (!alias) return [{ json: { __alias_warn: false } }];
const sd = $getWorkflowStaticData('global');
const seen = sd.__event_aliases_seen = sd.__event_aliases_seen || {};
const key = n.event + '|' + alias;
const first = !seen[key];
if (first) { seen[key] = new Date().toISOString(); }
return [{ json: { __alias_warn: first, __alias_event: n.event, __alias_raw: alias,
                  __alias_known: Object.keys(seen).length } }];
"""

ALIAS_WARN_TEXT_EXPR = (
    "={{ (() => { const j=$json;"
    " const esc=(v)=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');"
    " return '\\u2139\\ufe0f WF-2: new Smartlead event string \\\"' + esc(j.__alias_raw)"
    " + '\\\" routed to ' + esc(j.__alias_event) + ' \\u2014 update CONFIG.canonical_events'"
    " + ' (learned: ' + j.__alias_known + ')'; })() }}"
)

VERIFY_SECRET = r"""
const CFG = $('CONFIG').item.json;
const wh = $('Webhook').item.json ?? {};
const b = wh.body ?? {};
const hdrs = wh.headers ?? {};
const want = CFG.webhook_secret_sha256 || null;
const got = (b.secret_key === undefined || b.secret_key === null) ? null : String(b.secret_key);

let ok, mode;
if (!want) { ok = true; mode = 'unconfigured'; }           // ships inert; arm by setting the hash
else if (got === null) { ok = false; mode = 'missing'; }   // Nik: a missing secret counts as invalid
else {
  const crypto = require('crypto');
  const a = crypto.createHash('sha256').update(got).digest('hex');
  const c = String(want);
  // Constant-time over the DIGESTS. Hand-rolled rather than crypto.timingSafeEqual because that
  // needs Buffer, and only `crypto` itself was probed as available in this instance's Code nodes.
  // The length check leaks only the length of a hex digest (always 64), never anything secret.
  let diff = a.length ^ c.length;
  for (let i = 0; i < a.length && i < c.length; i++) diff |= a.charCodeAt(i) ^ c.charCodeAt(i);
  ok = diff === 0;
  mode = ok ? 'valid' : 'mismatch';
}

// An open endpoint must not become a Slack flood vector: rate-limit the warn and report how many
// posts were suppressed. The request was ALREADY answered 200 by Respond to Webhook, so a rejected
// event is dropped silently - never a 500 (Smartlead disables an endpoint after 5 failures).
const sd = $getWorkflowStaticData('global');
const now = Date.now();
const every = Number(CFG.webhook_secret_warn_interval_sec ?? 3600) * 1000;
let warn = false, suppressed = 0;
if (mode !== 'valid') {
  const last = Number(sd.__auth_warn_at ?? 0);
  sd.__auth_suppressed = Number(sd.__auth_suppressed ?? 0) + 1;
  if (now - last >= every) {
    warn = true;
    suppressed = Number(sd.__auth_suppressed) - 1;
    sd.__auth_warn_at = now;
    sd.__auth_suppressed = 0;
  }
}
const hint = [hdrs['cf-connecting-ip'] || hdrs['x-real-ip'] || '?',
              String(hdrs['user-agent'] || '?').slice(0, 60)].join(' / ');
return [{ json: { __auth_ok: ok, __auth_mode: mode, __auth_warn: warn,
                  __auth_suppressed: suppressed, __auth_hint: hint,
                  __auth_event: String(b.event_type ?? '?'),
                  __auth_campaign: String(b.campaign_name ?? b.campaign_id ?? '?') } }];
"""

AUTH_WARN_TEXT = (
    "={{ (() => { const j=$json; const esc=(v)=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); const m=j.__auth_mode; const head = m==='unconfigured' ? '\\ud83d\\udd13 WF-2: webhook secret validation is NOT ARMED (CONFIG.webhook_secret_sha256 is null) \\u2014 traffic accepted' : '\\u26d4 WF-2: DROPPED an unauthenticated webhook post (' + m + ')'; const extra = j.__auth_suppressed > 0 ? (' \\u00b7 +' + j.__auth_suppressed + ' more suppressed') : ''; return head + ' \\u00b7 event ' + esc(j.__auth_event) + ' \\u00b7 ' + esc(j.__auth_campaign) + ' \\u00b7 from ' + esc(j.__auth_hint) + extra; })() }}"
)

NORMALIZE = r"""// WF-2 Normalize - the single translation layer (architecture SS2)
// Defensive by design: EVERY payload field is optional (A3 is UNVERIFIED).
// B11: Normalize's $json is the CONFIG node's output, NOT the webhook body - the spine is
// Webhook -> Respond -> CONFIG -> Normalize. Reading $json.body silently produced an EMPTY
// payload on every single event. Always name the source node.
const b = $('Webhook').item.json.body ?? $('Webhook').item.json ?? {};
const cfg = $('CONFIG').item.json;

const CANON_WS = (s) => String(s ?? '')
  .replace(/[     ]/g, ' ')   // nbsp + friends -> plain space
  .replace(/\s+/g, ' ')
  .trim();
const low = (s) => CANON_WS(s).toLowerCase();
const mail = (s) => String(s ?? '').trim().toLowerCase();
const pick = (...vals) => { for (const v of vals) if (v !== undefined && v !== null && String(v).trim() !== '') return v; return null; };

// ---- event discriminator (defensive: Smartlead naming varies by webhook version)
const rawEvent = low(pick(b.event_type, b.event, b.webhook_event, b.type));
let event = 'UNKNOWN';
if (/first.*sent|email.?sent|email_sent/.test(rawEvent)) event = 'SENT';
else if (/repl/.test(rawEvent)) event = 'REPLIED';
else if (/bounce/.test(rawEvent)) event = 'BOUNCED';
else if (/unsub/.test(rawEvent)) event = 'UNSUB';
else if (/categor/.test(rawEvent)) event = 'CATEGORY_UPDATED';   // Make's trigger; we ignore it

const ld = b.lead_data ?? b.lead ?? {};
const campaign_name_raw = pick(b.campaign_name, b.campaign?.name, ld.campaign_name);
const campaign_name = CANON_WS(campaign_name_raw);

// ---- marker parser (same contract as W1.0.13.1: two-bracket convention)
const groups = [];
{ const re = /\[([^\]]*)\]/g; let m; while ((m = re.exec(campaign_name)) !== null) groups.push(m[1]); }
const canon = cfg.marker_canon || {};
let hypothesis = null, event_name = null, marker_unknown = null, is_nurture = false;
if (groups.length) {
  const key = low(groups[0]);
  if (Object.prototype.hasOwnProperty.call(canon, key)) {
    const v = canon[key];
    if (v === '__NURTURE__') is_nurture = true; else hypothesis = v;
  } else {
    marker_unknown = CANON_WS(groups[0]);
  }
  if (groups.length >= 2) {
    const ev = CANON_WS(groups[1]);
    if (ev !== '' && ev.length <= 60 && !/\[|\]/.test(ev)) event_name = ev;
  }
}
// nurture may also be signalled without brackets (Make parity: name contains "lead nurturing")
if (!is_nurture && /lead nurtur/.test(low(campaign_name))) is_nurture = true;

const n = {
  event, raw_event: rawEvent,
  campaign_id: pick(b.campaign_id, b.campaign?.id, ld.campaign_id),
  campaign_name, campaign_name_raw: campaign_name_raw ?? null,
  // B15: field names come from REAL webhook samples recovered from the Make blueprints
  // (wf2-webhook-payloads.md). EMAIL_SENT carries sl_email_lead_id, NOT lead_id - without this
  // sl_lead_id was null on every SENT event, and since the dedupe key is campaign_id + sl_lead_id
  // every first-email in a campaign collapsed onto ONE key and all but the first were dropped.
  sl_lead_id: pick(b.lead_id, b.sl_email_lead_id, ld.id, b.sl_lead_id),
  // the map id is what the Smartlead UI deep link keys on (?leadMap=), and the payload also ships
  // the finished link itself - prefer the given link over anything we construct
  sl_lead_map_id: pick(b.sl_email_lead_map_id, b.lead_map_id, b.campaign_lead_map_id),
  sl_app_url: pick(b.app_url, b.ui_master_inbox_link),
  // F5: Smartlead ships its OWN category on reply events (observed: reply_category "Interested").
  // While classify_enabled is false this is the category source, so the shadow diff measures real
  // gating instead of fail-open. At flip it becomes the comparison baseline for our classifier.
  // Smartlead sends this as a NAME in its test payload ("Interested") but as a NUMERIC ID on real
  // organic replies (observed: 2). Resolve ids back to names via category_map, so the F5 native
  // fallback and the accuracy comparison both see one consistent vocabulary.
  reply_category: (() => {
    const raw = pick(b.reply_category, b.lead_category?.new_name, b.lead_data?.category?.name,
                     b.lead_category?.new_id, b.lead_data?.category?.id);
    if (raw === null) return null;
    const asNum = Number(raw);
    if (Number.isFinite(asNum) && String(raw).trim() !== '') {
      for (const [nm, id] of Object.entries(cfg.category_map || {})) if (id === asNum) return nm;
      return null;                      // an id we do not know is worse than no category
    }
    return String(raw);
  })(),
  reply_source: pick(b.reply_source),
  // F1: the reply event turned out to be EMAIL_REPLY, not EMAIL_REPLIED - an assumption I had
  // recorded as verified. The regexes are deliberately loose, so a wrong constant routes correctly
  // and hides the mismatch. Flag it instead, so live traffic teaches us the other three names.
  event_alias: (() => {
    const canon = (cfg.canonical_events || {})[event] || null;
    return (event !== 'UNKNOWN' && canon && rawEvent && rawEvent !== canon) ? rawEvent : null;
  })(),
  sequence_number: (() => { const v = pick(b.sequence_number, b.current_seq_num, b.seq_number); const num = Number(v); return Number.isFinite(num) ? num : null; })(),
  timestamp: pick(b.timestamp, b.time_sent, b.event_timestamp, b.created_at),
  sender_inbox: mail(pick(b.from_email, b.email_account, b.sender_email)),
  lead: {
    email: mail(pick(b.to_email, ld.email, b.email)),
    first: pick(ld.first_name, b.first_name),
    last: pick(ld.last_name, b.last_name),
    full_name: pick(b.to_name, ld.full_name, [pick(ld.first_name, b.first_name), pick(ld.last_name, b.last_name)].filter(Boolean).join(' ') || null),
    company: CANON_WS(pick(ld.company_name, b.company_name)) || null,
    website: pick(ld.website, b.website),
    linkedin: pick(ld.linkedin_profile, b.linkedin_profile, ld.linkedin),
    location: pick(ld.location, b.location, ld.city, b.city),
    title: pick(ld.job_title, b.job_title, ld.title, b.title),
    custom_fields: ld.custom_fields ?? b.custom_fields ?? {},
  },
  reply: {
    subject: pick(b.subject, b.reply_subject, b.email_subject, b.last_reply?.subject),
    body: pick(b.reply_body, b.body, b.email_body, b.reply_message, b.message,
               b.last_reply?.email_body),
    received_at: pick(b.reply_time, b.time_replied, b.received_at, b.timestamp),
    message_id: pick(b.message_id, b.reply_message_id, b.last_reply?.message_id),
    stats_id: pick(b.stats_id, b.last_reply?.stats_id),
  },
  hypothesis, event_name, marker_unknown, is_nurture,
  // Provenance. Normalize whitelists its output, which silently dropped these two - so a
  // WF-2S-reconciled SENT event was indistinguishable from a genuine Smartlead delivery in
  // Shadow Log and the diff harness. That distinction is the entire reason the reconciler
  // stamps them: SENT arrives ONLY by replay today, and when Smartlead eventually fixes
  // delivery we need to see which source a given event came from.
  __reconciled: b.__reconciled === true,
  __reconciled_by: b.__reconciled === true ? pick(b.__reconciled_by) : null,
};
return [{ json: n }];
"""

DEDUPE = r"""// WF-2 Dedupe (architecture SS8) - import-free, staticData with age rotation
const n = $('Normalize').item.json;
const cfg = $('CONFIG').item.json;
const store = $getWorkflowStaticData('global');
store.wf2_seen = store.wf2_seen || {};
const nowSec = Math.floor(Number(new Date()) / 1000);
const maxAge = Number(cfg.dedupe_max_age_sec) || 172800;

// rotation first (bounded memory)
for (const k of Object.keys(store.wf2_seen)) {
  if (nowSec - Number(store.wf2_seen[k]) > maxAge) delete store.wf2_seen[k];
}
const key = [n.event, n.campaign_id, n.sl_lead_id, n.timestamp].map(v => String(v ?? '')).join('|');
const duplicate = Object.prototype.hasOwnProperty.call(store.wf2_seen, key);
if (!duplicate) store.wf2_seen[key] = nowSec;

// first-SENT-per-(campaign,lead) memo - defense for the seq gate
const sentKey = 'S|' + String(n.campaign_id ?? '') + '|' + String(n.sl_lead_id ?? '');
const firstSentSeen = Object.prototype.hasOwnProperty.call(store.wf2_seen, sentKey);
if (n.event === 'SENT' && !firstSentSeen) store.wf2_seen[sentKey] = nowSec;

return [{ json: { ...n, __dedupe_key: key, __duplicate: duplicate, __first_sent: !firstSentSeen } }];
"""

SHADOW_LOG = r"""// WF-2 Shadow Log (architecture SS6/SS9) - in shadow mode we record the INTENDED write
const cfg = $('CONFIG').item.json;
const n = $('Normalize').item.json;
const intended = $json.__intended ?? {};
return [{ json: {
  __shadow: true,
  write_mode: cfg.WRITE_MODE,
  event: n.event,
  campaign_id: n.campaign_id,
  campaign_name: n.campaign_name,
  lead_email: n.lead?.email ?? null,
  sl_lead_id: n.sl_lead_id ?? null,
  node: intended.node ?? null,
  method: intended.method ?? null,
  url_template: intended.url ?? null,
  body: intended.body ?? null,
  // a recorded intent is NOT necessarily a write: the same Skip path also carries entries whose
  // gate said __skip. Without this the diff harness counts skips as intended writes.
  would_write: $json.__skip !== true,
  skipped_write: $json.__skipped_write ?? null,
  recorded_at: new Date().toISOString(),
} }];
"""

UNION_LABELS = r"""// WF-2 union-label module (WF-1 W1.0.7 idiom) - NEVER absolute, never removes
const cfg = $('CONFIG').item.json;
const L = cfg.labels;
const lead = $json.data ?? $json ?? {};
const existing = Array.isArray(lead.label_ids) ? lead.label_ids.slice() : [];
const target = ($json.__target_labels ?? []);
const union = existing.slice();
for (const id of target) if (id && !union.includes(id)) union.push(id);
const changed = union.length !== existing.length;
return [{ json: { lead_id: lead.id ?? null, existing, target, label_ids: union, changed } }];
"""


def node(nid, name, ntype, tv, pos, params, **extra):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype, "typeVersion": tv, "position": pos}
    n.update(extra)
    return n


def code(nid, name, pos, js, **extra):
    return node(nid, name, "n8n-nodes-base.code", 2, pos, {"jsCode": js}, **extra)


def build():
    N = []
    C = {}
    X, Y = 0, 0

    # ---- spine
    # B10: responseMode MUST be 'responseNode' whenever a Respond node exists, or n8n aborts the
    # whole run with "Unused Respond to Webhook node found" and answers 500. Smartlead counts 5
    # failures and disables the endpoint, so this was an outage waiting for the first odd event.
    # Same parameters as production WF-1: respond FIRST, then do the CRM work.
    N.append(node("wf2-0001-webhook", "Webhook", "n8n-nodes-base.webhook", 2, [X, Y],
                  {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode",
                   "options": {"rawBody": False}},
                  webhookId=WEBHOOK_PATH))
    N.append(node("wf2-0002-respond", "Respond to Webhook", "n8n-nodes-base.respondToWebhook", 1,
                  [X + 200, Y], {"options": {}}))
    N.append(node("wf2-0003-config", "CONFIG", "n8n-nodes-base.set", 3.4, [X + 400, Y],
                  {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2, ensure_ascii=False),
                   "options": {}}))
    N.append(code("wf2-0003b-verify", "Verify Secret", [X + 500, Y], VERIFY_SECRET))
    N.append(node("wf2-0003c-ifauth", "IF Authentic", "n8n-nodes-base.if", 2, [X + 560, Y],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "wf2-cauth",
                                                  "leftValue": "={{ $json.__auth_ok === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(node("wf2-0003d-ifwarn", "IF Auth Warn", "n8n-nodes-base.if", 2, [X + 560, Y + 200],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "wf2-cauthw",
                                                  "leftValue": "={{ $json.__auth_warn === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(code("wf2-0003e-drop", "NoOp Drop Unauthenticated", [X + 620, Y + 320],
                  "// dropped silently - the 200 was already sent by Respond to Webhook\n"
                  "return [{ json: { dropped: 'unauthenticated' } }];"))
    N.append(code("wf2-0003f-quiet", "NoOp Auth Quiet", [X + 620, Y + 440],
                  "return [{ json: { auth: 'ok' } }];"))
    N.append(slack("wf2-0003g-warn", "Ops Warn Bad Secret", [X + 760, Y + 200],
                   "slack_channel_ops", AUTH_WARN_TEXT, SLACK_CRED))
    N.append(code("wf2-0004-normalize", "Normalize", [X + 600, Y], NORMALIZE))
    N.append(code("wf2-0004b-alias", "Event Alias Watch", [X + 700, Y + 260], ALIAS_WATCH))
    N.append(node("wf2-0004c-ifalias", "IF Alias New", "n8n-nodes-base.if", 2, [X + 760, Y + 260],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "wf2-calias",
                                                  "leftValue": "={{ $json.__alias_warn === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(slack("wf2-0004d-aliaswarn", "Ops Warn Event Alias", [X + 900, Y + 260],
                   "slack_channel_ops", ALIAS_WARN_TEXT_EXPR, SLACK_CRED))
    N.append(code("wf2-0004e-aliasok", "NoOp Alias Known", [X + 900, Y + 380],
                  "return [{ json: { alias: 'known' } }];"))
    N.append(code("wf2-0005-dedupe", "Dedupe", [X + 800, Y], DEDUPE))
    N.append(node("wf2-0006-ifdup", "IF Duplicate", "n8n-nodes-base.if", 2, [X + 1000, Y],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "wf2-c-dup",
                                                  "leftValue": "={{ $json.__duplicate === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean", "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(node("wf2-0007-noop-dup", "NoOp Duplicate", "n8n-nodes-base.noOp", 1, [X + 1200, Y - 160], {}))
    N.append(node("wf2-0008-switch", "Switch Event", "n8n-nodes-base.switch", 3, [X + 1200, Y + 120],
                  {"rules": {"values": [
                      {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                                  "typeValidation": "strict", "version": 1},
                                      "conditions": [{"id": "wf2-sw-sent",
                                                      "leftValue": "={{ $json.event }}",
                                                      "rightValue": "SENT",
                                                      "operator": {"type": "string", "operation": "equals"}}],
                                      "combinator": "and"}, "renameOutput": True, "outputKey": "SENT"},
                      {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                                  "typeValidation": "strict", "version": 1},
                                      "conditions": [{"id": "wf2-sw-repl",
                                                      "leftValue": "={{ $json.event }}",
                                                      "rightValue": "REPLIED",
                                                      "operator": {"type": "string", "operation": "equals"}}],
                                      "combinator": "and"}, "renameOutput": True, "outputKey": "REPLIED"},
                      {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                                  "typeValidation": "strict", "version": 1},
                                      "conditions": [{"id": "wf2-sw-bnc",
                                                      "leftValue": "={{ $json.event }}",
                                                      "rightValue": "BOUNCED",
                                                      "operator": {"type": "string", "operation": "equals"}}],
                                      "combinator": "and"}, "renameOutput": True, "outputKey": "BOUNCED"},
                      {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                                  "typeValidation": "strict", "version": 1},
                                      "conditions": [{"id": "wf2-sw-uns",
                                                      "leftValue": "={{ $json.event }}",
                                                      "rightValue": "UNSUB",
                                                      "operator": {"type": "string", "operation": "equals"}}],
                                      "combinator": "and"}, "renameOutput": True, "outputKey": "UNSUB"}]},
                   "options": {"fallbackOutput": "extra", "renameFallbackOutput": "default"}}))

    C["Webhook"] = {"main": [[{"node": "Respond to Webhook", "type": "main", "index": 0}]]}
    C["Respond to Webhook"] = {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]}
    # authenticity sits between CONFIG and Normalize: nothing downstream runs unverified
    C["CONFIG"] = {"main": [[{"node": "Verify Secret", "type": "main", "index": 0}]]}
    C["Verify Secret"] = {"main": [[{"node": "IF Authentic", "type": "main", "index": 0},
                                    {"node": "IF Auth Warn", "type": "main", "index": 0}]]}
    C["IF Authentic"] = {"main": [[{"node": "Normalize", "type": "main", "index": 0}],
                                  [{"node": "NoOp Drop Unauthenticated", "type": "main", "index": 0}]]}
    C["Normalize"] = {"main": [[{"node": "Dedupe", "type": "main", "index": 0},
                                {"node": "Event Alias Watch", "type": "main", "index": 0}]]}
    C["Event Alias Watch"] = {"main": [[{"node": "IF Alias New", "type": "main", "index": 0}]]}
    C["IF Alias New"] = {"main": [[{"node": "Ops Warn Event Alias", "type": "main", "index": 0}],
                                  [{"node": "NoOp Alias Known", "type": "main", "index": 0}]]}
    C["IF Auth Warn"] = {"main": [[{"node": "Ops Warn Bad Secret", "type": "main", "index": 0}],
                                  [{"node": "NoOp Auth Quiet", "type": "main", "index": 0}]]}
    # NOTE: Normalize is wired above with the Event Alias Watch tee (F1). Do not re-assign it here -
    # a second assignment silently dropped the tee and orphaned the watcher (caught by static I7).
    C["Dedupe"] = {"main": [[{"node": "IF Duplicate", "type": "main", "index": 0}]]}
    C["IF Duplicate"] = {"main": [[{"node": "NoOp Duplicate", "type": "main", "index": 0}],
                                  [{"node": "Switch Event", "type": "main", "index": 0}]]}

    # shared helper nodes
    N.append(code("wf2-0009-shadow", "Shadow Log", [X + 600, Y + 900], SHADOW_LOG))
    # NOTE: the union-label logic lives inline in BODY_LABELS (Body Lead Labels Union /
    # Body U Lead DNC Label), so no separate shared node is emitted - keeping one would be dead weight.

    # ---- branches from the library
    from build_wf2_graph import assemble
    bn, bc = assemble(SLACK_CRED)
    N.extend(bn)
    for k, v in bc.items():
        C[k] = v
    C["Switch Event"] = {"main": [
        [{"node": "IF Nurture SENT", "type": "main", "index": 0},
         {"node": "IF Unknown Marker", "type": "main", "index": 0}],
        [{"node": "IF Nurture REPLIED", "type": "main", "index": 0},
         {"node": "IF Unknown Marker", "type": "main", "index": 0}],
        [{"node": "B Person Search", "type": "main", "index": 0}],
        [{"node": "U Person Search", "type": "main", "index": 0}],
        [{"node": "Ops Warn Unknown Event", "type": "main", "index": 0}]]}

    add_shadow_passthrough(N, C)
    wf = {
        "name": "WF-2 Smartlead Receiver",
        "nodes": N,
        "connections": C,
        "active": False,
        "settings": {"executionOrder": "v1", "errorWorkflow": ERROR_WORKFLOW},
    }
    return wf


def add_shadow_passthrough(nodes, conns):
    """B20: a gate's false branch dead-ended at Shadow Log, so shadow mode stopped at the FIRST
    intended write on every path - only one intent per execution was ever recorded (proven on the
    real Smartlead test, exec 11602: the label/activity/category/forward intents were never even
    computed). Insert a pass-through `Skip <label>` that records AND continues to exactly where the
    live write goes, so shadow traverses the whole graph. Live behaviour is untouched."""
    byname = {n["name"]: n for n in nodes}
    added = 0
    for gate in [n for n in list(nodes) if n["name"].startswith("Gate ")]:
        label = gate["name"][len("Gate "):]
        main = conns.get(gate["name"], {}).get("main") or []
        if len(main) < 2:
            continue
        false_targets = [e["node"] for e in (main[1] or [])]
        if false_targets != ["Shadow Log"]:
            continue                                  # already rewired
        skip = f"Skip {label}"
        pos = byname[gate["name"]]["position"]
        nodes.append(code(f"{gate['id']}-skip", skip, [pos[0] + 180, pos[1] + 140],
                          "// B20: shadow bypass - record the intent, then continue exactly where\n"
                          "// the live write would have gone, so the whole graph is exercised.\n"
                          "return [{ json: { ...$json, __skipped_write: '" + label + "' } }];"))
        conns[gate["name"]]["main"][1] = [{"node": skip, "type": "main", "index": 0}]
        downstream = [dict(e) for o in (conns.get(label, {}).get("main") or []) for e in (o or [])]
        conns[skip] = {"main": [[{"node": "Shadow Log", "type": "main", "index": 0}] + downstream]}
        added += 1
    return added


def validate(wf, allow_live=False):
    e = []
    # class sweep (S1): no backward .item inside any fan-out region
    e.extend(item_violations(wf))
    names = [n["name"] for n in wf["nodes"]]
    if len(names) != len(set(names)):
        e.append("duplicate node names")
    ids = [n["id"] for n in wf["nodes"]]
    if len(ids) != len(set(ids)):
        e.append("duplicate node ids")
    cfg = json.loads(next(n for n in wf["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
    # The guard stays: you cannot build a live workflow by accident. --allow-live is an explicit,
    # logged opt-in for a supervised WRITE_MODE=live window, and it is the ONLY way past this.
    if cfg["WRITE_MODE"] != "shadow" and not allow_live:
        e.append("WRITE_MODE must ship as shadow (pass --allow-live for a supervised window)")
    if cfg["WRITE_MODE"] not in ("shadow", "live"):
        e.append(f"unknown WRITE_MODE {cfg['WRITE_MODE']!r}")
    if cfg["slack_channel_replies"] != "C0B8GCVNR5W":
        e.append("shadow phase: replies must go to Nik's channel until the flip")
    if cfg.get("slack_channel_replies_at_flip") != "C07LTD8UT70":
        e.append("the flip-time replies channel must stay recorded")
    if cfg["slack_channel_ops"] != "C0B8GCVNR5W":
        e.append("ops channel wrong")
    for v in cfg["forward_owner_map"].values():
        if v != v.strip():
            e.append(f"forward map has untrimmed address: {v!r}")
    if wf["settings"].get("errorWorkflow") != ERROR_WORKFLOW:
        e.append("errorWorkflow not bound")
    if wf.get("active") is not False:
        e.append("must be inactive")
    blob = json.dumps(wf)
    for bad in ("9f59ef3d", "api_key="):
        if bad in blob:
            e.append(f"secret-ish literal in workflow: {bad}")
    # B7: an HTTP node with no credential 401s. This is not a warning - it is a deploy gate,
    # and it bites in SHADOW too (SL Fetch Lead / SL Message History / LLM Classify are ungated reads).
    for n in wf["nodes"]:
        if n["type"] != "n8n-nodes-base.httpRequest":
            continue
        if not n["parameters"].get("authentication"):
            e.append(f"{n['name']}: no authentication configured")
        elif not n.get("credentials"):
            DEPLOY_GATES.append(n["name"])
    return e


DEPLOY_GATES = []   # HTTP nodes whose auth is declared but whose credential Nik must still create


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("--api-payload", type=Path, default=None)
    ap.add_argument("--allow-live", action="store_true",
                    help="explicit opt-in to build WRITE_MODE=live (supervised window only)")
    a = ap.parse_args()
    wf = build()
    errs = validate(wf, allow_live=a.allow_live)
    if errs:
        for x in errs:
            print(f"ERROR: {x}", file=sys.stderr)
        return 1
    a.output.write_bytes((json.dumps(wf, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if a.api_payload:
        payload = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
        a.api_payload.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"WF-2 built -> {a.output} (nodes: {len(wf['nodes'])})")
    if DEPLOY_GATES:
        print(f"DEPLOY GATE - {len(DEPLOY_GATES)} HTTP nodes declare auth but have NO credential bound;")
        print("  they will 401 until the credential exists in n8n (Nik, UI):")
        print(f"  {', '.join(DEPLOY_GATES)}")
        print("  Smartlead API (httpQueryAuth, api_key) is BOUND. Outstanding: httpHeaderAuth"
              " 'Anthropic API' (header x-api-key) - deferred, and harmless while"
              " classify_enabled is false since the node is then unreachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
