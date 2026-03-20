import json
import os
import sys
import time
import random
import shutil
import threading
import requests
from datetime import datetime, timedelta
from base64 import b64decode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from openpyxl import Workbook
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.generatePremiumCityImageReport import generate_premium_city_image_report
from utils.generateHybridCityHTMLReport import generate_hybrid_city_html_report
from utils.sendReportEmail import send_collection_report

# =============================================================================
# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# =============================================================================

SHOW_DATE = "2026-03-19"

DISTRICT_URL_TEMPLATE = (
    "https://www.district.in/movies/ustaad-bhagat-singh-movie-tickets-in-{city}-MV161614"
    "?frmtid=tvqjmjqme&fromdate=" + SHOW_DATE
)
BMS_URL_TEMPLATE = (
    "https://in.bookmyshow.com/movies/{city}/ustaad-bhagat-singh/buytickets/ET00339939/20260319"
)

DISTRICT_CITIES = [
    "hyderabad"
]
BMS_CITIES = [
    "hyderabad"
]

BMS_KEY      = "kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"
BOOKED_CODES = {"2"}

# ── PERFORMANCE TUNING ──
DISTRICT_CITY_WORKERS = 12    # parallel city workers for District (pure HTTP)
BMS_DRIVER_POOL_SIZE  = 12    # cities processed in parallel (each gets a fresh Chrome)
BMS_VENUE_WORKERS     = 5     # concurrent venue workers per city (HTTP seat layout calls)
DISTRICT_RATE         = 5     # max requests/second to district.in
BMS_MAX_CONCURRENT    = 50    # semaphore: max simultaneous BMS seat-layout API calls
BMS_429_MAX_RETRIES   = 10    # per-request: max retries on HTTP 429 / app-level rate limit
BMS_SOFT_RETRIES      = 3     # per-request: quick retries before escalating to backoff

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9", "en-GB,en;q=0.9", "en-IN,en;q=0.9",
    "en-AU,en;q=0.9", "en-CA,en;q=0.9", "en-NZ,en;q=0.9",
]

# =============================================================================
# ── HELPERS ───────────────────────────────────────────────────────────────────
# =============================================================================

def extract_movie_name_from_url(url):
    try:
        if '/movies/' in url and '/buytickets/' in url:
            parts      = url.split('/movies/')[1].split('/buytickets/')[0].split('/')
            movie_slug = parts[-1] if len(parts) > 1 else parts[0]
            return movie_slug.replace('-', ' ').title()
        if '/movies/' in url and '-movie-tickets-in-' in url:
            movie_slug = url.split('/movies/')[1].split('-movie-tickets-in-')[0]
            return movie_slug.replace('-', ' ').title()
    except Exception as e:
        print(f"Could not extract movie name from URL: {e}")
    return "Movie Collection"


# =============================================================================
# ── HTTP SESSION (thread-local, connection-pooled) ────────────────────────────
# =============================================================================

_thread_local = threading.local()

def get_http_session():
    if not hasattr(_thread_local, 'session'):
        s = requests.Session()
        ua = UserAgent()
        s.headers.update({
            'User-Agent': ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5,
                                                 status_forcelist=[502, 503, 504]),
        )
        s.mount('https://', adapter)
        s.mount('http://', adapter)
        _thread_local.session = s
    return _thread_local.session


# =============================================================================
# ── SELENIUM (Chrome driver factory for BMS — fresh per city, Cloudflare bypass) ───────
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
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--mute-audio")
    options.add_argument("--no-first-run")
    options.add_argument("--safebrowsing-disable-auto-update")
    options.page_load_strategy = 'normal'
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setBlockedURLs", {
        "urls": [
            "*google*", "*facebook*", "*branch.io*", "*sentry*",
            "*analytics*", "*doubleclick*", "*gtag*", "*gtm*",
            "*.woff", "*.woff2", "*.ttf", "*.otf",
            "*adservice*", "*adsense*", "*criteo*", "*taboola*",
        ]
    })
    return driver


def district_gmt_to_ist(dt_str):
    gmt = datetime.fromisoformat(dt_str)
    ist = gmt + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d %H:%M")

def normalize_bms_time(show_date, show_time):
    dt = datetime.strptime(f"{show_date} {show_time}", "%Y-%m-%d %I:%M %p")
    return dt.strftime("%Y-%m-%d %H:%M")

def build_seat_signature(seat_map):
    return "|".join(str(c) for c in sorted(seat_map.values()))


# =============================================================================
# ── RATE LIMITER (thread-safe) ────────────────────────────────────────────────
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
        sleep_time = wait_until - time.monotonic()
        if sleep_time > 0:
            time.sleep(sleep_time)


district_limiter = RateLimiter(DISTRICT_RATE)


# =============================================================================
# ── PROXY POOL (optional IP rotation for BMS) ────────────────────────────────
# =============================================================================
# Load proxies from BMS_PROXIES env var (comma-separated) or utils/proxies.txt
# Each BMS HTTP session gets a different proxy → different source IP to BMS
# Supports http://, https://, socks5:// (for SOCKS5: pip install pysocks)

_proxy_pool = []
_proxy_idx  = 0
_proxy_lock = threading.Lock()

def _load_proxies():
    global _proxy_pool
    env_proxies = os.environ.get("BMS_PROXIES", "").strip()
    if env_proxies:
        _proxy_pool = [p.strip() for p in env_proxies.split(",") if p.strip()]
    if not _proxy_pool:
        proxy_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils", "proxies.txt")
        if os.path.exists(proxy_file):
            with open(proxy_file, encoding="utf-8") as f:
                _proxy_pool = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if _proxy_pool:
        print(f"🌐 Loaded {len(_proxy_pool)} proxies for BMS IP rotation")

def _next_proxy():
    global _proxy_idx
    if not _proxy_pool:
        return None
    with _proxy_lock:
        proxy = _proxy_pool[_proxy_idx % len(_proxy_pool)]
        _proxy_idx += 1
    return proxy


# =============================================================================
# ── BMS ADAPTIVE THROTTLE (global, thread-safe) ──────────────────────────────
# =============================================================================
# Shared across ALL BMS workers.  Two mechanisms:
#   1. Semaphore:  caps concurrent BMS API calls (prevents burst overload)
#   2. Adaptive delay: increases on 429, decays on success (self-tuning pace)
# Jitter on delay prevents thundering-herd retries after a 429 wave.

