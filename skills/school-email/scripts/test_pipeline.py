#!/usr/bin/env python3
"""Unit tests for the school-email pipeline core. Run with:

    python3 -m unittest skills/school-email/scripts/test_pipeline.py
"""

import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline  # noqa: E402

TODAY = date(2026, 6, 4)


def ev(**kw):
    base = {
        "category": "action_required",
        "title": "Thing",
        "event_date": None,
        "snippet": "",
        "action_text": "",
        "url": "",
        "event_time_start": "",
        "event_time_end": "",
    }
    base.update(kw)
    return base


CHILDREN = {
    "Audrey": {"color_id": "3"},
    "Cory": {"color_id": "10"},
    "Reid": {"color_id": "7"},
}


def run(events, state=None, today=TODAY, cfg=None):
    cfg = cfg or {"lead_times": dict(pipeline.DEFAULT_LEAD_TIMES)}
    state = state or {"seen": {}, "processed_threads": []}
    return pipeline.route({"events": events}, cfg, state, today)


def run_entries(entries, state=None, today=TODAY, cfg=None):
    """Route a list of per-email entries (each may carry sender_child)."""
    cfg = cfg or {"lead_times": dict(pipeline.DEFAULT_LEAD_TIMES), "children": CHILDREN}
    state = state or {"seen": {}, "processed_threads": []}
    return pipeline.route(entries, cfg, state, today)


class ValidationTests(unittest.TestCase):
    def test_valid_minimal(self):
        self.assertEqual(pipeline.validate_event(ev(), 0), [])

    def test_bad_category(self):
        errs = pipeline.validate_event(ev(category="nope"), 0)
        self.assertTrue(any("category" in e for e in errs))

    def test_empty_title(self):
        errs = pipeline.validate_event(ev(title="  "), 0)
        self.assertTrue(any("title" in e for e in errs))

    def test_bad_date_format(self):
        errs = pipeline.validate_event(ev(event_date="May 23"), 0)
        self.assertTrue(any("event_date" in e for e in errs))

    def test_impossible_date(self):
        errs = pipeline.validate_event(ev(event_date="2026-02-30"), 0)
        self.assertTrue(any("event_date" in e for e in errs))

    def test_null_date_ok(self):
        self.assertEqual(pipeline.validate_event(ev(event_date=None), 0), [])

    def test_bad_time(self):
        errs = pipeline.validate_event(
            ev(category="parent_attendance", event_date="2026-06-10", event_time_start="25:00"), 0)
        self.assertTrue(any("event_time_start" in e for e in errs))

    def test_good_time(self):
        self.assertEqual(
            pipeline.validate_event(
                ev(category="parent_attendance", event_date="2026-06-10",
                   event_time_start="09:30", event_time_end="10:30"), 0), [])

    def test_route_collects_errors_and_skips_bad_event(self):
        res = run([ev(category="bogus"), ev(title="Good")])
        self.assertEqual(res["counts"]["errors"], 1)
        # the good one still routes
        self.assertEqual(res["counts"]["surface"], 1)


