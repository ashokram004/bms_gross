"""
Fetch all BookMyShow venue details for every city across all Indian states.
One-time run script. Uses Selenium (BMS is Cloudflare-protected).

Each city requires a fresh Chrome driver (Cloudflare tracks sessions).
Multiple drivers run in parallel for speed.

Output:  duplicate removal tools/bms_all_venues.json
Resume:  Saves progress per state; re-run to resume from where it left off.

Usage:   python "duplicate removal tools/fetchBmsVenues.py"
"""

import json
import os
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent

# ── Paths ──
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR      = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH   = os.path.join(ROOT_DIR, "utils", "bms_cities_config.json")
OUTPUT_PATH   = os.path.join(SCRIPT_DIR, "bms_all_venues.json")
PROGRESS_PATH = os.path.join(SCRIPT_DIR, "bms_venues_progress.json")

# ── Settings ──
BMS_WORKERS    = 5      # parallel Selenium drivers
PAGE_WAIT_MAX  = 10     # max seconds to wait for venue data to load
DRIVER_TIMEOUT = 20     # Selenium page load timeout
MAX_RETRIES    = 2      # retries per city on failure


# =============================================================================
# ── JS SNIPPET: Extract venues from window.__INITIAL_STATE__ ─────────────────
# =============================================================================

JS_EXTRACT_VENUES = """
var state = window.__INITIAL_STATE__;
if (!state) return null;
var api = state.fetchVenuesListingApi;
if (!api || !api.queries) return null;
var keys = Object.keys(api.queries);
for (var i = 0; i < keys.length; i++) {
    if (keys[i].indexOf('getVenuesListingData') >= 0) {
        var q = api.queries[keys[i]];
        if (q.status === 'fulfilled' && q.data) {
            return q.data.venues || [];
        }
        return null;
    }
}
return [];
"""


# =============================================================================
# ── SELENIUM DRIVER FACTORY ──────────────────────────────────────────────────
# =============================================================================

def make_driver():
    """Create a fresh stealth headless Chrome driver."""
    ua = UserAgent()
    options = Options()
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--headless=new")
    options.add_argument("start-maximized")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-site-isolation-trials")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(DRIVER_TIMEOUT)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', "
                  "{get: () => undefined});"
    })
    return driver


# =============================================================================
# ── FETCH VENUES FOR A SINGLE CITY ──────────────────────────────────────────
# =============================================================================

def fetch_bms_city(city_slug):
    """Load venue-list page via Selenium, extract all venues.
    Returns list of venue dicts (raw from BMS __INITIAL_STATE__).
    Uses a fresh driver (required — Cloudflare blocks reused sessions).
    """
    for attempt in range(MAX_RETRIES + 1):
        driver = None
        try:
            driver = make_driver()
            driver.get(f'https://in.bookmyshow.com/{city_slug}/venue-list')

            # Poll until fetchVenuesListingApi is populated (or timeout)
            venues = None
            for _ in range(PAGE_WAIT_MAX * 2):
                time.sleep(0.5)
                try:
                    result = driver.execute_script(JS_EXTRACT_VENUES)
                    if result is not None:
                        venues = result
                        break
                except Exception:
                    pass

            return venues if venues is not None else []

        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(2)
            else:
                return []
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


# =============================================================================
# ── PROGRESS / OUTPUT HELPERS ────────────────────────────────────────────────
# =============================================================================

def load_progress():
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed_states": []}

def save_progress(progress):
    with open(PROGRESS_PATH, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2)

def load_output():
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "platform": "bms",
        "fetched_at": "",
        "stats": {},
        "states": {},
    }

def save_output(output):
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

def compute_stats(output):
    total_cities = 0
    total_venues = 0
    unique_codes = set()
    cities_with = 0
    cities_without = 0

    for state_data in output['states'].values():
        for city_data in state_data['cities'].values():
            total_cities += 1
            vlist = city_data.get('venues', [])
            total_venues += len(vlist)
            if vlist:
                cities_with += 1
            else:
                cities_without += 1
            for v in vlist:
                unique_codes.add(v.get('VenueCode', ''))

    return {
        'total_states':           len(output['states']),
        'total_cities_processed': total_cities,
        'total_venue_entries':    total_venues,
        'total_unique_venues':    len(unique_codes),
        'cities_with_venues':     cities_with,
        'cities_without_venues':  cities_without,
    }