class BmsThrottle:
    def __init__(self, max_concurrent, max_delay=20.0):
        self._sem          = threading.Semaphore(max_concurrent)
        self._lock         = threading.Lock()
        self._delay        = 0.0
        self._max_delay    = max_delay
        self._last_429     = 0.0
        self._total_reqs   = 0
        self._total_429s   = 0
        self._success_run  = 0   # consecutive successes since last 429

    def acquire(self):
        """Call before each BMS API request. Blocks if too many concurrent."""
        self._sem.acquire()
        with self._lock:
            d = self._delay
            self._total_reqs += 1
        if d > 0:
            time.sleep(d * random.uniform(0.75, 1.25))  # ±25% jitter

    def release(self):
        """Call after each BMS API request completes."""
        self._sem.release()

    def report_429(self):
        """Called on HTTP 429 or app-level rate limit. Increases global delay."""
        with self._lock:
            self._total_429s += 1
            self._last_429 = time.monotonic()
            self._success_run = 0
            old = self._delay
            self._delay = min(
                max(0.25, self._delay * 2) if self._delay >= 0.1 else 0.25,
                self._max_delay
            )
            if int(self._delay * 10) != int(old * 10):
                print(f"      🔻 [Throttle] 429 #{self._total_429s} — global delay {old:.1f}s → {self._delay:.1f}s")

    def report_success(self):
        """Called on successful response. Gradually reduces delay."""
        with self._lock:
            if self._delay > 0:
                self._success_run += 1
                if self._success_run >= 10:
                    self._delay = max(0, self._delay * 0.5)
                    self._success_run = 0
                    if self._delay < 0.05:
                        self._delay = 0

    @property
    def stats(self):
        with self._lock:
            return f"reqs={self._total_reqs}, 429s={self._total_429s}, delay={self._delay:.2f}s"


bms_throttle = BmsThrottle(BMS_MAX_CONCURRENT)

# Global BMS retry queue — shows that fail after max retries get a second chance
_bms_retry_queue = []
_bms_retry_lock  = threading.Lock()


# =============================================================================
# ── DISTRICT ──────────────────────────────────────────────────────────────────
# =============================================================================

