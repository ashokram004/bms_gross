"""
Fetch all District.in venue details for every city across all Indian states.
One-time run script. All HTTP — no Selenium needed.

Output:  duplicate removal tools/district_all_venues.json
Resume:  Saves progress per state; re-run to resume from where it left off.

Usage:   python "duplicate removal tools/fetchDistrictVenues.py"
"""

import json
import os
import re
import time
import threading
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from fake_useragent import UserAgent

# ── Paths ──
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR      = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH   = os.path.join(ROOT_DIR, "utils", "district_cities_config.json")
OUTPUT_PATH   = os.path.join(SCRIPT_DIR, "district_all_venues.json")
PROGRESS_PATH = os.path.join(SCRIPT_DIR, "district_venues_progress.json")

# ── Settings ──
CITY_WORKERS     = 10     # parallel workers for city-level listing
VENUE_WORKERS    = 15     # parallel workers for venue detail pages
MAX_RATE         = 20     # max requests/second (across all workers)
REQUEST_TIMEOUT  = 15     # seconds per HTTP request


# =============================================================================
# ── RATE LIMITER ──────────────────────────────────────────────────────────────
# =============================================================================

class RateLimiter:
    def __init__(self, rate):
        self.min_interval = 1.0 / rate
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            if self._next_slot <= now:
                self._next_slot = now + self.min_interval
                return
            wait_until = self._next_slot
            self._next_slot = wait_until + self.min_interval
        wait = wait_until - time.monotonic()
        if wait > 0:
            time.sleep(wait)

limiter = RateLimiter(MAX_RATE)


# =============================================================================
# ── THREAD-LOCAL HTTP SESSION ─────────────────────────────────────────────────
# =============================================================================

_tl = threading.local()

