# Inbox registry ingestion

Source: `Janea All Inboxes for Make.com Auto-Forward Workflow - Janea All Inboxes (1.15.2025).csv`

- data rows read: **699**
- unique inboxes ingested: **696**
- exact duplicates collapsed: **3** (across 3 addresses)
- CONFLICTING owners (flagged, NOT ingested): **0**
- malformed rows skipped: **0**
- distinct owners in the registry: **14**

## Inboxes per owner

| owner | inboxes |
|---|---|
| Mario | 104 |
| Toby | 78 |
| Sergey | 64 |
| Mirza | 61 |
| Andreas | 50 |
| James | 44 |
| Chrissy | 44 |
| Rune | 44 |
| Noah | 44 |
| Matt | 44 |
| Can | 43 |
| Bill | 42 |
| Benedetto | 20 |
| Melisa | 14 |

## Duplicate rows collapsed (same inbox, same owner)

- `pii-0a3c839e@example.invalid` x2
- `pii-0c26273b@example.invalid` x2
- `pii-37cf60ff@example.invalid` x2

## Owner map embedded in the sheet (columns 8/9) - independent cross-check

- Andreas -> andreas@janeasystems.com
- Can -> can@janeasystems.com
- Mario -> mario@janeasystems.com
- Melisa -> melisa@janeasystems.com
- Mirza -> mirza@janeasystems.com
- Test -> (blank in sheet)
- Toby -> toby@janeasystems.com
