#!/usr/bin/env python3
"""
find_leads.py — find local contractor leads for web-design outreach.

A small, one-off tool. It queries the official Google Places API for
contractor-type businesses across a set of locations, then writes leads.csv.
Businesses with NO website are flagged HOT — they're exactly who the
"I build contractors a website" offer is for.

This is a lead-LIST builder, not an automated outreach system. Run it once,
get your CSV, then work the leads by hand.

------------------------------------------------------------------------------
REQUIREMENTS
    Python 3.8+
    pip install requests
------------------------------------------------------------------------------
HOW TO GET A GOOGLE PLACES API KEY (~10 minutes)
    1. Go to https://console.cloud.google.com/ and create/select a project.
    2. APIs & Services -> Library -> enable "Places API" (the older Places API,
       a.k.a. "Places API (Legacy)"). This script uses the classic Text Search
       + Place Details endpoints.
    3. APIs & Services -> Credentials -> Create credentials -> API key.
    4. Add billing to the project. Google gives a recurring free credit that
       easily covers a few hundred lookups, so this run won't actually cost you.
------------------------------------------------------------------------------
HOW TO RUN
    export GOOGLE_PLACES_API_KEY="your_key_here"      # Windows: set GOOGLE_PLACES_API_KEY=...
    python find_leads.py

    Produces leads.csv in the current folder, HOT (no-website) leads on top.
------------------------------------------------------------------------------
"""

import csv
import os
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests")

# ---- Configurable search ----------------------------------------------------
QUERIES = [
    "general contractor", "kitchen remodeling", "bathroom remodeling",
    "carpentry", "tile installation", "home remodeling", "deck builder",
]
LOCATIONS = [
    "Clayton NC", "Four Oaks NC", "Smithfield NC", "Garner NC",
    "Johnston County NC",
]

# ---- API plumbing -----------------------------------------------------------
TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
DETAIL_FIELDS = ",".join([
    "name", "formatted_phone_number", "website", "formatted_address",
    "rating", "user_ratings_total", "business_status", "url",
])
OUTPUT_FILE = "leads.csv"
REQUEST_PAUSE = 0.3       # be polite between requests
MAX_PAGES = 3            # Google returns at most 3 pages (~60 results) per query


def get_key():
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        sys.exit(
            "GOOGLE_PLACES_API_KEY is not set.\n"
            'Set it first, e.g.:  export GOOGLE_PLACES_API_KEY="your_key_here"'
        )
    return key


def get_json(url, params, retries=3):
    """GET with a couple of retries on transient network/server errors."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"  ! request failed: {e}")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def check_status(data, context):
    """Return True if usable. Hard-stop on auth/billing errors."""
    if data is None:
        return False
    status = data.get("status", "UNKNOWN")
    if status in ("OK", "ZERO_RESULTS"):
        return status == "OK"
    msg = data.get("error_message", "")
    if status in ("REQUEST_DENIED", "INVALID_REQUEST") and "api key" in msg.lower():
        sys.exit(f"\nAPI request denied: {msg}\nCheck the key and that Places API is enabled + billing is on.")
    if status == "OVER_QUERY_LIMIT":
        print(f"  ! over query limit at {context}; backing off")
        time.sleep(3)
        return False
    print(f"  ! {context}: status={status} {msg}")
    return False


def text_search(query, key):
    """Yield place_ids for a query, paging up to MAX_PAGES."""
    params = {"query": query, "key": key}
    for page in range(MAX_PAGES):
        data = get_json(TEXT_SEARCH_URL, params)
        if not check_status(data, f"search '{query}'"):
            return
        for r in data.get("results", []):
            pid = r.get("place_id")
            if pid:
                yield pid
        token = data.get("next_page_token")
        if not token:
            return
        # next_page_token needs a short delay before it becomes valid
        time.sleep(2)
        params = {"pagetoken": token, "key": key}


def place_details(place_id, key):
    data = get_json(DETAILS_URL, {"place_id": place_id, "fields": DETAIL_FIELDS, "key": key})
    if not check_status(data, f"details {place_id}"):
        return None
    return data.get("result")


def main():
    key = get_key()
    leads = {}  # place_id -> row dict (dedupes automatically)

    for location in LOCATIONS:
        for query in QUERIES:
            term = f"{query} in {location}"
            print(f"Searching: {term}")
            for pid in text_search(term, key):
                if pid in leads:
                    continue
                time.sleep(REQUEST_PAUSE)
                d = place_details(pid, key)
                if not d:
                    continue
                if d.get("business_status") == "CLOSED_PERMANENTLY":
                    continue
                website = (d.get("website") or "").strip()
                has_website = "YES" if website else "NO"
                leads[pid] = {
                    "name": d.get("name", ""),
                    "phone": d.get("formatted_phone_number", ""),
                    "website": website,
                    "has_website": has_website,
                    "address": d.get("formatted_address", ""),
                    "rating": d.get("rating", ""),
                    "reviews": d.get("user_ratings_total", ""),
                    "maps_url": d.get("url", ""),
                    "priority": "HOT" if has_website == "NO" else "warm",
                }

    rows = list(leads.values())
    # HOT (no website) first, then by review count desc as a rough quality sort
    rows.sort(key=lambda r: (r["priority"] != "HOT", -(int(r["reviews"]) if str(r["reviews"]).isdigit() else 0)))

    fieldnames = ["name", "phone", "website", "has_website", "address",
                  "rating", "reviews", "maps_url", "priority"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    hot = sum(1 for r in rows if r["priority"] == "HOT")
    print("\n" + "-" * 48)
    print(f"Done. {len(rows)} businesses found, {hot} HOT (no website).")
    print(f"Written to {OUTPUT_FILE} — HOT leads are at the top.")
    print("Next: import leads.csv into the outreach tracker and start messaging.")


if __name__ == "__main__":
    main()
