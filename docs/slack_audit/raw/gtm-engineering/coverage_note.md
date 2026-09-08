# Coverage note — #gtm-engineering (C0B7MK9QQ9L) raw scrape

**Scrape date:** 2026-08-18 (Phase 1, raw scrape only — no analysis performed)

## Pagination

- Total `slack_read_channel` pages fetched: **3** (limit=100 each; first call with no cursor, then two cursor-paginated calls).
  - Page 1 cursor after fetch: `bmV4dF90czoxNzg1NDI0MjkxMTAxNDI5`
  - Page 2 cursor after fetch: `bmV4dF90czoxNzgyODAwMzg5NjI2MDc5`
  - Page 3 returned the tool's own completeness confirmation, quoted verbatim: **"There are no more messages available."**
- Pagination was walked to exhaustion — page 3 reached the channel-creation system messages (`has joined the channel` for Melisa, Sergey, and Nik at 2026-06-02 13:57 IDT), which is the earliest possible content for this channel. There is nothing older to fetch.

## Message counts

- Top-level channel messages captured: **220** (29 in June + 125 in July + 66 in August, verified by parsing the three JSON files)
- Threads found (messages showing a "Thread: N replies" marker in the top-level read): **8**
- Threads expanded via `slack_read_thread` (to exhaustion — each returned "There are no more messages in this thread."): **8 of 8** (100%)
- Total thread replies captured: **24** (4 in June + 16 in July + 4 in August)
  1. ts 1786101935.040789 (Slackbot "This message was deleted.", 2026-08-07) — 4 replies
  2. ts 1784815139.601429 (Sergey, "nice! I think it makes sense to have a brief demo", 2026-07-23) — 3 replies
  3. ts 1784814328.466599 (Sergey, "Got it, I think it makes sense to have a quick sync on Monday...", 2026-07-23) — 1 reply
  4. ts 1784812512.922429 (Sergey, "please let us know the current status with...", 2026-07-23) — 1 reply
  5. ts 1783431231.665679 (Melisa, "we are getting really a lot of 'No longer working there'...", 2026-07-07) — 10 replies
  6. ts 1783350043.954559 (Melisa, "No, this is another one that came in today", 2026-07-06) — 1 reply
  7. ts 1782497864.652819 (Melisa, "Hey guys, I had a meeting with Toby...", 2026-06-26) — 1 reply
  8. ts 1782229499.688359 (Melisa, "We should look into this", 2026-06-23) — 3 replies
- **Grand total messages captured (top-level + thread replies): 244**

## Date range

- Oldest message: **1780397831.694599** — 2026-06-02 13:57:11 IDT (Melisa Draksler joins the channel; immediately followed by the channel-creation message)
- Newest message: **1787051222.885189** — 2026-08-18 14:07:02 IDT (the day of this scrape)
- Spans three calendar months: **June 2026, July 2026, August 2026** — split into three files accordingly.

## Files written

- `slack_audit/raw/gtm-engineering/2026-06.json` — 06-02 through 06-30 (29 top-level + 4 thread-reply messages; 2 of the 8 threads)
- `slack_audit/raw/gtm-engineering/2026-07.json` — 07-01 through 07-31 (125 top-level + 16 thread-reply messages; most of the volume; 5 of the 8 threads)
- `slack_audit/raw/gtm-engineering/2026-08.json` — 08-07 through 08-18 (66 top-level + 4 thread-reply messages; no channel activity 08-01–08-06; 1 of the 8 threads)

All three threads with month-crossing-looking parents were checked; every thread's replies land in the same calendar month as its parent message, so no thread spans two output files.

## Cross-references NOT followed (out of scope for this channel-only scrape)

Several messages in #gtm-engineering point to content living outside this channel or outside Slack entirely. Per the task scope (this channel's Slack history only), these were **noted but not fetched**:

- SharePoint files/folders: "Sales Sprint London 2026 - Messaging" doc, "Trigger-based campaign ideas shortlisting.xlsx" folder (both referenced 2026-06/07 and 2026-07-30).
- Google Sheets: conference list spreadsheet (referenced 2026-07-03 and again 2026-07-10, same URL).
- Claude.ai artifacts linked twice (2026-06-25 ts 1782379103.765899, and 2026-08-07 ts 1786102033.444819) — external hosted content, not fetched.
- A GitHub repo (tinyfish-io/bigset) shared via a forwarded message from Toby Rawlinson (2026-06-03) — Toby Rawlinson's original message/channel is outside #gtm-engineering and was not fetched.
- Three in-channel "Forwarded message from ..." references that repost earlier same-channel messages (2026-08-11 ts 1786432894.618189 forwarding ts 1786121237.549359; 2026-07-30 ts 1785421314.881549 forwarding ts 1784049028.030199; 2026-07-30 ts 1785421668.290249 forwarding ts 1784812771.399729; 2026-07-30 ts 1785424407.439809 forwarding ts 1785422477.839729) — all four forwarded originals were already independently captured earlier in this same channel scrape, so no separate fetch was needed; this is noted in the relevant JSON entries rather than being a true out-of-scope cross-reference.
- Attached files (PDFs, images, one .csv, one .md) were listed by filename/ID/size/type as returned by the tool but their binary/file contents were not downloaded — only Slack's metadata about them is captured, consistent with "raw text as returned by the tools."
- Two messages contain what look like account credentials/invite codes pasted in plain text (2026-06-12 ts 1781259287.708719 "Apify subscription" and 2026-07-03 ts 1783074680.206449 "HeyReach") — captured verbatim as scraped per the raw-dump mandate, flagged with a `"note"` field in the JSON for Phase 2 attention; not acted upon.

## Confirmation

No messages were posted, no reactions were added, and no Slack state was modified during this scrape — read-only tools (`slack_read_channel`, `slack_read_thread`) only.