class RoutingTests(unittest.TestCase):
    def test_fyi_dropped(self):
        res = run([ev(category="fyi", title="Principal leaving")])
        self.assertEqual(res["counts"]["surface"], 0)
        self.assertEqual(res["skipped"][0]["reason"], "fyi")

    def test_action_goes_to_notion_immediately(self):
        res = run([ev(category="action_required", title="Bring potluck dish")])
        self.assertEqual(res["surface"][0]["destination"], "notion")
        self.assertEqual(res["surface"][0]["all_day"], None)

    def test_closure_within_lead_surfaces_calendar_allday(self):
        res = run([ev(category="school_closure", title="Half day", event_date="2026-06-10")])
        s = res["surface"][0]
        self.assertEqual(s["destination"], "calendar")
        self.assertTrue(s["all_day"])

    def test_closure_beyond_lead_is_held(self):
        # 7-day lead; 30 days out -> held
        res = run([ev(category="school_closure", title="Summer break", event_date="2026-07-04")])
        self.assertEqual(res["counts"]["surface"], 0)
        self.assertEqual(res["held"][0]["reason"], "lead_time")
        self.assertEqual(res["held"][0]["lead_days"], 7)

    def test_attendance_lead_is_14(self):
        # 10 days out -> within 14-day window -> surface
        res = run([ev(category="parent_attendance", title="Concert", event_date="2026-06-14")])
        self.assertEqual(res["surface"][0]["destination"], "calendar")
        # 20 days out -> held
        res2 = run([ev(category="parent_attendance", title="Recital", event_date="2026-06-24")])
        self.assertEqual(res2["counts"]["held"], 1)

    def test_attendance_with_time_is_timed(self):
        res = run([ev(category="parent_attendance", title="Concert",
                      event_date="2026-06-10", event_time_start="18:00", event_time_end="19:30")])
        self.assertFalse(res["surface"][0]["all_day"])

    def test_attendance_without_time_is_allday(self):
        res = run([ev(category="parent_attendance", title="Field day", event_date="2026-06-10")])
        self.assertTrue(res["surface"][0]["all_day"])

    def test_past_event_skipped(self):
        res = run([ev(category="school_closure", title="Old day", event_date="2026-05-01")])
        self.assertEqual(res["skipped"][0]["reason"], "past")

    def test_today_closure_surfaces(self):
        res = run([ev(category="school_closure", title="Snow day", event_date="2026-06-04")])
        self.assertEqual(res["counts"]["surface"], 1)

    def test_null_date_calendar_reroutes_to_notion_review(self):
        res = run([ev(category="parent_attendance", title="Recital sometime", event_date=None)])
        s = res["surface"][0]
        self.assertEqual(s["destination"], "notion")
        self.assertEqual(s["reason"], "no_date_review")

    def test_overdue_action_still_surfaces(self):
        res = run([ev(category="action_required", title="Late form", event_date="2026-05-01")])
        self.assertEqual(res["surface"][0]["reason"], "overdue")

    def test_conservative_config_override(self):
        cfg = {"lead_times": {"school_closure": 3, "parent_attendance": 7}}
        # 5 days out with 3-day lead -> held
        res = run([ev(category="school_closure", title="PD day", event_date="2026-06-09")], cfg=cfg)
        self.assertEqual(res["counts"]["held"], 1)


class DedupTests(unittest.TestCase):
    def test_key_stable_across_title_whitespace_and_case(self):
        a = pipeline.item_key("school_closure", "Half Day, May 23", "2026-05-23")
        b = pipeline.item_key("school_closure", "  half day, may 23  ", "2026-05-23")
        self.assertEqual(a, b)

    def test_key_excludes_source_email(self):
        # same item, different digests -> same key (dedup across emails)
        res1 = run([ev(category="school_closure", title="Half day", event_date="2026-06-10")])
        key = res1["surface"][0]["key"]
        state = {"seen": {}, "processed_threads": []}
        pipeline.record(res1["surface"], state, TODAY)
        # second digest restates the same closure
        res2 = run([ev(category="school_closure", title="Half day", event_date="2026-06-10")], state=state)
        self.assertEqual(res2["counts"]["surface"], 0)
        self.assertEqual(res2["skipped"][0]["reason"], "duplicate")
        self.assertEqual(res2["skipped"][0]["key"], key)

    def test_held_item_not_recorded_resurfaces_when_in_window(self):
        state = {"seen": {}, "processed_threads": []}
        far = ev(category="school_closure", title="PD day", event_date="2026-06-20")
        # 16 days out -> held (7-day lead)
        res_far = run([far], state=state, today=date(2026, 6, 4))
        self.assertEqual(res_far["counts"]["held"], 1)
        pipeline.record(res_far["surface"], state, date(2026, 6, 4))  # records nothing
        self.assertEqual(len(state["seen"]), 0)
        # later, 5 days out -> surfaces
        res_near = run([far], state=state, today=date(2026, 6, 15))
        self.assertEqual(res_near["counts"]["surface"], 1)

    def test_record_is_idempotent(self):
        state = {"seen": {}, "processed_threads": []}
        items = run([ev(title="Form")])["surface"]
        self.assertEqual(pipeline.record(items, state, TODAY), 1)
        self.assertEqual(pipeline.record(items, state, TODAY), 0)