# =============================================================================
# ── MAIN ─────────────────────────────────────────────────────────────────────
# =============================================================================

def main():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    progress = load_progress()
    output   = load_output()
    completed_states = set(progress.get("completed_states", []))
    total_states = len(config)
    total_cities = sum(len(v) for v in config.values())

    print(f"{'='*60}")
    print(f"  BMS Venue Fetcher (Selenium)")
    print(f"  {total_states} states, {total_cities} cities")
    print(f"  Already completed: {len(completed_states)} states")
    print(f"  Parallel drivers: {BMS_WORKERS}")
    print(f"{'='*60}\n")

    # Global slug cache: avoid re-fetching if same slug appears in multiple states
    fetched_slugs = {}   # slug → venue list

    for state_idx, (state_name, cities) in enumerate(config.items(), 1):
        if state_name in completed_states:
            print(f"[{state_idx}/{total_states}] {state_name} — skipped (already done)")
            continue

        print(f"[{state_idx}/{total_states}] {state_name} ({len(cities)} cities)")
        t_state = time.time()

        # Separate cached slugs from ones we need to fetch
        to_fetch = []
        cached_results = {}
        for ci in cities:
            slug = ci['slug']
            if slug in fetched_slugs:
                cached_results[ci['name']] = (slug, fetched_slugs[slug])
            else:
                to_fetch.append(ci)

        if cached_results:
            print(f"  {len(cached_results)} cities cached from prior states")

        # Fetch uncached cities in parallel
        fresh_results = {}
        if to_fetch:
            with ThreadPoolExecutor(max_workers=BMS_WORKERS) as executor:
                future_map = {}
                for ci in to_fetch:
                    f = executor.submit(fetch_bms_city, ci['slug'])
                    future_map[f] = ci

                done = 0
                for future in as_completed(future_map):
                    ci = future_map[future]
                    venues = future.result()
                    fresh_results[ci['name']] = (ci['slug'], venues)
                    fetched_slugs[ci['slug']] = venues
                    done += 1

                    if venues:
                        print(f"  [{done}/{len(to_fetch)}] "
                              f"{ci['name']}: {len(venues)} venues")
                    elif done % 25 == 0:
                        print(f"  [{done}/{len(to_fetch)}] processing...")

        # Merge and assemble state output
        all_results = {**cached_results, **fresh_results}
        state_output = {"cities": {}}
        state_venue_count = 0
        cities_with = 0
        cities_without = 0

        for city_name, (slug, venues) in all_results.items():
            state_output['cities'][city_name] = {
                'slug':        slug,
                'venue_count': len(venues),
                'venues':      venues,
            }
            state_venue_count += len(venues)
            if venues:
                cities_with += 1
            else:
                cities_without += 1

        # Save state
        output['states'][state_name] = state_output
        output['fetched_at'] = datetime.now().isoformat()
        output['stats'] = compute_stats(output)

        save_output(output)
        completed_states.add(state_name)
        progress['completed_states'] = list(completed_states)
        save_progress(progress)

        elapsed = time.time() - t_state
        print(f"  ✓ {state_name}: {state_venue_count} venues, "
              f"{cities_with} with / {cities_without} without ({elapsed:.0f}s)\n")

    # Cleanup on full completion
    if len(completed_states) == total_states:
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)
        s = output['stats']
        print(f"{'='*60}")
        print(f"  ALL DONE!")
        print(f"  States:          {s['total_states']}")
        print(f"  Cities:          {s['total_cities_processed']}")
        print(f"  Venue entries:   {s['total_venue_entries']}")
        print(f"  Unique venues:   {s['total_unique_venues']}")
        print(f"  Cities w/ venues: {s['cities_with_venues']}")
        print(f"  Output: {OUTPUT_PATH}")
        print(f"{'='*60}")


if __name__ == '__main__':
    main()
