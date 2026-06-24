#!/usr/bin/env python3
"""
ghl_schedule.py — upload the Springs Creative videos to GoHighLevel and
schedule them to your connected Google Business Profile (Social Planner).

WHY THIS RUNS LOCALLY: the Claude Code web environment blocks egress to
services.leadconnectorhq.com. Your Mac has no such restriction, so you run
this one command and it talks to the GHL API directly.

------------------------------------------------------------------------------
SETUP (one time, on your Mac, inside the repo)
------------------------------------------------------------------------------
  cd ~/Desktop/video-use            # wherever you cloned the repo
  python3 -m pip install requests   # the only dependency
  # create a FRESH GHL Private Integration Token (rotate the old one!)
  # Settings -> Private Integrations -> scopes: "Social Planner" + "Medias"
  export GHL_TOKEN="pit-xxxxxxxx..."
  export GHL_LOCATION_ID="ibvPpyoxFegC4gujJX5f"

------------------------------------------------------------------------------
USAGE
------------------------------------------------------------------------------
  # 1) confirm the token works and find your GBP account
  python3 samples/springs-creative/ghl_schedule.py verify

  # 2) preview exactly what WOULD be scheduled (no API writes) — default
  python3 samples/springs-creative/ghl_schedule.py plan --start 2026-06-30

  # 3) actually upload + schedule (writes to GHL)
  python3 samples/springs-creative/ghl_schedule.py plan --start 2026-06-30 --commit

Notes:
  • Posts to your Google Business Profile by default (auto-detected). Override
    with --account <id>, or --all-accounts to post everywhere connected.
  • Times are 10:00 AM America/New_York. Edit PLAN below to taste.
  • Everything is a dry run until you pass --commit.
  • The GHL API is verbose here on purpose — if a field is rejected, paste the
    printed response back to me and I'll adjust the payload.
"""
from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run:  python3 -m pip install requests")

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/New_York")
except Exception:
    TZ = None  # falls back to naive local time

BASE = "https://services.leadconnectorhq.com"
VERSION = "2021-07-28"
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

CTA = "https://ai-audit.springsyncai.com/landing"

# ---- the posting plan (edit freely) ----------------------------------------
# day_offset = days after --start ; hour = local ET hour
PLAN = [
    dict(day=0,  hour=10, video="main-landscape.mp4",
         caption=("Your next customer is already scrolling. Springs Creative Marketing helps "
                  "Triangle businesses show up with strategy, not guesswork — modern websites, "
                  f"clean local SEO, social that sounds like you, and practical AI. Book your FREE audit: {CTA}")),
    dict(day=2,  hour=10, video="websites-landscape.mp4",
         caption=f"Your website is your first impression. Modern, fast, built to convert. Free audit: {CTA}"),
    dict(day=4,  hour=10, video="local-seo-landscape.mp4",
         caption=f"When your neighbors search, be the first name they find. Clean local SEO + smart content. Free audit: {CTA}"),
    dict(day=7,  hour=10, video="social-landscape.mp4",
         caption=f"Your brand has a voice — your marketing should too. Social that brings in real leads. Free audit: {CTA}"),
    dict(day=9,  hour=10, video="ai-edge-landscape.mp4",
         caption=f"Want an edge most local businesses don't have? Practical AI that saves you time. Free audit: {CTA}"),
    dict(day=11, hour=10, video="main-square.mp4",
         caption=f"Marketing that's clear, measured, and built to grow. Book your FREE marketing audit: {CTA}"),
]


def headers():
    tok = os.environ.get("GHL_TOKEN", "").strip()
    if not tok:
        sys.exit("Set GHL_TOKEN (export GHL_TOKEN=pit-...).")
    return {"Authorization": f"Bearer {tok}", "Version": VERSION, "Accept": "application/json"}


def location_id():
    loc = os.environ.get("GHL_LOCATION_ID", "").strip()
    if not loc:
        sys.exit("Set GHL_LOCATION_ID (export GHL_LOCATION_ID=...).")
    return loc


def get_accounts():
    """Return the raw JSON from the accounts endpoint."""
    loc = location_id()
    r = requests.get(f"{BASE}/social-media-posting/{loc}/accounts", headers=headers(), timeout=30)
    if r.status_code >= 300:
        sys.exit(f"accounts failed [{r.status_code}]: {r.text}")
    return r.json()


def extract_accounts(data):
    """Find the list of account dicts regardless of response nesting."""
    lst = None
    if isinstance(data, list):
        lst = data
    elif isinstance(data, dict):
        for k in ("accounts", "results", "data"):
            v = data.get(k)
            if isinstance(v, list):
                lst = v
                break
            if isinstance(v, dict):
                for k2 in ("accounts", "results"):
                    if isinstance(v.get(k2), list):
                        lst = v[k2]
                        break
            if lst is not None:
                break
    return [a for a in (lst or []) if isinstance(a, dict)]