class ChildColorTests(unittest.TestCase):
    def test_sender_default_child_colors_calendar(self):
        # kkuhn -> Audrey: a dated closure from that sender is purple (3)
        entries = [{"email_id": "t1", "sender_child": "Audrey",
                    "events": [ev(category="school_closure", title="Half day", event_date="2026-06-10")]}]
        s = run_entries(entries)["surface"][0]
        self.assertEqual(s["child"], "Audrey")
        self.assertEqual(s["color_id"], "3")

    def test_explicit_name_overrides_sender(self):
        # General sender, but the item names Reid -> blue (7)
        entries = [{"email_id": "t1", "sender_child": "general",
                    "events": [ev(category="parent_attendance", title="Reid recital",
                                  event_date="2026-06-10", child="Reid", event_time_start="18:00")]}]
        s = run_entries(entries)["surface"][0]
        self.assertEqual(s["child"], "Reid")
        self.assertEqual(s["color_id"], "7")
        self.assertFalse(s["all_day"])

    def test_general_has_no_color(self):
        entries = [{"email_id": "t1", "sender_child": "general",
                    "events": [ev(category="school_closure", title="Teacher workday", event_date="2026-06-10")]}]
        s = run_entries(entries)["surface"][0]
        self.assertEqual(s["child"], "general")
        self.assertIsNone(s["color_id"])

    def test_unknown_child_name_falls_back_to_sender(self):
        entries = [{"email_id": "t1", "sender_child": "Audrey",
                    "events": [ev(category="school_closure", title="Half day",
                                  event_date="2026-06-10", child="Bartholomew")]}]
        self.assertEqual(run_entries(entries)["surface"][0]["child"], "Audrey")

    def test_default_color_applies_to_general(self):
        cfg = {"lead_times": dict(pipeline.DEFAULT_LEAD_TIMES), "children": CHILDREN, "default_color_id": "8"}
        entries = [{"email_id": "t1", "sender_child": "general",
                    "events": [ev(category="school_closure", title="PD day", event_date="2026-06-10")]}]
        self.assertEqual(run_entries(entries, cfg=cfg)["surface"][0]["color_id"], "8")

    def test_same_date_two_kids_not_deduped(self):
        cfg = {"lead_times": dict(pipeline.DEFAULT_LEAD_TIMES), "children": CHILDREN}
        state = {"seen": {}, "processed_threads": []}
        cory = [{"email_id": "t1", "sender_child": "general",
                 "events": [ev(category="parent_attendance", title="Field day",
                               event_date="2026-06-10", child="Cory")]}]
        reid = [{"email_id": "t2", "sender_child": "general",
                 "events": [ev(category="parent_attendance", title="Field day",
                               event_date="2026-06-10", child="Reid")]}]
        r1 = pipeline.route(cory, cfg, state, TODAY)
        pipeline.record(r1["surface"], state, TODAY)
        r2 = pipeline.route(reid, cfg, state, TODAY)
        # different child -> different key -> still surfaces
        self.assertEqual(r2["counts"]["surface"], 1)
        self.assertEqual(r2["surface"][0]["color_id"], "7")

    def test_child_in_validate(self):
        self.assertEqual(pipeline.validate_event(ev(child="Audrey"), 0), [])
        self.assertEqual(pipeline.validate_event(ev(child=None), 0), [])
        errs = pipeline.validate_event(ev(child=123), 0)
        self.assertTrue(any("child" in e for e in errs))


class StateIOTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "state.json")
            state = pipeline.load_state(path)
            state["seen"]["abc"] = {"title": "x"}
            pipeline.save_state(path, state)
            again = pipeline.load_state(path)
            self.assertIn("abc", again["seen"])

    def test_config_partial_lead_time_merge(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w") as fh:
                fh.write('{"sender":"x@y.edu","lead_times":{"school_closure":3}}')
            cfg = pipeline.load_config(path)
            self.assertEqual(cfg["lead_times"]["school_closure"], 3)
            # untouched key keeps default
            self.assertEqual(cfg["lead_times"]["parent_attendance"], 14)


class InputShapeTests(unittest.TestCase):
    def test_accepts_list_of_emails(self):
        payload = [
            {"email_id": "t1", "events": [ev(title="A")]},
            {"email_id": "t2", "events": [ev(title="B")]},
        ]
        cfg = {"lead_times": dict(pipeline.DEFAULT_LEAD_TIMES)}
        res = pipeline.route(payload, cfg, {"seen": {}, "processed_threads": []}, TODAY)
        self.assertEqual(res["counts"]["surface"], 2)
        self.assertEqual({s["source_email_id"] for s in res["surface"]}, {"t1", "t2"})

    def test_empty(self):
        res = run([])
        self.assertEqual(res["counts"], {"surface": 0, "held": 0, "skipped": 0, "errors": 0})


if __name__ == "__main__":
    unittest.main()
