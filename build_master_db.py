import json
import time
import os
import threading
import logging
import re
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from base64 import b64decode
from collections import defaultdict

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# ── 1. CONFIGURATION ─────────────────────────────────────────────────────────
# =============================================================================

INPUT_STATE_LIST = [
    'Andhra Pradesh', 'Telangana', 'Karnataka', 'Tamil Nadu'
]

# File paths
CONFIG_PATH = os.path.join("utils", "bms_cities_config.json")
DB_PATH = "master_screen_db.json"
LOG_PATH = "processed_screens.log"
DEBUG_DIR = "debug_logs"

# Settings
BMS_DRIVER_POOL_SIZE = 5
ENCRYPTION_KEY = "kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"

# Console Logging setup
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Ensure debug directory exists
os.makedirs(DEBUG_DIR, exist_ok=True)


# =============================================================================
# ── 2. DATABASE MANAGER ──────────────────────────────────────────────────────
# =============================================================================

class MasterScreenDB:
    """Thread-safe, append-only database manager for screen layouts."""
    def __init__(self, db_path=DB_PATH, log_path=LOG_PATH):
        self.db_path = db_path
        self.log_path = log_path
        self.lock = threading.Lock()
        self.data = self._load_json(db_path)
        self.processed = self._load_log(log_path)

    def _load_json(self, path):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _load_log(self, path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return set(line.strip() for line in f)
        return set()

    def is_processed(self, venue_code, screen_name):
        return f"{venue_code}_{screen_name}" in self.processed

    def add_screen(self, venue_code, screen_name, venue_name, capacity_data):
        key = f"{venue_code}_{screen_name}"
        with self.lock:
            self.data[key] = {
                "venue_code": venue_code,
                "venue_name": venue_name,
                "screen_name": screen_name,
                "total_capacity": capacity_data['total_capacity'],
                "categories": capacity_data['categories'],
                "last_updated": datetime.now().isoformat()
            }
            
            self.processed.add(key)
            with open(self.log_path, 'a', encoding='utf-8') as log:
                log.write(f"{key}\n")
            
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)


# =============================================================================
# ── 3. BROWSER & DECRYPTION UTILS ────────────────────────────────────────────
# =============================================================================

def _create_chrome_driver():
    ua = UserAgent()
    options = Options()
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--headless=new")
    options.add_argument("start-maximized")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-site-isolation-trials")
    options.add_argument("disable-csp")
    options.add_argument("--disable-blink-features=AutomationControlled")
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver

def dump_debug_file(filename, content):
    """Utility to safely write error logs/HTML."""
    filepath = os.path.join(DEBUG_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to write debug file {filename}: {e}")

def extract_initial_state_from_page(driver, url, identifier, is_venue_list=False):
    """Loads BMS page and uses Selenium to perfectly extract the JS object."""
    try:
        driver.get(url)
        time.sleep(3) 
        
        html = driver.page_source
        if "cloudflare" in html.lower() or "challenge-platform" in html.lower():
            dump_debug_file(f"{identifier}_cloudflare_blocked.html", html)
            logger.error(f"  🛑 Cloudflare block detected for {identifier}")
            return None

        # Poll the browser's JS engine until the API block populates
        for _ in range(15): # Try for 7.5 seconds
            try:
                state = driver.execute_script("return window.__INITIAL_STATE__;")
                if state:
                    if is_venue_list:
                        queries = state.get("fetchVenuesListingApi", {}).get("queries", {})
                        if any("getVenuesListingData" in k for k in queries.keys()):
                            return state
                    else:
                        queries = state.get("venueShowtimesFunctionalApi", {}).get("queries", {})
                        if any("getShowtimesByVenue" in k for k in queries.keys()):
                            return state
            except Exception:
                pass
            time.sleep(0.5)

        # If it times out, dump whatever state we have to debug
        dump_debug_file(f"{identifier}_timeout.html", driver.page_source)
        try:
            partial_state = driver.execute_script("return window.__INITIAL_STATE__;")
            dump_debug_file(f"{identifier}_partial_state.json", json.dumps(partial_state, indent=2))
        except:
            pass
            
        logger.error(f"  ⚠️ Timeout waiting for API data for {identifier}")
        return None

    except Exception as e:
        logger.error(f"  ❌ Exception loading page {url}: {e}")
        return None

def get_single_seat_layout(driver, venue_code, session_id):
    api_url = "https://services-in.bookmyshow.com/doTrans.aspx"
    js = (
        "var cb = arguments[0];"
        "var x = new XMLHttpRequest();"
        "x.open('POST', '%s', true);"
        "x.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');"
        "x.timeout = 15000;"
        "x.onload = function() { cb(x.responseText); };"
        "x.onerror = function() { cb(null); };"
        "x.ontimeout = function() { cb(null); };"
        "x.send('strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode=%s&lngTransactionIdentifier=0&strParam1=%s&strParam2=WEB&strParam5=Y&strFormat=json');"
    ) % (api_url, venue_code, session_id)

    try:
        driver.set_script_timeout(20)
        resp = driver.execute_async_script(js)
    except Exception as e:
        return None, str(e).split('\n')[0]

    if not resp: return None, "Empty response"
    data = json.loads(resp).get("BookMyShow", {})
    if data.get("blnSuccess") == "true":
        return data.get("strData"), None
    return None, data.get("strException", "")

def decrypt_data(enc):
    decoded = b64decode(enc)
    cipher = AES.new(ENCRYPTION_KEY.encode(), AES.MODE_CBC, iv=bytes(16))
    return unpad(cipher.decrypt(decoded), AES.block_size).decode()

def parse_layout_capacity(decrypted, price_map):
    header, rows_part = decrypted.split("||")
    rows = rows_part.split("|")

    cat_map = {}
    local_price_map = price_map.copy()
    last_price = 0.0

    for p in header.split("|"):
        parts = p.split(":")
        if len(parts) >= 3:
            cat_map[parts[1]] = parts[2]
            current_price = local_price_map.get(parts[2], 0.0)
            if current_price > 0: last_price = current_price
            elif last_price > 0: local_price_map[parts[2]] = last_price

    seats = {}
    for row in rows:
        if not row: continue
        parts = row.split(":")
        if len(parts) < 3: continue
        block = parts[3][0] if len(parts) > 3 else parts[2][0]
        area = cat_map.get(block)
        if not area: continue
        
        for seat in parts:
            if len(seat) < 2: continue
            status = seat[1]
            if seat[0] == block and status in ("1", "2"):
                seats[area] = seats.get(area, 0) + 1

    categories = {}
    total_capacity = 0
    for area, total in seats.items():
        total_capacity += total
        ac_code = next((code for code, label in cat_map.items() if label == area), "UNK")
        categories[area] = {
            "total_seats": total,
            "area_code": ac_code
        }

    return {"total_capacity": total_capacity, "categories": categories}


# =============================================================================
# ── 4. DISCOVERY & EXTRACTION LOGIC ──────────────────────────────────────────
# =============================================================================

def slugify_venue_name(name):
    name = name.lower()
    name = name.replace("&", "and")
    name = name.replace("'", "")
    name = re.sub(r'[^a-z0-9]+', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-')

def extract_venues_from_state(state_data):
    """Robust extraction of venues from the state JSON."""
    try:
        api_data = state_data.get("fetchVenuesListingApi", {}).get("queries", {})
        for key, val in api_data.items():
            if "getVenuesListingData" in key and val.get("data"):
                venues = val["data"].get("venues", [])
                if venues: return venues
    except: pass
    return []

def process_city_infrastructure(state_name, city_name, city_slug, db, city_counter_str):
    driver = None
    try:
        driver = _create_chrome_driver()
        
        # 1. Fetch Venue List for the City
        venue_list_url = f"https://in.bookmyshow.com/{city_slug}/venue-list"
        logger.info(f"  🏢 [DB Builder] {city_counter_str} Fetching {city_name}...")
        
        state_data = extract_initial_state_from_page(driver, venue_list_url, identifier=f"VenueList_{city_slug}", is_venue_list=True)
        
        if not state_data:
            logger.warning(f"    ⚠️ No state data for {city_name}")
            return

        # NEW EXTRACTION LOGIC FOR VENUE LIST PAGE
        venues = []
        try:
            # The structure for venue-list is usually inside fetchVenuesListingApi
            queries = state_data.get("fetchVenuesListingApi", {}).get("queries", {})
            for key, val in queries.items():
                if "getVenuesListingData" in key:
                    venues = val.get("data", {}).get("venues", [])
                    break
        except Exception as e:
            dump_debug_file(f"DEBUG_{city_slug}_keys.txt", str(list(state_data.keys())))
            logger.error(f"    ❌ Could not extract venues from {city_name}: {e}")

        if not venues:
            logger.info(f"    ⚠️ No venues found in {city_name}")
            return

        tomorrow = datetime.now() + timedelta(days=1)
        target_date_str = tomorrow.strftime("%Y%m%d")

        # 2. Iterate through every Venue
        for v in venues:
            venue_code = v.get("VenueCode")
            venue_name = v.get("VenueName")
            if not venue_code: continue

            venue_slug = slugify_venue_name(venue_name)
            # URL format for specific theatre schedule
            theatre_url = f"https://in.bookmyshow.com/cinemas/{city_slug}/{venue_slug}/buytickets/{venue_code}/{target_date_str}"
            
            # This uses the same driver, so it should be fast
            theatre_state = extract_initial_state_from_page(driver, theatre_url, identifier=f"Theatre_{venue_code}", is_venue_list=False)
            
            if not theatre_state:
                continue

            # 3. Extract Shows from the NEW Theatre Page API
            screens_map = defaultdict(list)
            
            # The payload you showed uses venueShowtimesFunctionalApi -> getShowtimesByVenue
            try:
                queries = theatre_state.get("venueShowtimesFunctionalApi", {}).get("queries", {})
                for key, val in queries.items():
                    if "getShowtimesByVenue" in key and val.get("data"):
                        events = val.get("data", {}).get("showDetailsTransformed", {}).get("Event", [])
                        for event in events:
                            for child in event.get("ChildEvents", []):
                                for show in child.get("ShowTimes", []):
                                    screen_name = show.get("ScreenName", "Main Screen")
                                    screens_map[screen_name].append(show)
            except Exception as e:
                logger.error(f"    ❌ Show extraction failed for {venue_code}: {e}")
                continue

            if not screens_map:
                continue

            # 4. Map screen and save to DB
            for screen_name, shows in screens_map.items():
                if db.is_processed(venue_code, screen_name): continue
                
                # Sort to find an available show
                shows.sort(key=lambda x: x.get("AvailStatus", "0") not in ("0", "2"), reverse=True)
                
                for show in shows:
                    sid = str(show.get("SessionId"))
                    if not sid: continue
                    
                    price_map = {c["PriceDesc"]: float(c["CurPrice"]) for c in show.get("Categories", [])}
                    
                    enc, err = get_single_seat_layout(driver, venue_code, sid)
                    if enc:
                        try:
                            decrypted = decrypt_data(enc)
                            cap_data = parse_layout_capacity(decrypted, price_map)
                            if cap_data['total_capacity'] > 0:
                                db.add_screen(venue_code, screen_name, venue_name, cap_data)
                                logger.info(f"    ✅ Mapped: {venue_name[:15]} | {screen_name} -> {cap_data['total_capacity']} seats")
                                break 
                        except: pass
    finally:
        if driver: driver.quit()

def run_master_builder(cities_list):
    db = MasterScreenDB()
    total_cities = len(cities_list)
    logger.info(f"\n🚀 Starting Master Screen DB Builder — {total_cities} cities, {BMS_DRIVER_POOL_SIZE} parallel workers")
    logger.info(f"🎯 Target Date: {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')} (Tomorrow)\n")

    def _process_wrapper(args):
        idx, (state, city_name, city_slug) = args
        counter_str = f"[{idx}/{total_cities}]"
        process_city_infrastructure(state, city_name, city_slug, db, counter_str)

    with ThreadPoolExecutor(max_workers=BMS_DRIVER_POOL_SIZE) as pool:
        futures = [
            pool.submit(_process_wrapper, (idx, city_info))
            for idx, city_info in enumerate(cities_list, 1)
        ]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass
                
    logger.info(f"\n🏁 Finished Building Master DB! Mapped {len(db.processed)} total screens.")


if __name__ == "__main__":
    if not os.path.exists(CONFIG_PATH):
        logger.error(f"❌ Config file missing at {CONFIG_PATH}. Exiting.")
        exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        bms_config = json.load(f)

    target_cities = [
        (s, c['name'], c['slug']) 
        for s in INPUT_STATE_LIST 
        for c in bms_config.get(s, [])
    ]

    if not target_cities:
        logger.warning("⚠️ No target cities found in config for the given states.")
    else:
        run_master_builder(target_cities)