def cmd_verify(_args):
    data = get_accounts()
    accts = extract_accounts(data)
    if not accts:
        print("Token reached GHL, but I couldn't auto-parse the account list.")
        print("Copy everything below and send it to Claude:\n")
        print(json.dumps(data, indent=2)[:4000])
        return
    print(f"Token OK. {len(accts)} connected account(s):\n")
    for a in accts:
        plat = str(a.get("platform") or a.get("type") or "?")
        name = str(a.get("name") or a.get("accountName") or "?")
        print(f"  platform={plat:<18} name={name:<30} id={a.get('id') or a.get('_id')}")
    gbp = _find_gbp(accts)
    print("\nGoogle Business Profile:",
          (gbp.get('id') or gbp.get('_id')) if gbp else "not auto-detected — use --account <id> from the list above")
    print("\n--- raw response (for reference) ---")
    print(json.dumps(data, indent=2)[:3000])


def _find_gbp(accts):
    for a in accts:
        blob = " ".join(str(a.get(k, "")) for k in ("platform", "type", "name", "accountName")).lower()
        if any(w in blob for w in ("google", "gmb", "business profile", "gbp", "mybusiness")):
            return a
    return None


def upload_media(path: Path) -> str:
    """Upload a local file to the GHL media library; return its public URL."""
    loc = location_id()
    with open(path, "rb") as fh:
        files = {"file": (path.name, fh, "video/mp4")}
        data = {"hosted": "false", "name": path.name, "altType": "location", "altId": loc}
        r = requests.post(f"{BASE}/medias/upload-file", headers=headers(), files=files, data=data, timeout=300)
    if r.status_code >= 300:
        sys.exit(f"media upload failed for {path.name} [{r.status_code}]: {r.text}")
    j = r.json()
    url = j.get("url") or j.get("fileUrl") or j.get("link") or (j.get("file") or {}).get("url")
    if not url:
        sys.exit(f"media upload returned no URL for {path.name}: {j}")
    return url


def create_post(account_ids, caption, media_url, when_iso, commit):
    loc = location_id()
    payload = {
        "accountIds": account_ids,
        "summary": caption,
        "media": [{"url": media_url, "type": "video"}],
        "status": "scheduled",
        "scheduleDate": when_iso,
        "type": "post",
    }
    if not commit:
        print(f"   DRY-RUN payload: accounts={account_ids} when={when_iso} media={media_url[:60]}…")
        return
    r = requests.post(f"{BASE}/social-media-posting/{loc}/posts", headers=headers(), json=payload, timeout=60)
    if r.status_code >= 300:
        sys.exit(f"create post failed [{r.status_code}]: {r.text}")
    print(f"   scheduled ✓  id={r.json().get('id') or r.json().get('_id','?')}")


def cmd_plan(args):
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    accts = extract_accounts(get_accounts())
    if args.account:
        account_ids = [args.account]
    elif args.all_accounts:
        account_ids = [a.get("id") or a.get("_id") for a in accts]
    else:
        gbp = _find_gbp(accts)
        if not gbp:
            sys.exit("No Google Business Profile account found. Use --account <id> or --all-accounts (run 'verify' to list).")
        account_ids = [gbp.get("id") or gbp.get("_id")]

    print(f"{'COMMITTING' if args.commit else 'DRY RUN'} — {len(PLAN)} posts → accounts {account_ids}\n")
    for item in PLAN:
        path = OUT / item["video"]
        if not path.exists():
            sys.exit(f"missing video: {path}")
        dt = datetime.combine(start + timedelta(days=item["day"]), dtime(item["hour"], 0))
        if TZ:
            dt = dt.replace(tzinfo=TZ)
        iso = dt.isoformat()
        print(f"• {item['video']:<26} {iso}")
        media_url = upload_media(path) if args.commit else "(dry-run, upload skipped)"
        create_post(account_ids, item["caption"], media_url, iso, args.commit)
    print("\nDone." if args.commit else "\nDry run complete — add --commit to schedule for real.")


def main():
    ap = argparse.ArgumentParser(description="Schedule Springs Creative videos to GHL Social Planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="check token + list connected accounts")
    p = sub.add_parser("plan", help="schedule the PLAN to GBP")
    p.add_argument("--start", required=True, help="first post date, YYYY-MM-DD")
    p.add_argument("--commit", action="store_true", help="actually write to GHL (default is dry run)")
    p.add_argument("--account", help="post to a specific account id")
    p.add_argument("--all-accounts", action="store_true", help="post to every connected account")
    args = ap.parse_args()
    {"verify": cmd_verify, "plan": cmd_plan}[args.cmd](args)


if __name__ == "__main__":
    main()
