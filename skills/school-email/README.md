# school-email

A Claude Code skill that triages **school email** into two trustworthy outputs:

```
FETCH    unread mail from ONE school sender (Gmail)
  ↓
EXTRACT  read the whole email → structured items (category + date + verbatim quote)
  ↓
ROUTE    action_required        → Notion task list
         school_closure (7d)    ┐
         parent_attendance (14d)┘→ Google Calendar, on a lead-time delay
         fyi                     → dropped
  ↓
DEDUP    a stable per-item key + a state file → never surface the same thing
         twice, even though cron runs ~3x/day
```

School emails arrive as digests ("Community Update", "Weekly Update") that bundle
several messages and bury the actual ask 4–6 paragraphs deep. The skill reads the
whole thing, pulls out every item, and never invents a date, time, or link it
can't quote from the text.

## How it's built

- **`SKILL.md`** — orchestration the agent follows each run (FETCH → EXTRACT →
  ROUTE → RECORD). Uses the Gmail, Notion, and Google Calendar MCP servers.
- **`scripts/extraction_prompt.md`** — the canonical, verbatim EXTRACT contract
  (categories, rules, JSON schema).
- **`scripts/pipeline.py`** — dependency-free, deterministic core: `validate`,
  `route` (category routing + lead-time gating), `record`/`processed` (dedup
  state). The model never hand-rolls this logic.
- **`scripts/test_pipeline.py`** — 29 unit tests covering validation, routing,
  lead-time hold/release, dedup, and state I/O.

## Setup

1. Connect the **Gmail**, **Notion**, and **Google Calendar** MCP servers.
2. `cp scripts/config.example.json scripts/config.json` and fill in:
   - `sender` — the one school address to watch.
   - `notion_data_source_id` — the task database (create one via the Notion
     `notion-create-database` tool; schema is in `SKILL.md`).
   - `timezone`, `calendar_id`, lead times — adjust if needed.
3. `bash scripts/setup.sh` to verify.
4. Run it: tell the agent **"Run the school-email skill"**, or schedule it (see
   the Cron section in `SKILL.md`).

## Configuration

| Key | Meaning | Default |
|-----|---------|---------|
| `sender` | The single Gmail sender to watch | — (required) |
| `notion_data_source_id` | Notion task DB data source | — (required) |
| `calendar_id` | Target Google Calendar | `primary` |
| `timezone` | IANA tz for timed events | `America/New_York` |
| `gmail_processed_label` | Label applied after processing | `Processed/School` |
| `lead_times.school_closure` | Days ahead closures surface | `7` |
| `lead_times.parent_attendance` | Days ahead events surface | `14` |
| `state_path` | Dedup state file | `scripts/state.json` |

**Lead-time delay:** an item farther out than its lead time is *held* (not
recorded), so the calendar/tasks don't fill with far-future noise. A later run
surfaces it once it enters the window. Items with no parseable date that would
otherwise be calendar entries are rerouted to Notion as `review` tasks rather
than dropped.

## Test

```bash
python3 -m unittest scripts/test_pipeline.py
```
