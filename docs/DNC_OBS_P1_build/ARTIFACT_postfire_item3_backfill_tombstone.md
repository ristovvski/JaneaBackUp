# Post-fire — item 3 of Nik's 2026-09-15 GO: backfill + tombstone

## Backfill (via `dnc_archived_responders_import`, dry-run then real, both clean)

4/4 written (`processed:4, conflicts_declined:0`). Independently read back from the registry
directly (not trusting the HTTP response) — all 4 present, `status=active, reason=reply_dnc`.

**Two things found and corrected during post-verify, not part of the original plan:**

1. `added_at` came back as the backfill's OWN timestamp (2026-09-15T13:54Z), not the caller-supplied
   original reply date (2026-09-01/02) — `DNC__UpsertLedger__v1`'s `Decide` step evidently always
   stamps `$now` rather than honoring a caller-supplied historical `added_at`. Registry protection
   is in place either way; the audit trail just shows the backfill date, not the true original
   reply date. Not fixed today (out of scope for this GO item) — flagging for awareness.
2. None of the 4 came back with a `pipedrive_person_id` (UpsertLedger doesn't resolve one from a
   bare LinkedIn URL in this call shape) — meaning none would ever reach the projections sweep's
   686-field write. Looked up all 4 directly in Pipedrive and verified by LinkedIn URL match before
   attaching:
   - **Person-054b9bef** (pid 85962) — LinkedIn matches exactly, owner Noah Keimach. Attached.
   - **Person-58accf5a** (pid 85942) — LinkedIn matches exactly, owner Noah Keimach. Attached.
   - **Person-19f1d00c** (pid 85787) — LinkedIn matches, owner Noah Keimach. Attached. Also
     corrected a data-quality issue: the backfill used the raw LinkedIn URN HeyReach returned
     (`ACoAAAPMYF4B8rRIDJe3h0RtJytJPvdHoCcIMAk`) as `identity_key`/`linkedin_url_norm` instead of
     the vanity slug (`travis-mcgregor-33a41219`) every other row in this project uses — checked no
     collision existed, then updated both fields to the correct slug (matching what Pipedrive's own
     record has on file). Left as a URN, his row would never match the normal identity-matching
     waterfall (linkedin_url_norm/email_lc Equals) used by every reader in this project, silently
     weakening his DNC protection.
   - **Burak Aksar** — the only Pipedrive match found (id 4618) has an empty LinkedIn field and
     `add_time` of 2024-11-20 (predates this campaign by over a year, owned by Toby not Noah) — not
     a confident match. Left `pipedrive_person_id` unset rather than risk attaching the wrong
     person. His registry row still provides identity/email-based DNC protection at the gate and
     registry layers; he just won't get a Pipedrive 686-field write until a real match is found.

## Tombstone (direct `id`-matched update, same shape as `dnc_s4_retirement_removal`'s internal
`Update Row`, custom `removed_reason` per row)

Both confirmed via direct read-back:
- Person-d9409383 (id 33141): `status=removed, removed_reason=false_reply_ooo`.
- Person-b27663e9 (id 33142): `status=removed, removed_reason=false_reply_mailbox_inactive`.

Checked their live Pipedrive 686 field BEFORE tombstoning: both still unset (they fell in item 1's
135-row remainder chunk, not yet processed) — tombstoning now, combined with item 1's new
`status==='active'` guard, means neither will ever get a wrongful Pipedrive DNC-field write. No
reverse/undo needed.