def get_district_seat_layout_http(cinema_id, session_id):
    """Direct HTTP POST for District seat layout API — no Selenium needed."""
    api_url = "https://www.district.in/gw/consumer/movies/v1/select-seat"
    params  = {
        "version": "3", "site_id": "1", "channel": "mweb",
        "child_site_id": "1", "platform": "district",
    }
    payload = {"cinemaId": int(cinema_id), "sessionId": str(session_id)}
    headers = {
        "Content-Type": "application/json",
        "x-guest-token": str(random.randint(1, 9999999999)),
        "Origin": "https://www.district.in",
        "Referer": "https://www.district.in/",
    }
    try:
        session = get_http_session()
        resp = session.post(api_url, params=params, json=payload,
                            headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def district_process_venue_http(cin, city_name):
    """Processes a single District venue via HTTP — no Selenium driver needed.
    Uses global _global_district_sids set to skip already-processed SIDs across all workers.
    """
    results = []
    try:
        venue = cin['entityName']
        for s in cin.get('sessions', []):
            sid = str(s.get('sid', ''))
            cid = s.get('cid')

            # Check if SID already processed (thread-safe global check)
            with _global_district_sids_lock:
                if sid in _global_district_sids:
                    continue
                _global_district_sids.add(sid)

            code_to_label  = {}
            default_prices = {}
            for a in s.get('areas', []):
                code_to_label[a['code']]  = a['label']
                default_prices[a['code']] = float(a['price'])

            b_gross, p_gross, b_tkts, t_tkts = 0, 0, 0, 0
            seat_map        = defaultdict(int)
            label_price_map = {}
            layout_res      = None

            if cid:
                layout_res = get_district_seat_layout_http(cid, sid)

            if layout_res and 'seatLayout' in layout_res:
                for area in layout_res['seatLayout'].get('colAreas', {}).get('objArea', []):
                    area_code = area.get('AreaCode')
                    label     = code_to_label.get(area_code, area_code)
                    price     = float(area.get('AreaPrice') or default_prices.get(area_code, 0))
                    label_price_map[label] = price
                    for row in area.get('objRow', []):
                        for seat in row.get('objSeat', []):
                            status = seat.get('SeatStatus')
                            t_tkts += 1; p_gross += price
                            seat_map[label] += 1
                            if status != '0' and status != 0:
                                b_tkts += 1; b_gross += price
            else:
                for a in s.get('areas', []):
                    tot, av, pr = a['sTotal'], a['sAvail'], a['price']
                    bk = tot - av
                    seat_map[a['label']]       = tot
                    label_price_map[a['label']] = float(pr)
                    b_tkts += bk; t_tkts += tot
                    b_gross += bk * pr; p_gross += tot * pr

            price_seat_map  = defaultdict(int)
            price_seat_list = []
            for label, count in seat_map.items():
                pr = label_price_map.get(label, 0.0)
                price_seat_map[float(pr)] += count
                price_seat_list.append((float(pr), count))

            occ             = round((b_tkts / t_tkts) * 100, 2) if t_tkts else 0
            normalized_time = district_gmt_to_ist(s['showTime'])

            results.append({
                "source":               "district",
                "sid":                  sid,
                "city":                 city_name,
                "venue":                venue,
                "cinema_id":            str(cid) if cid else "",
                "showTime":             s['showTime'],
                "normalized_show_time": normalized_time,
                "seat_category_map":    dict(seat_map),
                "price_seat_map":       dict(price_seat_map),
                "price_seat_signature": sorted(price_seat_list),
                "seat_signature":       build_seat_signature(seat_map),
                "total_tickets":        abs(t_tkts),
                "booked_tickets":       min(abs(b_tkts), abs(t_tkts)),
                "total_gross":          abs(p_gross),
                "booked_gross":         min(abs(int(b_gross)), abs(int(p_gross))),
                "occupancy":            min(100, abs(occ)),
                "is_fallback":          False,
            })
    except Exception as e:
        print(f"❌ [District][{city_name}] Venue worker error: {e}")
    return results


def fetch_district_city(city_name, city_slug, city_counter_str):
    """
    Fetches all District data for one city via HTTP — no Selenium needed.
    Step 1: HTTP GET page to extract __NEXT_DATA__ JSON.
    Step 2: Process each venue's shows (seat layout via HTTP POST).
    """
    url = DISTRICT_URL_TEMPLATE.format(city=city_slug)

    cinemas = []
    for attempt in range(2):
        try:
            district_limiter.acquire()
            session = get_http_session()
            resp    = session.get(url, timeout=15)

            if resp.status_code == 403 and attempt == 0:
                time.sleep(15)
                if hasattr(_thread_local, 'session'):
                    delattr(_thread_local, 'session')
                continue

            if resp.status_code != 200:
                print(f"   ⚠️  [District] {city_counter_str} {city_name:<15} — HTTP {resp.status_code}")
                return []
            html = resp.text

            marker = 'id="__NEXT_DATA__"'
            idx    = html.find(marker)
            if idx == -1:
                return []

            start    = html.find('>', idx) + 1
            end      = html.find('</script>', start)
            data     = json.loads(html[start:end])
            sessions = data['props']['pageProps']['data']['serverState']['movieSessions']
            if not sessions:
                return []
            key     = list(sessions.keys())[0]
            cinemas = sessions[key].get('arrangedSessions', [])
            break
        except Exception as e:
            print(f"   ❌ [District] {city_counter_str} {city_name:<15} — Error: {e}")
            return []

    if not cinemas:
        return []

    city_results = []
    for cin in cinemas:
        results = district_process_venue_http(cin, city_name)
        city_results.extend(results)

    gross = sum(r['booked_gross'] for r in city_results)
    if city_results:
        print(f"   ✅ [District] {city_counter_str} {city_name:<15} | Shows: {len(city_results):<3} | Gross: ₹{gross:<10,}")
    return city_results


def run_district(city_pairs):
    """
    Main District runner. Processes cities in PARALLEL with DISTRICT_CITY_WORKERS threads.
    """
    all_results = []
    total       = len(city_pairs)
    completed   = [0]
    lock        = threading.Lock()
    print(f"\n🚀 [District] Starting — {total} cities, {DISTRICT_CITY_WORKERS} parallel workers, {DISTRICT_RATE} req/sec\n")

    def _wrapped(idx, city_name, city_slug):
        results = fetch_district_city(city_name, city_slug, f"[{idx}/{total}]")
        with lock:
            completed[0] += 1
            if completed[0] % 20 == 0:
                print(f"   📊 [District] Progress: {completed[0]}/{total} cities done")
        return results

    with ThreadPoolExecutor(max_workers=DISTRICT_CITY_WORKERS) as executor:
        futures = {
            executor.submit(_wrapped, idx, city_name, city_slug): city_name
            for idx, (city_name, city_slug) in enumerate(city_pairs, 1)
        }
        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception as e:
                print(f"❌ [District] City worker error: {e}")

    print(f"\n✅ [District] Done — {len(all_results)} total shows across {total} cities.")
    return all_results


# =============================================================================
# ── BMS ───────────────────────────────────────────────────────────────────────
# =============================================================================

def extract_initial_state_from_page(driver, url):
    """Load BMS page with fresh driver and parse __INITIAL_STATE__ from SSR HTML."""
    try:
        driver.get(url)
        html = driver.page_source
        if len(html) < 10000 and "Cloudflare" in html:
            return None
        marker = "window.__INITIAL_STATE__"
        start  = html.find(marker)
        if start == -1:
            return None
        start = html.find("{", start)
        brace_count = 0; end = start
        while end < len(html):
            if html[end] == "{": brace_count += 1
            elif html[end] == "}": brace_count -= 1
            if brace_count == 0: break
            end += 1
        return json.loads(html[start:end + 1])
    except Exception:
        return None


def extract_venues(state):
    if not state:
        return []
    try:
        sbe       = state.get("showtimesByEvent")
        if not sbe: return []
        date_code = sbe.get("currentDateCode")
        if not date_code: return []
        widgets   = sbe["showDates"][date_code]["dynamic"]["data"]["showtimeWidgets"]
        for w in widgets:
            if w.get("type") == "groupList":
                for g in w["data"]:
                    if g.get("type") == "venueGroup":
                        return g["data"]
    except Exception:
        pass
    return []


def decrypt_data(enc):
    try:
        decoded = b64decode(enc)
        cipher  = AES.new(BMS_KEY.encode(), AES.MODE_CBC, iv=bytes(16))
        return unpad(cipher.decrypt(decoded), AES.block_size).decode()
    except:
        return None

def calculate_bms_collection(decrypted, price_map):
    header, rows_part = decrypted.split("||")
    rows = rows_part.split("|")

    cat_map         = {}
    local_price_map = price_map.copy()
    last_price      = 0.0

    for p in header.split("|"):
        parts = p.split(":")
        if len(parts) >= 3:
            cat_map[parts[1]] = parts[2]
            current_price = local_price_map.get(parts[2], 0.0)
            if current_price > 0:   last_price = current_price
            elif last_price > 0:    local_price_map[parts[2]] = last_price

    seats, booked = {}, {}
    for row in rows:
        if not row: continue
        parts = row.split(":")
        if len(parts) < 3: continue
        block = parts[3][0] if len(parts) > 3 else parts[2][0]
        area  = cat_map.get(block)
        if not area: continue
        for seat in parts:
            if len(seat) < 2: continue
            status = seat[1]
            if seat[0] == block and status in ("1", "2"):
                seats[area] = seats.get(area, 0) + 1
            if seat[0] == block and status in BOOKED_CODES:
                booked[area] = booked.get(area, 0) + 1

    t_tkts, b_tkts, t_gross, b_gross = 0, 0, 0, 0
    for area, total in seats.items():
        bk = booked.get(area, 0); pr = local_price_map.get(area, 0)
        t_tkts += total; b_tkts += bk
        t_gross += total * pr; b_gross += bk * pr

    occ = round((b_tkts / t_tkts) * 100, 2) if t_tkts else 0
    return t_tkts, b_tkts, int(t_gross), int(b_gross), occ, seats, local_price_map


def get_seat_layout_http(venue_code, session_id):
    """HTTP-based BMS seat layout — with adaptive throttle, exponential backoff,
    per-thread unique fingerprint, and session rotation on 429.
    On rate limit, the session is destroyed and a fresh one created (new UA,
    new cookies, new Accept-Language) so BMS sees a “new user”."""
    api_url = "https://services-in.bookmyshow.com/doTrans.aspx"
    payload = (
        f"strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode={venue_code}"
        f"&lngTransactionIdentifier=0&strParam1={session_id}"
        f"&strParam2=WEB&strParam5=Y&strFormat=json"
    )

    attempts        = 0
    timeout_retries = 0

    while attempts < BMS_429_MAX_RETRIES:
        # Get or create thread-local session (fresh UA + cookies each time)
        if not hasattr(_thread_local, 'bms_session'):
            s = requests.Session()
            s.headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": UserAgent().random,
                "Origin": "https://in.bookmyshow.com",
                "Referer": "https://in.bookmyshow.com/",
                "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
            })
            proxy = _next_proxy()
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            _thread_local.bms_session = s
        session = _thread_local.bms_session

        bms_throttle.acquire()
        try:
            resp = session.post(api_url, data=payload, timeout=15)
        except Exception as e:
            bms_throttle.release()
            if "timeout" in str(e).lower():
                timeout_retries += 1
                if timeout_retries <= 2:
                    continue
                return None, f"timeout x{timeout_retries}"
            if _proxy_pool:
                p = _next_proxy()
                if p:
                    session.proxies = {"http": p, "https": p}
                attempts += 1
                continue
            return None, str(e).split('\n')[0]
        bms_throttle.release()

        if resp.status_code == 429:
            attempts += 1
            bms_throttle.report_429()
            wait = min(2 ** min(attempts, 4) + random.uniform(0, 2), 20)
            time.sleep(wait)
            # Session rotation: destroy session → next iteration creates fresh identity
            try: _thread_local.bms_session.close()
            except Exception: pass
            del _thread_local.bms_session
            continue

        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"

        data = resp.json().get("BookMyShow", {})
        if data.get("blnSuccess") == "true":
            bms_throttle.report_success()
            return data.get("strData"), None

        error_msg = data.get("strException", "")
        if any(kw in error_msg.lower() for kw in ["rate limit", "connectivity issue", "high demand"]):
            attempts += 1
            bms_throttle.report_429()
            if attempts < BMS_SOFT_RETRIES:
                time.sleep(random.uniform(0.3, 1.0))
                continue
            wait = min(2 ** min(attempts, 4) + random.uniform(0, 2), 20)
            time.sleep(wait)
            # Rotate session on app-level rate limit too
            try: _thread_local.bms_session.close()
            except Exception: pass
            del _thread_local.bms_session
            continue

        return None, error_msg

    return None, "RATE_LIMITED"