def get_session():
    if not hasattr(_tl, 'session'):
        s = requests.Session()
        s.headers.update({
            'User-Agent': UserAgent().random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20, pool_maxsize=20,
            max_retries=requests.adapters.Retry(
                total=3, backoff_factor=1, status_forcelist=[502, 503, 504]
            ),
        )
        s.mount('https://', adapter)
        s.mount('http://', adapter)
        _tl.session = s
    return _tl.session


# =============================================================================
# ── HELPERS ───────────────────────────────────────────────────────────────────
# =============================================================================

def parse_next_data(html):
    """Extract __NEXT_DATA__ JSON from a District page."""
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    idx = html.find(marker)
    if idx < 0:
        return None
    start = idx + len(marker)
    end = html.find('</script>', start)
    if end < 0:
        return None
    try:
        return json.loads(html[start:end].strip())
    except json.JSONDecodeError:
        return None


def slugify(name):
    """Convert cinema name to URL-safe slug (lowercase, alphanumeric, dashes)."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9]+', '-', name)
    return name.strip('-')


# =============================================================================
# ── FETCH: CITY-LEVEL VENUE LIST ─────────────────────────────────────────────
# =============================================================================

def fetch_city_venues(city_slug):
    """GET cinemas-in-{city} → list of basic venue dicts."""
    url = f"https://www.district.in/movies/cinemas-in-{city_slug}"
    limiter.acquire()
    try:
        resp = get_session().get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 403:
            time.sleep(3)
            limiter.acquire()
            resp = get_session().get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []

        data = parse_next_data(resp.text)
        if not data:
            return []

        rails = (data.get('props', {}).get('pageProps', {}).get('data', {})
                 .get('serverState', {}).get('EDSResponse', {}).get('rails', []))

        venues = []
        for rail in rails:
            for item in rail.get('items', []):
                cd = item.get('ItemDetails', {}).get('CinemaData', {})
                if cd and cd.get('cinema_id'):
                    venues.append({
                        'cinema_id':  str(cd['cinema_id']),
                        'cinema_name': cd.get('cinema_name', ''),
                        'p_city_id':   cd.get('p_city_id'),
                        'logo':        cd.get('logo', ''),
                        'attributes':  cd.get('attributes', []),
                        'distance':    cd.get('distance'),
                    })
        return venues
    except Exception:
        return []


# =============================================================================
# ── FETCH: VENUE DETAIL PAGE ─────────────────────────────────────────────────
# =============================================================================

def fetch_venue_detail(cinema_id, cinema_name, city_slug):
    """GET the venue's dedicated page → rich dict with address, lat, lon, etc."""
    name_slug = slugify(cinema_name)
    url = f"https://www.district.in/movies/{name_slug}-in-{city_slug}-CD{cinema_id}"

    limiter.acquire()
    try:
        resp = get_session().get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 403:
            time.sleep(3)
            limiter.acquire()
            resp = get_session().get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None

        data = parse_next_data(resp.text)
        if not data:
            return None

        page_data = data.get('props', {}).get('pageProps', {}).get('data', {})
        server_state = page_data.get('serverState', {})

        # Cinema data lives under serverState["{cinema_id}"].meta.cinema
        cinema_state = server_state.get(str(cinema_id))
        if not cinema_state:
            # Fallback: find any key that has 'meta' inside
            for key in server_state:
                val = server_state[key]
                if isinstance(val, dict) and 'meta' in val:
                    cinema_state = val
                    break

        if not cinema_state:
            return None

        cinema = cinema_state.get('meta', {}).get('cinema', {})
        if not cinema:
            return None

        # Extract amenities safely (field can be None)
        raw_amenities = cinema.get('amenities') or []
        amenities = [
            a.get('name', '') for a in raw_amenities
            if isinstance(a, dict) and a.get('status') == 1
        ]

        return {
            'id':              cinema.get('id'),
            'pid':             cinema.get('pid'),
            'name':            cinema.get('name', ''),
            'label':           cinema.get('label', ''),
            'address':         cinema.get('address', ''),
            'pincode':         cinema.get('pincode', ''),
            'lat':             cinema.get('lat'),
            'lon':             cinema.get('lon'),
            'city_id':         cinema.get('cityId'),
            'city_name':       page_data.get('cityName', ''),
            'city_label':      page_data.get('cityLabel', ''),
            'chain_key':       cinema.get('chainKey', ''),
            'content_id':      cinema.get('contentId'),
            'fnb':             cinema.get('fnb'),
            'm_ticket':        cinema.get('mTkt'),
            'b_code':          cinema.get('bCode', ''),
            'logo_detail':     cinema.get('cinemaLogoUrl', ''),
            'is_pass_enabled': cinema.get('isPassEnabled'),
            'session_count':   cinema.get('sessionCount'),
            'amenities':       amenities,
        }
    except Exception:
        return None


# =============================================================================
# ── PROGRESS / OUTPUT HELPERS ─────────────────────────────────────────────────
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
        "platform": "district",
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
    unique_ids = set()
    cities_with = 0
    cities_without = 0
    details_ok = 0
    details_fail = 0

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
                unique_ids.add(v.get('cinema_id', ''))
                if v.get('detail_fetched'):
                    details_ok += 1
                else:
                    details_fail += 1

    return {
        'total_states':          len(output['states']),
        'total_cities_processed': total_cities,
        'total_venue_entries':    total_venues,
        'total_unique_venues':    len(unique_ids),
        'cities_with_venues':     cities_with,
        'cities_without_venues':  cities_without,
        'venue_details_fetched':  details_ok,
        'venue_details_failed':   details_fail,
    }


# =============================================================================
# ── MAIN ──────────────────────────────────────────────────────────────────────
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
    print(f"  District Venue Fetcher")
    print(f"  {total_states} states, {total_cities} cities")
    print(f"  Already completed: {len(completed_states)} states")
    print(f"  City workers: {CITY_WORKERS}, Venue workers: {VENUE_WORKERS}")
    print(f"  Rate limit: {MAX_RATE} req/s")
    print(f"{'='*60}\n")

    # Global cache: avoid re-fetching venue details across states
    global_venue_details = {}   # cinema_id → detail dict

    for state_idx, (state_name, cities) in enumerate(config.items(), 1):
        if state_name in completed_states:
            print(f"[{state_idx}/{total_states}] {state_name} — skipped (already done)")
            continue

        print(f"[{state_idx}/{total_states}] {state_name} ({len(cities)} cities)")
        t_state = time.time()

        # ── Phase 1: Fetch city-level cinema lists ──
        city_venue_map = {}   # city_name → { slug, venues }

        with ThreadPoolExecutor(max_workers=CITY_WORKERS) as executor:
            future_map = {}
            for ci in cities:
                f = executor.submit(fetch_city_venues, ci['slug'])
                future_map[f] = ci

            for future in as_completed(future_map):
                ci = future_map[future]
                venues = future.result()
                city_venue_map[ci['name']] = {'slug': ci['slug'], 'venues': venues}
                if venues:
                    print(f"  {ci['name']}: {len(venues)} venues")

        # ── Phase 2: Collect unique cinema_ids needing detail fetch ──
        unique_cinemas = {}   # cinema_id → (cinema_name, city_slug)
        for city_data in city_venue_map.values():
            for v in city_data['venues']:
                cid = v['cinema_id']
                if cid not in global_venue_details and cid not in unique_cinemas:
                    unique_cinemas[cid] = (v['cinema_name'], city_data['slug'])

        already_cached = sum(
            1 for city_data in city_venue_map.values()
            for v in city_data['venues']
            if v['cinema_id'] in global_venue_details
        )
        if already_cached:
            print(f"  {already_cached} venue details cached from prior states")

        if unique_cinemas:
            print(f"  Fetching details for {len(unique_cinemas)} unique venues...")
            with ThreadPoolExecutor(max_workers=VENUE_WORKERS) as executor:
                future_map = {}
                for cid, (cname, cslug) in unique_cinemas.items():
                    f = executor.submit(fetch_venue_detail, cid, cname, cslug)
                    future_map[f] = cid

                done_count = 0
                ok_count = 0
                for future in as_completed(future_map):
                    cid = future_map[future]
                    detail = future.result()
                    done_count += 1
                    if detail:
                        global_venue_details[cid] = detail
                        ok_count += 1
                    if done_count % 50 == 0:
                        print(f"    Details: {done_count}/{len(unique_cinemas)} "
                              f"({ok_count} ok)")

            print(f"  Got details for {ok_count}/{len(unique_cinemas)} venues")

        # ── Phase 3: Assemble enriched output for this state (preserve existing venues) ──
        existing_state = output.get('states', {}).get(state_name, {})
        state_output = {"cities": {}}
        for city_name, city_info in city_venue_map.items():
            # Start with existing venues for this city (keyed by cinema_id)
            existing_city = existing_state.get('cities', {}).get(city_name, {})
            venue_index = {v['cinema_id']: v for v in existing_city.get('venues', []) if v.get('cinema_id')}

            # Add/update with newly fetched venues
            for v in city_info['venues']:
                cid = v['cinema_id']
                detail = global_venue_details.get(cid)
                entry = {
                    'cinema_id':      cid,
                    'cinema_name':    v['cinema_name'],
                    'p_city_id':      v.get('p_city_id'),
                    'logo':           v.get('logo', ''),
                    'attributes':     v.get('attributes', []),
                    'distance':       v.get('distance'),
                    'detail_fetched': detail is not None,
                }
                if detail:
                    entry.update({
                        'address':         detail.get('address', ''),
                        'pincode':         detail.get('pincode', ''),
                        'lat':             detail.get('lat'),
                        'lon':             detail.get('lon'),
                        'city_id':         detail.get('city_id'),
                        'city_label':      detail.get('city_label', ''),
                        'chain_key':       detail.get('chain_key', ''),
                        'content_id':      detail.get('content_id'),
                        'pid':             detail.get('pid'),
                        'fnb':             detail.get('fnb'),
                        'm_ticket':        detail.get('m_ticket'),
                        'b_code':          detail.get('b_code', ''),
                        'logo_detail':     detail.get('logo_detail', ''),
                        'is_pass_enabled': detail.get('is_pass_enabled'),
                        'session_count':   detail.get('session_count'),
                        'amenities':       detail.get('amenities', []),
                    })
                venue_index[cid] = entry

            merged = list(venue_index.values())
            state_output['cities'][city_name] = {
                'slug':        city_info['slug'],
                'venue_count': len(merged),
                'venues':      merged,
            }

        # ── Save ──
        output['states'][state_name] = state_output
        output['fetched_at'] = datetime.now().isoformat()
        output['stats'] = compute_stats(output)

        save_output(output)
        completed_states.add(state_name)
        progress['completed_states'] = list(completed_states)
        save_progress(progress)

        elapsed = time.time() - t_state
        vc = sum(c['venue_count'] for c in state_output['cities'].values())
        cw = sum(1 for c in state_output['cities'].values() if c['venue_count'] > 0)
        print(f"  ✓ {state_name}: {vc} venue entries, "
              f"{cw}/{len(state_output['cities'])} cities with venues ({elapsed:.0f}s)\n")

    # ── Cleanup on full completion ──
    if len(completed_states) == total_states:
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)
        s = output['stats']
        print(f"{'='*60}")
        print(f"  ALL DONE!")
        print(f"  States:         {s['total_states']}")
        print(f"  Cities:         {s['total_cities_processed']}")
        print(f"  Venue entries:  {s['total_venue_entries']}")
        print(f"  Unique venues:  {s['total_unique_venues']}")
        print(f"  Details OK:     {s['venue_details_fetched']}")
        print(f"  Details failed: {s['venue_details_failed']}")
        print(f"  Output: {OUTPUT_PATH}")
        print(f"{'='*60}")


if __name__ == '__main__':
    main()
