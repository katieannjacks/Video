#!/usr/bin/env bash
# autopost.sh — schedule a fresh batch to GBP + Facebook + YouTube in ONE command.
#
# Usage (from the repo root, ~/Desktop/video-use):
#   ./samples/springs-creative/autopost.sh 2026-07-13        # PREVIEW (no posting)
#   ./samples/springs-creative/autopost.sh 2026-07-13 go     # actually schedule
#
# Credentials: it reads GHL_TOKEN / GHL_LOCATION_ID from your shell, or from a
# file named  ghl.env  in the repo root (copy ghl.env.example -> ghl.env and fill
# it in once; ghl.env is gitignored so it never leaves your Mac).
#
# Run ONCE per batch (one unique start date). Running twice with the same date
# double-books — if that happens, use the `dedupe` command (see RUNBOOK.md).

set -euo pipefail
cd "$(dirname "$0")/../.."                 # repo root

[ -f ghl.env ] && { set -a; . ./ghl.env; set +a; }
: "${GHL_TOKEN:?Set GHL_TOKEN (export it, or create ghl.env from ghl.env.example)}"
: "${GHL_LOCATION_ID:?Set GHL_LOCATION_ID}"

START="${1:?usage: ./autopost.sh YYYY-MM-DD [go]}"
COMMIT=""; MODE="PREVIEW (dry run — nothing scheduled)"
[ "${2:-}" = "go" ] && { COMMIT="--commit"; MODE="LIVE — scheduling for real"; }

S="samples/springs-creative/ghl_schedule.py"
# Connected account ids (from `verify`; update here if you reconnect accounts)
FB="6a3c1c8703851bb947dea053_ibvPpyoxFegC4gujJX5f_1162630580269373_page"
YT="6a3c1f7779a3769b79a98f27_ibvPpyoxFegC4gujJX5f_UCCWABfhzbTlDuVbahQ3s40w_profile"

echo "=== Springs Creative autopost — week of $START — $MODE ==="
git pull --quiet || true

echo; echo ">> Google Business Profile (branded images)"
python3 "$S" plan --start "$START" $COMMIT

echo; echo ">> Facebook (videos)"
python3 "$S" plan --start "$START" $COMMIT --account "$FB"

echo; echo ">> YouTube Shorts (vertical)"
python3 "$S" plan --start "$START" $COMMIT --vertical --account "$YT"

echo; echo "=== Done ($MODE). ==="
[ -z "$COMMIT" ] && echo "Looks right? Re-run with 'go' on the end to schedule:  ./samples/springs-creative/autopost.sh $START go"