def get_seat_layout(driver, venue_code, session_id):
    """Selenium XHR for BMS seat layout API.
    Uses global BmsThrottle for pacing + exponential backoff on rate limits."""
    api_url = "https://services-in.bookmyshow.com/doTrans.aspx"
    js = """
        var cb = arguments[0]; var x = new XMLHttpRequest();
        x.open("POST", "%s", true);
        x.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
        x.onload = function() { cb(x.responseText); };
        x.onerror = function() { cb(null); };
        x.send("strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode=%s&lngTransactionIdentifier=0&strParam1=%s&strParam2=WEB&strParam5=Y&strFormat=json");
    """ % (api_url, venue_code, session_id)

    attempts        = 0
    timeout_retries = 0
    while attempts < BMS_429_MAX_RETRIES:
        bms_throttle.acquire()
        try:
            driver.set_script_timeout(3)
            resp = driver.execute_async_script(js)
        except Exception as e:
            bms_throttle.release()
            err_line = str(e).split('\n')[0]
            if "timeout" in err_line.lower():
                timeout_retries += 1
                if timeout_retries <= 2:
                    continue
                return None, f"timeout x{timeout_retries}"
            return None, err_line
        bms_throttle.release()

        if not resp:
            return None, "Empty response"
        data = json.loads(resp).get("BookMyShow", {})
        if data.get("blnSuccess") == "true":
            bms_throttle.report_success()
            return data.get("strData"), None
        error_msg = data.get("strException", "")
        if any(kw in error_msg.lower() for kw in ["rate limit", "connectivity issue", "high demand"]):
            attempts += 1
            bms_throttle.report_429()
            if attempts < BMS_SOFT_RETRIES:
                time.sleep(random.uniform(0.3, 1.0))
                continue
            wait = min(2 ** min(attempts, 4) + random.uniform(0, 2), 20)
            time.sleep(wait)
            continue
        return None, error_msg
    return None, "RATE_LIMITED"


# Global: detect whether HTTP seat layout works (tested once, used for all cities)
_bms_http_tested = False
_bms_http_works  = False
_bms_http_lock   = threading.Lock()

# Global BMS SIDs set (shared across all cities/workers)
_global_bms_sids = set()
_global_bms_sids_lock = threading.Lock()

# Global District SIDs set (shared across all cities/workers)
_global_district_sids = set()
_global_district_sids_lock = threading.Lock()


def process_bms_venue(driver, venue, city_name, use_http=False):
    """
    Processes ONE BMS venue. Uses HTTP seat layout if use_http=True, else Selenium XHR.
    Full business logic: sold-out recovery, screen caching, deferred SIDs.
    """
    results            = []
    screen_details_map = {}  # screenName → seat_map (cache for recovery)

    try:
        v_name = venue["additionalData"]["venueName"]
        v_code = venue["additionalData"]["venueCode"]

        shows      = venue.get("showtimes", [])
        shows.sort(key=lambda s: s["additionalData"].get("availStatus", "0"), reverse=True)
        show_queue    = deque(shows)
        deferred_sids = set()

        while show_queue:
            show      = show_queue.popleft()
            sid       = str(show["additionalData"]["sessionId"])
            show_time = show["title"]

            raw_screen = show.get("screenAttr", "")
            screenName = raw_screen if raw_screen else "Main Screen"

            with _global_bms_sids_lock:
                if sid in _global_bms_sids:
                    continue
                _global_bms_sids.add(sid)

            soldOut        = False
            seat_map       = {}
            is_fallback    = False
            price_seat_map = {}

            try:
                cats      = show["additionalData"].get("categories", [])
                price_map = {c["areaCatCode"]: float(c["curPrice"]) for c in cats}
                enc, error_msg = get_seat_layout_http(v_code, sid) if use_http else get_seat_layout(driver, v_code, sid)
                data           = None

                # Rate-limited after all retries → queue for retry sweep
                if error_msg == "RATE_LIMITED":
                    with _bms_retry_lock:
                        _bms_retry_queue.append({
                            'venue_code': v_code, 'sid': sid,
                            'show_time': show_time, 'screenName': screenName,
                            'v_name': v_name, 'cats': cats,
                            'price_map': price_map,
                            'city_name': city_name,
                        })
                    continue

                if not enc:
                    if not price_map:
                        continue
                    max_price   = max(price_map.values())
                    is_fallback = True
                    for p in price_map.values():
                        price_seat_map[float(p)] = 0

                    if error_msg and "sold out" in error_msg.lower():
                        recovered_capacity = None
                        recovered_seat_map = None

                        if screenName in screen_details_map:
                            recovered_seat_map = screen_details_map[screenName]
                            recovered_capacity = sum(recovered_seat_map.values())

                        if not recovered_capacity:
                            try:
                                base_sid = int(sid)
                                for offset in range(7, 0, -1):
                                    target_sid = str(base_sid + offset)
                                    n_enc, _ = get_seat_layout_http(v_code, target_sid) if use_http else get_seat_layout(driver, v_code, target_sid)
                                    if n_enc:
                                        n_dec = decrypt_data(n_enc)
                                        n_res = calculate_bms_collection(n_dec, {})
                                        if n_res[0] > 0:
                                            recovered_capacity = n_res[0]
                                            recovered_seat_map = n_res[5]
                                            break
                            except Exception:
                                pass

                        if recovered_capacity:
                            calc_gross = sum(count * price_map.get(ac, 0) for ac, count in recovered_seat_map.items())
                            if calc_gross > 0:
                                t_tkts = b_tkts = recovered_capacity
                                t_gross = b_gross = calc_gross
                                screen_details_map[screenName] = recovered_seat_map
                                seat_map    = recovered_seat_map
                                is_fallback = False
                                ps_map      = defaultdict(int)
                                for ac, count in seat_map.items():
                                    ps_map[float(price_map.get(ac, 0))] += count
                                price_seat_map = dict(ps_map)
                            else:
                                recovered_capacity = None

                        if not recovered_capacity:
                            FALLBACK_SEATS = 400
                            t_tkts  = b_tkts  = FALLBACK_SEATS
                            t_gross = b_gross = int(FALLBACK_SEATS * max_price)

                        occ     = 100.0
                        soldOut = True
                        data    = {"total_tickets": t_tkts, "booked_tickets": b_tkts,
                                   "total_gross": t_gross, "booked_gross": b_gross, "occupancy": occ}

                    else:
                        if screenName in screen_details_map:
                            cached = screen_details_map[screenName]
                            seat_map     = cached
                            t_tkts       = sum(cached.values())
                            b_tkts       = int(t_tkts * 0.5)
                            ps_map       = defaultdict(int); t_gross_calc = 0
                            for ac, count in cached.items():
                                pr = float(price_map.get(ac, 0))
                                ps_map[pr] += count; t_gross_calc += count * pr
                            price_seat_map = dict(ps_map)
                            t_gross = int(t_gross_calc); b_gross = int(t_gross * 0.5)
                            occ = 50.0; is_fallback = False
                        elif sid not in deferred_sids and len(show_queue) > 0:
                            deferred_sids.add(sid)
                            with _global_bms_sids_lock:
                                _global_bms_sids.discard(sid)
                            show_queue.append(show)
                            continue
                        else:
                            t_tkts  = 400; b_tkts  = 200
                            t_gross = int(400 * max_price); b_gross = int(200 * max_price)
                            occ     = 50.0
                        data = {"total_tickets": t_tkts, "booked_tickets": b_tkts,
                                "total_gross": t_gross, "booked_gross": b_gross, "occupancy": occ}
                else:
                    decrypted = decrypt_data(enc)
                    res       = calculate_bms_collection(decrypted, price_map)
                    data      = {
                        "total_tickets":  abs(res[0]),
                        "booked_tickets": min(abs(res[1]), abs(res[0])),
                        "total_gross":    abs(res[2]),
                        "booked_gross":   min(abs(res[3]), abs(res[2])),
                        "occupancy":      min(100, abs(res[4])),
                    }
                    seat_map        = res[5]
                    final_price_map = res[6]

                    if data["total_tickets"] > 0:
                        ps_map  = defaultdict(int); ps_list = []
                        for ac, count in seat_map.items():
                            pr = float(final_price_map.get(ac, 0))
                            ps_map[pr] += count; ps_list.append((pr, count))
                        price_seat_map             = dict(ps_map)
                        data["price_seat_signature"] = sorted(ps_list)
                        screen_details_map[screenName] = seat_map

                if data and data['total_tickets'] > 0:
                    normalized_time = normalize_bms_time(SHOW_DATE, show_time)
                    data.update({
                        "source":               "bms",
                        "sid":                  sid,
                        "city":                 city_name,
                        "venue":                v_name,
                        "venue_code":           v_code,
                        "showTime":             show_time,
                        "normalized_show_time": normalized_time,
                        "seat_category_map":    seat_map,
                        "price_seat_map":       price_seat_map,
                        "price_seat_signature": data.get("price_seat_signature", []),
                        "seat_signature":       build_seat_signature(seat_map),
                        "is_fallback":          is_fallback,
                    })
                    results.append(data)

            except Exception:
                continue

    except Exception as e:
        print(f"❌ [BMS] Venue worker error for {city_name}: {e}")

    return results


