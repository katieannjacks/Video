---
name: school-email
description: "Triage school emails into a calendar and a task list. Pulls unread mail from one school sender in Gmail, extracts every buried ask from digest-style 'Community Update' emails into structured items, then routes action items to a Notion task list and closures/events to Google Calendar on a lead-time delay — deduping so the same thing never surfaces twice across a 3x/day cron. Use when asked to process, triage, or check school email, or when run on a schedule."
version: 1.0.0
---

# School-Email Pipeline

Turn the firehose of school email into exactly two trustworthy outputs: a **task
list** (Notion) of things the parent must do, and a **calendar** (Google
Calendar) of closures and events the parent must plan around — each surfaced only
when it's close enough to matter, and never twice.

## Principle

1. **Determinism lives in code, judgment lives in the model.** `scripts/pipeline.py`
   owns validation, lead-time gating, and dedup. You own reading the email and
   extracting items. Never reimplement routing/dedup logic by hand — pipe through
   the script so behavior is identical every run.
2. **Read the whole email.** Asks are buried 4–6 paragraphs into digests that
   bundle 2–5 messages. Skimming the subject line loses the potluck sign-up.
3. **Never invent.** No date in the text → `null`. No time → empty. No link →
   empty. A fabricated calendar entry is worse than a missing one.
4. **Surface once.** The cron runs ~3x/day. The state file is the memory that
   keeps you from double-booking. Always `record` what you surfaced.

## Prerequisites (one-time)

- `scripts/config.json` exists (copy `config.example.json`) with a `senders` map
  and `notion_data_source_id`. Run `bash scripts/setup.sh` to check.
- The three MCP servers are connected: **Gmail**, **Notion**, **Google Calendar**.
  Tool names below are given by their suffix (e.g. `search_threads`); the server
  prefix is whatever this environment assigns.
- A Gmail label for processed mail (default `Processed/School`). Create it with
  the Gmail `create_label` tool if `list_labels` doesn't show it.
- A Notion task database. If `notion_data_source_id` is empty, create one with
  `notion-create-database` (schema below) and paste its data source ID into the
  config before continuing.

  ```sql
  CREATE TABLE ("Task" TITLE, "Status" STATUS, "Due" DATE,
                "Category" SELECT('action_required':blue, 'review':orange),
                "Child" SELECT('Audrey':purple, 'Cory':green, 'Reid':blue, 'General':gray),
                "Source quote" RICH_TEXT, "Link" URL)
  ```

### Senders and per-child colors

`config.json` watches several `senders`, each mapped to a default child (or
`general`). `children` maps each child to a Google Calendar `colorId`:

| Child | Color | colorId |
|-------|-------|---------|
| Audrey (5th) | purple — Grape | `3` |
| Cory (K) | green — Basil | `10` |
| Reid (K) | blue — Peacock | `7` |
| general | calendar default | none |

A child is resolved per item with priority **explicit name in the email →
sender's default child → general**. So a General-sender email that names Cory
turns green; an unattributed closure stays the default color. `pipeline.py`
computes the resolved `child` and `color_id` for you — don't do it by hand.

## Run loop

Read `scripts/extraction_prompt.md` first — it is the canonical EXTRACT contract.

### 1. FETCH

Build one query from all configured senders and pull unread:
`query: "from:(kkuhn@wcpss.net OR bcline@wcpss.net OR cstomp@wcpss.net OR noreply@wcpss.net) is:unread"`
(use the actual keys of `senders`). For each thread returned, call `get_thread`
with `messageFormat: FULL_CONTENT` to get the full body of every message. Note
each thread's actual `From` address and `threadId` — you need both: the From
address selects the sender's default child, the threadId marks it processed.

If nothing is unread, stop: there's nothing to do.

### 2. EXTRACT

For each email, apply the prompt in `scripts/extraction_prompt.md` to the
**entire body** and produce the JSON it specifies. One object per email, tagged
with the sender's default child (look up the From address in `senders`):

```json
{ "email_id": "<threadId>", "sender_child": "<senders[from] or 'general'>", "events": [ … ] }
```

The per-item `child` field (set only when a child is named in the text) overrides
`sender_child`. If a digest's messages come from different senders, split it into
one entry per sender so `sender_child` stays correct.

Collect them into a list. Validate before routing:

```bash
echo '<the list>' | python3 scripts/pipeline.py validate
```

If `valid` is false, fix the offending event (usually an unescaped quote in a
`snippet`) and re-validate. Per the contract, a malformed extraction is
discarded — never push unvalidated items downstream.

### 3. ROUTE

```bash
echo '<the list>' | python3 scripts/pipeline.py --config scripts/config.json route
```

The output partitions every item into `surface` / `held` / `skipped` and assigns
each surfaced item a `destination` and stable `key`. You only act on `surface`:

- **`destination: "notion"`** — create a row with `notion-create-pages` under the
  configured `data_source_id`. Map: `Task`←title, `Due`←event_date (omit if
  null), `Category`←`action_required` or `review` (when `reason` is
  `no_date_review`), `Child`←`child` (use `General` when child is `general`),
  `Source quote`←snippet, `Link`←url. Put `action_text` in the page body.
- **`destination: "calendar"`** — create an event with `create_event`. Pass
  `colorId` = the item's `color_id` when it's non-null (purple/green/blue per
  child); omit `colorId` entirely when it's null (general → calendar default).
  Set `calendarId` from config. Then:
  - `all_day: true` → set `allDay: true`; `startTime`/`endTime` = the
    `event_date` at midnight (same day, or end = next day).
  - `all_day: false` → build `startTime`/`endTime` from `event_date` +
    `event_time_start`/`event_time_end` (use a 1-hour default end only if
    `event_time_end` is empty). Pass `timeZone` from config.
  - Put the `snippet` in `description` so the calendar entry is auditable.

`held` items are deliberately not yet surfaced (too far out) — do nothing; a
future run will pick them up when they enter the lead-time window. `skipped`
items (`fyi`, `duplicate`, `past`) need no action.

If a downstream create call fails, do **not** record that item — leave it for the
next run rather than losing the dedup guarantee.

### 4. RECORD + mark read

Record only the items you successfully created, so they never surface again:

```bash
echo '<JSON list of the surfaced items you created>' \
  | python3 scripts/pipeline.py --config scripts/config.json record
```

(You can pipe the whole `route` output's `surface` array, or filter to the ones
that succeeded.) Then, for each fully-processed thread, use the Gmail
`label_thread` tool to remove `UNREAD` and add the `Processed/School` label, and
call `pipeline.py processed <threadId>` to log it. This keeps the next run from
re-reading the same mail.

### 5. Report

Summarize for the user: N tasks added, N calendar events added, what's held and
when it'll surface, and anything skipped for review (`no_date_review` items —
flag these, they had no parseable date).

## Hard rules

- **Pipe through `pipeline.py` for routing and dedup. Always.** Don't eyeball
  lead times or hand-track what you've seen.
- **`record` only what landed.** A surfaced-but-failed item must remain
  un-recorded.
- **One sender.** The pipeline watches exactly the configured address. Don't
  widen the Gmail query.
- **Verbatim snippets.** The `snippet` is the human's audit trail — never
  summarize it, never invent it.

## Cron

Three times a day, headless:

```cron
0 7,12,18 * * *  cd /path/to/repo && claude -p "Run the school-email skill" >> /tmp/school-email.log 2>&1
```

Dedup makes repeated runs safe: anything already surfaced is skipped, anything
still too far out stays held.
