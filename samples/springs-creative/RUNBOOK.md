# Springs Creative — autopost runbook

Plain-English guide to running this on an ongoing basis.

## Where it lives
- **On your Mac:** `~/Desktop/video-use` (the folder you cloned).
- **Backed up on GitHub:** `katieannjacks/Video`, branch
  `claude/sample-video-new-repo-H5x5C`. If your Mac ever dies, re-clone it.

## The most important thing to know
**Posting is already automatic.** Once a post is *scheduled*, GoHighLevel
publishes it at its set time. **Your Mac can be closed/off** — you do NOT need to
leave anything running. The script's only job is to *create* the scheduled posts.

## One-time: save your login
So you don't re-paste your token every time:
```bash
cd ~/Desktop/video-use
cp samples/springs-creative/ghl.env.example ghl.env
open -e ghl.env        # paste your current GHL token, save
```
`ghl.env` stays on your Mac (gitignored).

## Schedule a new batch — ONE command
Pick a **Monday** as the start date. Preview first, then add `go`:
```bash
cd ~/Desktop/video-use
./samples/springs-creative/autopost.sh 2026-07-13        # preview (nothing posts)
./samples/springs-creative/autopost.sh 2026-07-13 go     # schedule for real
```
This schedules all six clips to **GBP (images) + Facebook (video) + YouTube
(Shorts)**, Mon/Wed/Fri for two weeks. Run it **once per date** (running twice
with the same date double-books — see "Fix duplicates" below).

## Add NEW / more content
Generating new videos needs the studio (ffmpeg, fonts, AI voice) — that lives in
**Claude Code on the web**, not your Mac. So the loop is:

1. Open **claude.ai/code** → this project → say e.g.
   *"make 4 new videos about holiday promos, same brand, schedule for the week of Dec 1."*
   Claude builds the videos + images and commits them.
2. On your Mac:
   ```bash
   cd ~/Desktop/video-use
   ./samples/springs-creative/autopost.sh 2026-12-01 go
   ```

**Just changing captions/dates** (reusing existing videos)? Edit the `PLAN`
block at the top of `samples/springs-creative/ghl_schedule.py`, then run
autopost with a new date.

## Fix duplicates (if you ever double-book)
```bash
python3 samples/springs-creative/ghl_schedule.py dedupe --account <FB-id>          # preview
python3 samples/springs-creative/ghl_schedule.py dedupe --commit --account <FB-id> # delete extras
```
(Get account ids any time with: `python3 samples/springs-creative/ghl_schedule.py verify`.)

## Housekeeping
- **Rotate your GHL token** every so often (Settings → Private Integrations).
  Update `ghl.env` when you do.
- Edit everything in GHL → **Social Planner** (captions, times, delete posts).
- If you reconnect a social account, its id changes — run `verify` and update the
  ids near the top of `autopost.sh`.

## Fully automatic (advanced, optional)
You *can* have macOS run autopost on a schedule (cron/launchd), but it requires
your Mac awake + a valid token + fresh content each time, so it's usually not
worth it. The recommended rhythm is the ~10-minute monthly ritual above:
new content from Claude → one `autopost ... go`.