def fetch_bms_city(city_name, city_slug, city_counter_str):
    """
    Fetches all BMS data for one city.
    Creates a FRESH Chrome driver each call — required to pass Cloudflare per-city.
    Driver is quit immediately after page load; seat layouts done via parallel HTTP.
    """
    global _bms_http_tested, _bms_http_works

    url    = BMS_URL_TEMPLATE.format(city=city_slug)
    driver = None

    try:
        city_start = time.monotonic()
        driver     = _create_chrome_driver()

        state_data = extract_initial_state_from_page(driver, url)
        venues     = extract_venues(state_data) if state_data else []
        page_ms    = int((time.monotonic() - city_start) * 1000)

        try:
            driver.quit()
        except Exception:
            pass
        driver = None

        if not venues:
            return []

        print(f"   🏙️  {city_counter_str} {city_name:<15} — {len(venues)} venues ({page_ms}ms)")

        with _bms_http_lock:
            if not _bms_http_tested:
                for v in venues:
                    shows = v.get("showtimes", [])
                    if not shows:
                        continue
                    test_vcode = v["additionalData"]["venueCode"]
                    test_sid   = str(shows[0]["additionalData"]["sessionId"])
                    enc, err   = get_seat_layout_http(test_vcode, test_sid)
                    _bms_http_works = enc is not None or (err and "sold out" in err.lower())
                    break
                _bms_http_tested = True
                mode = "parallel HTTP" if _bms_http_works else "Selenium"
                print(f"   🔍 [BMS] Seat layout mode: {mode}")

        if _bms_http_works:
            city_results = []
            with ThreadPoolExecutor(max_workers=BMS_VENUE_WORKERS) as venue_pool:
                futures = [
                    venue_pool.submit(process_bms_venue, None, v, city_name, True)
                    for v in venues
                ]
                for f in as_completed(futures):
                    try:
                        city_results.extend(f.result())
                    except Exception as e:
                        print(f"      ❌ Venue worker error: {e}")
        else:
            city_results = []
            selenium_driver = _create_chrome_driver()
            try:
                for venue in venues:
                    city_results.extend(process_bms_venue(selenium_driver, venue, city_name))
            finally:
                try:
                    selenium_driver.quit()
                except Exception:
                    pass

        gross   = sum(r['booked_gross'] for r in city_results)
        city_ms = int((time.monotonic() - city_start) * 1000)
        if city_results:
            print(f"   ✅ [BMS] {city_counter_str} {city_name:<15} | Shows: {len(city_results):<3} | Gross: ₹{gross:<10,} ({city_ms}ms)")
        return city_results

    except Exception as e:
        print(f"   ❌ [BMS] {city_counter_str} {city_name:<15} — Error: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def run_bms(city_pairs):
    """
    Main BMS runner — fresh Chrome driver per city, BMS_DRIVER_POOL_SIZE parallel.
    """
    all_results    = []
    total          = len(city_pairs)
    completed      = [0]
    _progress_lock = threading.Lock()
    workers        = min(BMS_DRIVER_POOL_SIZE, total)

    print(f"\n🚀 [BMS] Starting — {total} cities, {workers} parallel workers, {BMS_VENUE_WORKERS} venue workers")
    print(f"   Strategy: fresh driver per city + parallel HTTP seat layouts\n")

    bms_start = time.monotonic()

    def _process_city(args):
        idx, (city_name, city_slug) = args
        counter_str = f"[{idx}/{total}]"
        try:
            results = fetch_bms_city(city_name, city_slug, counter_str)
            with _progress_lock:
                completed[0] += 1
                if completed[0] % 20 == 0 or completed[0] == total:
                    elapsed = time.monotonic() - bms_start
                    print(f"   📊 [BMS] Progress: {completed[0]}/{total} cities done ({elapsed:.0f}s)")
            return results
        except Exception as e:
            print(f"❌ [BMS] Error for {city_name}: {e}")
            return []

    with ThreadPoolExecutor(max_workers=workers) as city_pool:
        futures = [
            city_pool.submit(_process_city, (idx, city_info))
            for idx, city_info in enumerate(city_pairs, 1)
        ]
        for f in as_completed(futures):
            try:
                all_results.extend(f.result())
            except Exception as e:
                print(f"❌ [BMS] City future error: {e}")

    bms_elapsed = time.monotonic() - bms_start
    print(f"\n✅ [BMS] Initial pass done — {len(all_results)} shows across {total} cities in {bms_elapsed:.1f}s")
    print(f"   📊 [Throttle] {bms_throttle.stats}")

    # ── Retry sweep: recover rate-limited shows ──────────────────────────────
    with _bms_retry_lock:
        retry_batch = list(_bms_retry_queue)
        _bms_retry_queue.clear()

    if retry_batch:
        print(f"\n🔄 [BMS] Retry sweep: {len(retry_batch)} rate-limited shows")
        recovered = 0
        still_failed = 0
        for item in retry_batch:
            time.sleep(random.uniform(0.5, 1.5))
            enc, err = get_seat_layout_http(item['venue_code'], item['sid'])
            if not enc:
                still_failed += 1
                continue
            try:
                decrypted = decrypt_data(enc)
                res       = calculate_bms_collection(decrypted, item['price_map'])
                data = {
                    "total_tickets":  abs(res[0]),
                    "booked_tickets": min(abs(res[1]), abs(res[0])),
                    "total_gross":    abs(res[2]),
                    "booked_gross":   min(abs(res[3]), abs(res[2])),
                    "occupancy":      min(100, abs(res[4])),
                }
                if data["total_tickets"] > 0:
                    seat_map        = res[5]
                    final_price_map = res[6]
                    ps_map = defaultdict(int); ps_list = []
                    for ac, count in seat_map.items():
                        pr = float(final_price_map.get(ac, 0))
                        ps_map[pr] += count; ps_list.append((pr, count))
                    normalized_time = normalize_bms_time(SHOW_DATE, item['show_time'])
                    data.update({
                        "source": "bms", "sid": item['sid'],
                        "city": item['city_name'],
                        "venue": item['v_name'], "venue_code": item['venue_code'],
                        "showTime": item['show_time'],
                        "normalized_show_time": normalized_time,
                        "seat_category_map": seat_map,
                        "price_seat_map": dict(ps_map),
                        "price_seat_signature": sorted(ps_list),
                        "seat_signature": build_seat_signature(seat_map),
                        "is_fallback": False,
                    })
                    all_results.append(data)
                    recovered += 1
            except Exception:
                still_failed += 1
        print(f"   ✅ [Retry] Recovered {recovered}/{len(retry_batch)} shows ({still_failed} still failed)")

    total_elapsed = time.monotonic() - bms_start
    print(f"\n✅ [BMS] All done — {len(all_results)} total shows in {total_elapsed:.1f}s")
    return all_results


# =============================================================================
# ── VENUE MAPPING ─────────────────────────────────────────────────────────────
# =============================================================================

VENUE_MAP = {}   # BMS VenueCode → District cinema_id

def load_venue_mapping():
    global VENUE_MAP
    mapping_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils', 'venue_mapping.json')
    if os.path.exists(mapping_path):
        with open(mapping_path, encoding='utf-8') as f:
            data = json.load(f)
        VENUE_MAP = data.get('bms_to_district', {})
        print(f"📍 Loaded venue mapping: {len(VENUE_MAP)} BMS→District pairs")
    else:
        print("⚠️  Venue mapping not found (utils/venue_mapping.json). Venue-based matching disabled.")

def _is_same_venue(bms_show, dist_show):
    """Check venue mapping. Returns True/False if mapping exists, 'unmapped' if BMS venue not in map."""
    bms_code = bms_show.get('venue_code', '')
    dist_cid = dist_show.get('cinema_id', '')
    if not bms_code or not dist_cid:
        return 'unmapped'
    mapped_dist = VENUE_MAP.get(bms_code)
    if mapped_dist is None:
        return 'unmapped'
    return mapped_dist == dist_cid

# =============================================================================
# ── DEDUP + MERGE ─────────────────────────────────────────────────────────────
# =============================================================================

def dedup_same_platform(records, source_label):
    seen    = {}
    best    = []
    dropped = 0
    for r in records:
        sid = r.get('sid', '')
        if not sid:
            best.append(r); continue
        if sid not in seen:
            seen[sid] = len(best)
            best.append(r)
        else:
            dropped += 1
            existing = best[seen[sid]]
            if r.get('booked_gross', 0) > existing.get('booked_gross', 0):
                best[seen[sid]] = r
                print(f"   ♻️  [{source_label}] Replaced lower-gross duplicate SID {sid}")
            else:
                print(f"   ♻️  [{source_label}] Dropped duplicate SID {sid}")
    if dropped:
        print(f"   ✅ [{source_label}] Dedup removed {dropped} duplicate(s). {len(best)} unique shows remain.")
    return best


def merge_data(dist_data, bms_data):
    dist_data = dedup_same_platform(dist_data, "District")
    bms_data  = dedup_same_platform(bms_data,  "BMS")

    print(f"\n🔄 Merging {len(dist_data)} District + {len(bms_data)} BMS shows...")
    final_data     = []
    SEAT_TOLERANCE = 5

    district_by_time = defaultdict(list)
    for r in dist_data:
        district_by_time[(r['city'], r['normalized_show_time'])].append(r)

    for bms in bms_data:
        key        = (bms['city'], bms['normalized_show_time'])
        candidates = district_by_time.get(key, [])
        match      = None

        # 1. Exact SID
        for c in candidates:
            if c['sid'] == bms['sid']:
                match = c; print(f"   🔗 SID Match: {bms['sid']}"); break

        # 2. Price + Seat signature + Venue Map
        if not match and not bms.get('is_fallback', False):
            b_sig = bms.get('price_seat_signature', [])
            for c in candidates:
                d_sig = c.get('price_seat_signature', [])
                if not b_sig or not d_sig or len(b_sig) != len(d_sig): continue
                if all(bp == dp and abs(bs - ds) <= SEAT_TOLERANCE
                       for (bp, bs), (dp, ds) in zip(b_sig, d_sig)):
                    if _is_same_venue(bms, c) is True:
                        match = c
                        print(f"   🔗 Price/Seat Sig + Venue Map: {bms['venue']} == {c['venue']}")
                        break

        # 3. Seat signature + Venue Map
        if not match and not bms.get('is_fallback', False):
            b_seats = sorted(bms.get('seat_category_map', {}).values())
            for c in candidates:
                d_seats = sorted(c.get('seat_category_map', {}).values())
                if not b_seats or not d_seats or len(b_seats) != len(d_seats): continue
                if all(abs(bs - ds) <= SEAT_TOLERANCE for bs, ds in zip(b_seats, d_seats)):
                    if _is_same_venue(bms, c) is True:
                        match = c
                        print(f"   🔗 Seat Sig + Venue Map: {bms['venue']} == {c['venue']}")
                        break

        # 4. Venue map + strict price set
        if not match and candidates:
            b_prices = {p for p in bms.get('price_seat_map', {}).keys() if p > 0}
            for c in candidates:
                d_prices = {p for p in c.get('price_seat_map', {}).keys() if p > 0}
                if b_prices != d_prices: continue
                if _is_same_venue(bms, c) is True:
                    match = c
                    print(f"   🔗 Venue Map + Price: {bms['venue']} == {c['venue']}")
                    break

        # 5. Venue map only (seats/prices may differ between platforms)
        if not match and candidates:
            for c in candidates:
                if _is_same_venue(bms, c) is True:
                    match = c
                    print(f"   🔗 Venue Map Only: {bms['venue']} == {c['venue']}")
                    break

        if match:
            candidates.remove(match)
            if not bms.get('is_fallback', False) and bms['booked_gross'] > match['booked_gross']:
                for k in ('total_tickets','booked_tickets','total_gross','booked_gross',
                          'occupancy','seat_category_map','price_seat_map','seat_signature'):
                    match[k] = bms[k]
            # Store both SIDs for cross-run identity matching
            match['bms_sid']      = bms['sid']
            match['district_sid'] = match['sid']
            final_data.append(match)
        else:
            bms['bms_sid']      = bms['sid']
            bms['district_sid'] = None
            final_data.append(bms)

    for sublist in district_by_time.values():
        for show in sublist:
            show['bms_sid']      = None
            show['district_sid'] = show['sid']
            final_data.append(show)

    print(f"✅ Merge complete — {len(final_data)} final shows.")
    return final_data


# =============================================================================
# ── EXCEL ─────────────────────────────────────────────────────────────────────
# =============================================================================

def generate_excel(data, filename):
    wb          = Workbook()
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    # Theatre Wise
    ws_th = wb.active
    ws_th.title = "Theatre Wise"
    ws_th.append(["Venue","Shows","Total Seats","Booked Seats","Total Gross","Booked Gross","Occ %"])
    th_map = {}
    for r in data:
        k = r["venue"]
        if k not in th_map:
            th_map[k] = {"shows":0,"t_seats":0,"b_seats":0,"p_gross":0,"b_gross":0}
        d = th_map[k]
        d["shows"]+=1; d["t_seats"]+=r["total_tickets"]; d["b_seats"]+=r["booked_tickets"]
        d["p_gross"]+=r["total_gross"]; d["b_gross"]+=r["booked_gross"]
    for v, d in th_map.items():
        occ = round((d["b_seats"]/d["t_seats"])*100,2) if d["t_seats"] else 0
        ws_th.append([v,d["shows"],d["t_seats"],d["b_seats"],d["p_gross"],d["b_gross"],occ])

    # City Wise
    ws_city = wb.create_sheet(title="City Wise")
    ws_city.append(["City","Theatres","Shows","Total Seats","Booked Seats","Total Gross","Booked Gross","Occ %"])
    city_map = {}
    for r in data:
        k = r["city"]
        if k not in city_map:
            city_map[k] = {"shows":0,"t_seats":0,"b_seats":0,"p_gross":0,"b_gross":0,"venues":set()}
        d = city_map[k]
        d["shows"]+=1; d["t_seats"]+=r["total_tickets"]; d["b_seats"]+=r["booked_tickets"]
        d["p_gross"]+=r["total_gross"]; d["b_gross"]+=r["booked_gross"]; d["venues"].add(r["venue"])
    for city, d in city_map.items():
        occ = round((d["b_seats"]/d["t_seats"])*100,2) if d["t_seats"] else 0
        ws_city.append([city,len(d["venues"]),d["shows"],d["t_seats"],d["b_seats"],d["p_gross"],d["b_gross"],occ])

    # Show Wise
    ws_show = wb.create_sheet(title="Show Wise")
    ws_show.append(["Source","City","Venue","Time","SID","Total Seats","Booked Seats","Total Gross","Booked Gross","Occ %"])
    for r in data:
        ws_show.append([r["source"],r["city"],r["venue"],r["normalized_show_time"],r["sid"],
                        r["total_tickets"],r["booked_tickets"],r["total_gross"],r["booked_gross"],r["occupancy"]])

    # Summary
    ws_sum = wb.create_sheet(title="Summary")
    agg_t  = sum(r["total_tickets"]  for r in data)
    agg_b  = sum(r["booked_tickets"] for r in data)
    agg_bg = sum(r["booked_gross"]   for r in data)
    occ    = round((agg_b/agg_t)*100,2) if agg_t else 0
    ws_sum.append(["Metric","Value"])
    for row in [("Total Cities",len(city_map)),("Total Theatres",len(th_map)),
                ("Total Shows",len(data)),("Booked Gross",agg_bg),
                ("Occupancy %",occ),("Generated At",datetime.now().strftime("%Y-%m-%d %H:%M:%S"))]:
        ws_sum.append(list(row))

    path = os.path.join(reports_dir, filename)
    wb.save(path)
    print(f"📊 Excel saved: {path}")


# =============================================================================
# ── REPORT MANAGEMENT ────────────────────────────────────────────────────────
# =============================================================================

def get_report_base_name(movie_name, show_date, report_type):
    """Generate meaningful report name: MovieName_18Mar_CitiesReport"""
    slug = movie_name.replace(" ", "_")
    date_str = datetime.strptime(show_date, "%Y-%m-%d").strftime("%d%b")
    return f"{slug}_{date_str}_{report_type}Report"


def load_previous_report_data(base_name, reports_dir="reports"):
    """Load previously saved show data for merging."""
    path = os.path.join(reports_dir, f"{base_name}_data.json")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📂 Loaded previous data: {len(data)} shows from {path}")
            return data
        except Exception as e:
            print(f"⚠️  Could not load previous data: {e}")
    return None


def save_report_data(final_data, base_name, reports_dir="reports"):
    """Save show data as JSON for future merging."""
    path = os.path.join(reports_dir, f"{base_name}_data.json")
    serializable = []
    for show in final_data:
        s = {}
        for k, v in show.items():
            s[k] = list(v) if isinstance(v, set) else v
        serializable.append(s)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"💾 Data saved: {path}")


