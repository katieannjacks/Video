#!/usr/bin/env python3
"""Deterministic core of the school-email pipeline.

The LLM (the agent running the skill) handles FETCH and EXTRACT. This script
owns everything that must be deterministic and auditable:

  * validate  — structural validation of extracted events
  * route     — apply category routing + lead-time gating + dedup, decide
                what to surface now vs. hold vs. skip
  * record    — persist successfully-surfaced items so they're never
                surfaced again (the DEDUP guarantee across 3x/day cron runs)
  * mark-thread / processed — track which Gmail threads are done

No third-party dependencies — stdlib only, so it runs anywhere python3 does
and is trivially unit-testable.

Routing rules (overridable via config.json):

  action_required   -> notion   (surface immediately; event_date -> due date)
  school_closure    -> calendar (all-day; lead time 7 days)
  parent_attendance -> calendar (timed if event_time_start; lead time 14 days)
  fyi               -> dropped  (never surfaced)

A calendar item with no event_date can't be placed on a calendar (we never
invent dates), so it is rerouted to notion as a "needs a date" review task
instead of being silently lost.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime

VALID_CATEGORIES = ("action_required", "school_closure", "parent_attendance", "fyi")

CATEGORY_DESTINATION = {
    "action_required": "notion",
    "school_closure": "calendar",
    "parent_attendance": "calendar",
    "fyi": "none",
}

DEFAULT_LEAD_TIMES = {"school_closure": 7, "parent_attendance": 14}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Optional fields and the categories they're meaningful for. Used only for
# validation warnings, never to mutate the data.
OPTIONAL_FIELDS = ("action_text", "url", "event_time_start", "event_time_end")


def _default_state_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


def load_config(path):
    cfg = {
        "lead_times": dict(DEFAULT_LEAD_TIMES),
        "state_path": _default_state_path(),
    }
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        # Merge lead_times so partial overrides keep the defaults.
        lead = dict(DEFAULT_LEAD_TIMES)
        lead.update(user.get("lead_times", {}))
        cfg.update(user)
        cfg["lead_times"] = lead
        # Resolve a relative state_path against the config file's directory so
        # behavior doesn't depend on the current working directory.
        sp = cfg.get("state_path")
        if sp and not os.path.isabs(sp):
            cfg["state_path"] = os.path.join(os.path.dirname(os.path.abspath(path)), sp)
    if not cfg.get("state_path"):
        cfg["state_path"] = _default_state_path()
    return cfg


def load_state(path):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    else:
        state = {}
    state.setdefault("seen", {})
    state.setdefault("processed_threads", [])
    return state


def save_state(path, state):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _normalize_title(title):
    t = (title or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = t.strip(" .,!:;-")
    return t


def item_key(category, title, event_date, child="general"):
    """Stable dedup key. Deliberately excludes the source email so the same
    item bundled into multiple digests dedups to one row. Includes the resolved
    child so the same date for two different kids stays two distinct items."""
    basis = f"{category}|{_normalize_title(title)}|{event_date or 'null'}|{(child or 'general').lower()}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def resolve_child(item_child, sender_child, children):
    """Priority: explicit name on the item > sender's default child > general.
    Only names present in the configured `children` map are honored."""
    if item_child and item_child in children:
        return item_child
    if sender_child and sender_child in children:
        return sender_child
    return "general"


def child_color(child, children, default_color_id):
    info = children.get(child) if child else None
    if info and info.get("color_id"):
        return str(info["color_id"])
    return default_color_id


def validate_event(event, index):
    """Return a list of error strings for one event (empty == valid)."""
    errors = []
    if not isinstance(event, dict):
        return [f"event[{index}]: not an object"]

    cat = event.get("category")
    if cat not in VALID_CATEGORIES:
        errors.append(f"event[{index}]: category {cat!r} not in {VALID_CATEGORIES}")

    title = event.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"event[{index}]: title must be a non-empty string")

    ed = event.get("event_date", None)
    if ed not in (None, ""):
        if not isinstance(ed, str) or not DATE_RE.match(ed):
            errors.append(f"event[{index}]: event_date {ed!r} must be YYYY-MM-DD or null")
        else:
            try:
                datetime.strptime(ed, "%Y-%m-%d")
            except ValueError:
                errors.append(f"event[{index}]: event_date {ed!r} is not a real date")

    for field in ("event_time_start", "event_time_end"):
        val = event.get(field, "")
        if val not in (None, "") and not TIME_RE.match(str(val)):
            errors.append(f"event[{index}]: {field} {val!r} must be 24h HH:MM or empty")

    snip = event.get("snippet", "")
    if snip is not None and not isinstance(snip, str):
        errors.append(f"event[{index}]: snippet must be a string")

    child = event.get("child", None)
    if child not in (None, "") and not isinstance(child, str):
        errors.append(f"event[{index}]: child must be a name string or null")

    return errors


def _norm_date(ed):
    """Treat empty string as null."""
    if ed in (None, ""):
        return None
    return ed


def _iter_events(payload):
    """Accept several shapes:
      {"events": [...]}
      {"email_id": "...", "events": [...]}
      [{"email_id": "...", "events": [...]}, ...]
    Yields (source_email_id, event) tuples.
    """
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("input must be an object or a list of objects")
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("each extraction entry must be an object")
        email_id = entry.get("email_id") or entry.get("thread_id") or entry.get("message_id")
        sender_child = entry.get("sender_child")
        for event in entry.get("events", []):
            yield email_id, sender_child, event


def route(payload, cfg, state, today):
    lead_times = cfg.get("lead_times", DEFAULT_LEAD_TIMES)
    children = cfg.get("children", {})
    default_color_id = cfg.get("default_color_id")
    seen = state.get("seen", {})

    surface, held, skipped, errors = [], [], [], []

    raw = list(_iter_events(payload))
    for idx, (email_id, sender_child, event) in enumerate(raw):
        ev_errors = validate_event(event, idx)
        if ev_errors:
            errors.extend(ev_errors)
            continue

        cat = event["category"]
        title = event["title"]
        event_date = _norm_date(event.get("event_date"))
        child = resolve_child(event.get("child"), sender_child, children)
        color_id = child_color(child, children, default_color_id)
        key = item_key(cat, title, event_date, child)

        base = {
            "key": key,
            "category": cat,
            "title": title,
            "event_date": event_date,
            "child": child,
            "color_id": color_id,
            "snippet": event.get("snippet", ""),
            "action_text": event.get("action_text", ""),
            "url": event.get("url", ""),
            "event_time_start": event.get("event_time_start", ""),
            "event_time_end": event.get("event_time_end", ""),
            "source_email_id": email_id,
        }

        if cat == "fyi":
            skipped.append({**base, "reason": "fyi"})
            continue

        if key in seen:
            skipped.append({**base, "reason": "duplicate"})
            continue

        dest = CATEGORY_DESTINATION[cat]

        if dest == "calendar":
            if event_date is None:
                # Can't calendar without a date, and we never invent one.
                # Reroute to notion so a human can resolve it.
                surface.append({
                    **base,
                    "destination": "notion",
                    "all_day": None,
                    "reason": "no_date_review",
                })
                continue
            days_until = (datetime.strptime(event_date, "%Y-%m-%d").date() - today).days
            if days_until < 0:
                skipped.append({**base, "reason": "past", "days_until": days_until})
                continue
            lead = lead_times.get(cat, DEFAULT_LEAD_TIMES.get(cat, 0))
            if days_until > lead:
                held.append({**base, "reason": "lead_time", "days_until": days_until, "lead_days": lead})
                continue
            timed = cat == "parent_attendance" and bool(base["event_time_start"])
            surface.append({
                **base,
                "destination": "calendar",
                "all_day": not timed,
                "days_until": days_until,
                "reason": "in_window",
            })
            continue

        # destination == notion (action_required)
        reason = "action"
        if event_date is not None:
            days_until = (datetime.strptime(event_date, "%Y-%m-%d").date() - today).days
            if days_until < 0:
                reason = "overdue"
            base["days_until"] = days_until
        surface.append({**base, "destination": "notion", "all_day": None, "reason": reason})

    return {
        "today": today.isoformat(),
        "counts": {
            "surface": len(surface),
            "held": len(held),
            "skipped": len(skipped),
            "errors": len(errors),
        },
        "surface": surface,
        "held": held,
        "skipped": skipped,
        "errors": errors,
    }


def record(items, state, today):
    """Mark surfaced items as seen so they never surface again."""
    seen = state.setdefault("seen", {})
    recorded = 0
    for item in items:
        key = item.get("key")
        if not key:
            continue
        if key in seen:
            continue
        seen[key] = {
            "category": item.get("category"),
            "title": item.get("title"),
            "event_date": item.get("event_date"),
            "child": item.get("child"),
            "destination": item.get("destination"),
            "dest_id": item.get("dest_id", ""),
            "first_seen": today.isoformat(),
        }
        recorded += 1
    return recorded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_stdin_json():
    data = sys.stdin.read()
    if not data.strip():
        return {"events": []}
    return json.loads(data)


def _parse_today(value):
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today()


def cmd_validate(args):
    payload = _read_stdin_json()
    errors = []
    for idx, (_email, _sender_child, event) in enumerate(_iter_events(payload)):
        errors.extend(validate_event(event, idx))
    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    return 1 if errors else 0


def cmd_route(args):
    cfg = load_config(args.config)
    state = load_state(args.state or cfg["state_path"])
    payload = _read_stdin_json()
    result = route(payload, cfg, state, _parse_today(args.today))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_record(args):
    cfg = load_config(args.config)
    state_path = args.state or cfg["state_path"]
    state = load_state(state_path)
    payload = _read_stdin_json()
    # Accept either {"surface": [...]} (route output) or a bare list.
    if isinstance(payload, dict):
        items = payload.get("surface", payload.get("items", []))
    else:
        items = payload
    n = record(items, state, _parse_today(args.today))
    save_state(state_path, state)
    print(json.dumps({"recorded": n, "total_seen": len(state["seen"]), "state_path": state_path}, indent=2))
    return 0


def cmd_processed(args):
    cfg = load_config(args.config)
    state_path = args.state or cfg["state_path"]
    state = load_state(state_path)
    added = []
    for tid in args.thread_id:
        if tid not in state["processed_threads"]:
            state["processed_threads"].append(tid)
            added.append(tid)
    save_state(state_path, state)
    print(json.dumps({"added": added, "total": len(state["processed_threads"])}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="School-email pipeline: route/dedup core")
    parser.add_argument("--config", default=os.environ.get("SCHOOL_EMAIL_CONFIG"),
                        help="Path to config.json")
    parser.add_argument("--state", default=os.environ.get("SCHOOL_EMAIL_STATE"),
                        help="Override state file path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate extracted events from stdin")
    p_val.set_defaults(func=cmd_validate)

    p_route = sub.add_parser("route", help="Decide surface/hold/skip from stdin")
    p_route.add_argument("--today", help="Override today's date (YYYY-MM-DD)")
    p_route.set_defaults(func=cmd_route)

    p_rec = sub.add_parser("record", help="Mark surfaced items as seen")
    p_rec.add_argument("--today", help="Override today's date (YYYY-MM-DD)")
    p_rec.set_defaults(func=cmd_record)

    p_proc = sub.add_parser("processed", help="Mark Gmail threads as processed")
    p_proc.add_argument("thread_id", nargs="+")
    p_proc.set_defaults(func=cmd_processed)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
