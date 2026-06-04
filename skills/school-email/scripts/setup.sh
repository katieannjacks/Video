#!/usr/bin/env bash
set -euo pipefail
G="\033[0;32m"; R="\033[0;31m"; Y="\033[0;33m"; N="\033[0m"
ok()   { echo -e "  ${G}+${N} $1"; }
fail() { echo -e "  ${R}x${N} $1"; }
warn() { echo -e "  ${Y}!${N} $1"; }
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""; echo "School-Email Pipeline — Setup Check"; echo ""
errors=0

command -v python3 &>/dev/null && ok "Python $(python3 --version 2>&1 | awk '{print $2}')" \
  || { fail "Python 3 not found"; errors=$((errors+1)); }

if python3 "$here/pipeline.py" validate </dev/null >/dev/null 2>&1; then
  ok "pipeline.py runs"
else
  fail "pipeline.py failed to run"; errors=$((errors+1))
fi

if python3 -m unittest "$here/test_pipeline.py" >/dev/null 2>&1; then
  ok "unit tests pass"
else
  fail "unit tests failing — run: python3 -m unittest $here/test_pipeline.py"; errors=$((errors+1))
fi

if [ -f "$here/config.json" ]; then
  ok "config.json present"
  python3 - "$here/config.json" <<'PY' || warn "config.json still has placeholder values to fill in"
import json,sys
c=json.load(open(sys.argv[1]))
bad=[]
if str(c.get("notion_data_source_id","")).startswith("REQUIRED") or not c.get("notion_data_source_id"):
    bad.append("notion_data_source_id")
senders=c.get("senders") or {}
if not senders or any("yourschool" in s for s in senders):
    bad.append("senders")
sys.exit(1 if bad else 0)
PY
else
  warn "no config.json yet — copy config.example.json to config.json and fill it in"
fi

echo ""
echo "MCP servers required at run time (provided by the agent, not this script):"
echo "  - Gmail    (search_threads, get_thread, label_thread, list_labels, create_label)"
echo "  - Notion   (notion-create-pages, notion-create-database, notion-fetch)"
echo "  - Calendar (create_event, list_events, list_calendars)"
echo ""
[ $errors -eq 0 ] && echo -e "${G}Core checks passed.${N}" || echo -e "${R}$errors check(s) failed.${N}"
echo ""