def merge_with_previous_data(new_data, old_data):
    """Merge current run with previous saved data.
    - Identity: a show is the same if either its bms_sid or district_sid matches.
    - Current run data always wins; old-only shows (morning shows etc.) are preserved.
    """
    if not old_data:
        return new_data

    new_sids: set[str] = set()
    for show in new_data:
        if show.get('bms_sid'):
            new_sids.add(show['bms_sid'])
        if show.get('district_sid'):
            new_sids.add(show['district_sid'])

    merged = list(new_data)
    preserved = 0
    for show in old_data:
        old_show_sids = {s for s in (show.get('bms_sid'), show.get('district_sid')) if s}
        if not old_show_sids and show.get('sid'):
            old_show_sids = {show['sid']}
        if old_show_sids & new_sids:
            continue
        merged.append(show)
        preserved += 1

    if preserved:
        print(f"   📎 Preserved {preserved} shows from previous run")
    return merged


def archive_previous_reports(base_name, reports_dir="reports", old_reports_dir="old_reports"):
    """Move existing aggregated reports to old_reports/ before overriding."""
    os.makedirs(old_reports_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    moved = 0
    for ext in ['.xlsx', '.png', '.html', '_data.json']:
        src = os.path.join(reports_dir, f"{base_name}{ext}")
        if os.path.exists(src):
            dest = os.path.join(old_reports_dir, f"{base_name}_{ts}{ext}")
            shutil.move(src, dest)
            moved += 1
    if moved:
        print(f"   📁 Archived {moved} previous report files to {old_reports_dir}/")


# =============================================================================
# ── MAIN ──────────────────────────────────────────────────────────────────────
# =============================================================================

if __name__ == "__main__":
    # Build city pairs — city name derived from District slug
    district_pairs = [
        (slug.replace("-", " ").title(), slug)
        for slug in DISTRICT_CITIES
    ]
    bms_pairs = [
        (d_slug.replace("-", " ").title(), b_slug)
        for d_slug, b_slug in zip(DISTRICT_CITIES, BMS_CITIES)
    ]

    # Clear global SIDs sets for fresh run
    with _global_district_sids_lock:
        _global_district_sids.clear()
    with _global_bms_sids_lock:
        _global_bms_sids.clear()

    # Load optional proxy pool for BMS IP rotation
    _load_proxies()

    total = len(district_pairs)
    print(f"🎬 BMS — {len(bms_pairs)} cities ({BMS_DRIVER_POOL_SIZE} parallel) | District — {total} cities ({DISTRICT_CITY_WORKERS} parallel)")
    print(f"   BMS: fresh Chrome per city + parallel HTTP seat layouts")
    print(f"   ⚡ Both platforms running in parallel\n")

    all_dist_data = []
    all_bms_data  = []

    # District and BMS run fully in parallel — each is one thread
    with ThreadPoolExecutor(max_workers=2) as pool:
        district_future = pool.submit(run_district, district_pairs)
        bms_future      = pool.submit(run_bms,      bms_pairs)

        all_dist_data = district_future.result()
        all_bms_data  = bms_future.result()

    print(f"\n📋 Both sources done.")
    print(f"   District: {len(all_dist_data)} shows")
    print(f"   BMS:      {len(all_bms_data)} shows")

    # Load venue mapping and merge
    load_venue_mapping()
    final_data = merge_data(all_dist_data, all_bms_data)

    # Reports
    if final_data:
        movie_name      = extract_movie_name_from_url(DISTRICT_URL_TEMPLATE.replace("{city}", DISTRICT_CITIES[0]))
        show_date_fmt   = datetime.strptime(SHOW_DATE, "%Y-%m-%d").strftime("%d %b %Y")
        base_name       = get_report_base_name(movie_name, SHOW_DATE, "Cities")
        is_show_day     = SHOW_DATE == datetime.now().strftime("%Y-%m-%d")
        current_run_data = list(final_data)  # snapshot before merging

        # Load previous data and merge (preserves shows from earlier runs)
        old_data = load_previous_report_data(base_name)
        if old_data:
            final_data = merge_with_previous_data(final_data, old_data)

        print(f"\n📦 Generating reports — {len(final_data)} shows across {total} cities...")

        # Archive previous aggregated reports before overriding
        archive_previous_reports(base_name)

        # ── Aggregated report (cumulative) in reports/ ──
        generate_excel(final_data, f"{base_name}.xlsx")
        generate_premium_city_image_report(
            final_data, f"reports/{base_name}.png",
            movie_name=movie_name, show_date=show_date_fmt,
        )
        generate_hybrid_city_html_report(
            final_data,
            DISTRICT_URL_TEMPLATE.replace("{city}", DISTRICT_CITIES[0]),
            f"reports/{base_name}.html",
        )
        save_report_data(final_data, base_name)

        # ── Current-run-only report (booking update) in old_reports/ ──
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"{base_name}_{ts}"
        os.makedirs("old_reports", exist_ok=True)
        generate_excel(current_run_data, f"{snapshot_name}.xlsx")
        shutil.move(f"reports/{snapshot_name}.xlsx", f"old_reports/{snapshot_name}.xlsx")
        generate_premium_city_image_report(
            current_run_data, f"old_reports/{snapshot_name}.png",
            movie_name=movie_name, show_date=show_date_fmt,
        )
        generate_hybrid_city_html_report(
            current_run_data,
            DISTRICT_URL_TEMPLATE.replace("{city}", DISTRICT_CITIES[0]),
            f"old_reports/{snapshot_name}.html",
        )
        print(f"   📋 Booking update saved to old_reports/{snapshot_name}.*")

        # ── Email ──
        aggregated_files = [
            f"reports/{base_name}.xlsx",
            f"reports/{base_name}.png",
            f"reports/{base_name}.html",
        ]
        snapshot_files = [
            f"old_reports/{snapshot_name}.xlsx",
            f"old_reports/{snapshot_name}.png",
            f"old_reports/{snapshot_name}.html",
        ]

        if is_show_day and old_data:
            send_collection_report(
                report_type="cities",
                movie_name=movie_name,
                show_date=show_date_fmt,
                subject_label="Tracked Gross + Advance Sales",
                attachment_paths=aggregated_files + snapshot_files,
                sections=[
                    {
                        "label": "A. Tracked Gross + Advance Sales (Full Day)",
                        "note":  "Cumulative gross tracked so far, including advance sales for remaining shows today.",
                        "files": aggregated_files,
                    },
                    {
                        "label": "B. Advance Sales (Remaining Shows)",
                        "note":  "Current advance booking status for shows yet to begin.",
                        "files": snapshot_files,
                    },
                ],
            )
        else:
            send_collection_report(
                report_type="cities",
                movie_name=movie_name,
                show_date=show_date_fmt,
                subject_label="Advance Sales",
                attachment_paths=aggregated_files,
            )

        print(f"\n🏁 All done. Report: {base_name}")
    else:
        print("❌ No data collected.")