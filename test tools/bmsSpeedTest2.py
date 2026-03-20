"""Definitive BMS page load speed test with CORRECT slugs."""
import time
import json
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent

BMS_TPL = "https://in.bookmyshow.com/movies/{city}/dhurandhar-the-revenge/buytickets/ET00478890/20260321"

CITIES = [
    ("Bengaluru", "bengaluru"),
    ("Mysore", "mysore"),
    ("Hubli", "hubli"),
    ("Mangalore", "mangalore"),
    ("Belgaum", "belgaum"),
    ("Shimoga", "shimoga"),
    ("Davangere", "davangere"),
    ("Tumkur", "tumkur"),
]

def parse_state_and_venues(html):
    """Parse __INITIAL_STATE__ and extract venues."""
    marker = "window.__INITIAL_STATE__"
    start = html.find(marker)
    if start == -1:
        return None, 0
    start = html.find("{", start)
    brace_count = 0; end = start
    while end < len(html):
        if html[end] == "{": brace_count += 1
        elif html[end] == "}": brace_count -= 1
        if brace_count == 0: break
        end += 1
    try:
        state = json.loads(html[start:end + 1])
    except:
        return None, 0
    
    # Extract venues
    try:
        sbe = state.get("showtimesByEvent", {})
        dc = sbe.get("currentDateCode")
        if dc and dc in sbe.get("showDates", {}):
            sd = sbe["showDates"][dc]
            if "dynamic" in sd:
                widgets = sd["dynamic"]["data"]["showtimeWidgets"]
                for w in widgets:
                    if w.get("type") == "groupList":
                        for g in w["data"]:
                            if g.get("type") == "venueGroup":
                                return state, len(g["data"])
    except:
        pass
    return state, 0

def make_driver(page_load_strategy='normal', block_resources=False):
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
    options.add_argument("disable-csp")
    options.page_load_strategy = page_load_strategy
    
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    if block_resources:
        prefs["profile.managed_default_content_settings.stylesheets"] = 2
        prefs["profile.managed_default_content_settings.fonts"] = 2
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
    
    if block_resources:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setBlockedURLs", {
            "urls": ["*.css", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", 
                     "*.woff", "*.woff2", "*.ttf", "*.ico", "*.mp4", "*.webp",
                     "*google*", "*facebook*", "*branch.io*", "*sentry*",
                     "*analytics*", "*doubleclick*", "*gtag*"]
        })
    
    return driver

# ============================================================================
# TEST 1: Normal mode - fresh driver per city (BASELINE)
# ============================================================================
print("=" * 80)
print("TEST 1: BASELINE — normal mode, fresh driver per city")
print("=" * 80)

for city_name, slug in CITIES[:3]:
    url = BMS_TPL.format(city=slug)
    driver = make_driver()
    t0 = time.monotonic()
    driver.get(url)
    time.sleep(1)
    html = driver.page_source
    elapsed = (time.monotonic() - t0) * 1000
    state, venues = parse_state_and_venues(html)
    print(f"  {city_name:<15}: {elapsed:>6.0f}ms | Venues: {venues} | HTML: {len(html)} | URL: {driver.current_url[:80]}")
    driver.quit()

# ============================================================================
# TEST 2: Normal mode - REUSE single driver for all cities
# ============================================================================
print("\n" + "=" * 80)
print("TEST 2: REUSE — normal mode, single driver for 8 cities")
print("=" * 80)

driver = make_driver()
for city_name, slug in CITIES:
    url = BMS_TPL.format(city=slug)
    t0 = time.monotonic()
    driver.get(url)
    time.sleep(1)
    html = driver.page_source
    elapsed = (time.monotonic() - t0) * 1000
    state, venues = parse_state_and_venues(html)
    print(f"  {city_name:<15}: {elapsed:>6.0f}ms | Venues: {venues} | HTML: {len(html)} | URL: {driver.current_url[:80]}")
driver.quit()

# ============================================================================
# TEST 3: Eager mode + blocked resources - REUSE driver
# ============================================================================
print("\n" + "=" * 80)
print("TEST 3: EAGER + blocked resources — single driver for 8 cities")
print("=" * 80)

driver = make_driver(page_load_strategy='eager', block_resources=True)
for city_name, slug in CITIES:
    url = BMS_TPL.format(city=slug)
    t0 = time.monotonic()
    driver.get(url)
    # With eager, DOM is ready but JS may not have run
    # Poll for __INITIAL_STATE__ with showtime data
    found_venues = 0
    max_wait = 10  # max 10s
    while (time.monotonic() - t0) < max_wait:
        html = driver.page_source
        state, venues = parse_state_and_venues(html)
        if venues > 0:
            found_venues = venues
            break
        if state and "showtimesByEvent" in state:
            found_venues = venues
            break
        time.sleep(0.2)
    
    elapsed = (time.monotonic() - t0) * 1000
    if found_venues == 0:
        # Final check
        html = driver.page_source
        _, found_venues = parse_state_and_venues(html)
    print(f"  {city_name:<15}: {elapsed:>6.0f}ms | Venues: {found_venues} | HTML: {len(html)}")
driver.quit()

# ============================================================================
# TEST 4: Eager mode + blocked resources + NO sleep - REUSE driver
# ============================================================================
print("\n" + "=" * 80)
print("TEST 4: EAGER + blocked resources + JS wait for state — reuse driver")
print("=" * 80)

driver = make_driver(page_load_strategy='eager', block_resources=True)
for city_name, slug in CITIES:
    url = BMS_TPL.format(city=slug)
    t0 = time.monotonic()
    driver.get(url)
    
    # Use WebDriverWait-style JS polling for the showtime data
    try:
        driver.set_script_timeout(12)
        result = driver.execute_async_script("""
            var cb = arguments[0];
            var attempts = 0;
            function check() {
                attempts++;
                try {
                    var state = window.__INITIAL_STATE__;
                    if (state && state.showtimesByEvent && state.showtimesByEvent.currentDateCode) {
                        cb({found: true, attempts: attempts, keys: Object.keys(state.showtimesByEvent)});
                        return;
                    }
                } catch(e) {}
                if (attempts > 50) {
                    cb({found: false, attempts: attempts});
                    return;
                }
                setTimeout(check, 200);
            }
            check();
        """)
        elapsed = (time.monotonic() - t0) * 1000
        
        if result and result.get('found'):
            html = driver.page_source
            _, venues = parse_state_and_venues(html)
            print(f"  {city_name:<15}: {elapsed:>6.0f}ms | Venues: {venues} | JS polls: {result.get('attempts')}")
        else:
            print(f"  {city_name:<15}: {elapsed:>6.0f}ms | NOT FOUND | JS polls: {result.get('attempts') if result else '?'}")
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  {city_name:<15}: {elapsed:>6.0f}ms | ERROR: {str(e)[:80]}")
driver.quit()

# ============================================================================
# TEST 5: Try direct HTTP to BMS API for showtimes  
# ============================================================================
print("\n" + "=" * 80)
print("TEST 5: BMS API discovery — try known API endpoints")
print("=" * 80)

import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://in.bookmyshow.com",
    "Referer": "https://in.bookmyshow.com/",
})

api_urls = [
    ("Showtimes API v1", "https://in.bookmyshow.com/api/explore/v1/showtimes/event/ET00478890?date=20260321&regionCode=BANG"),
    ("Showtimes API v2", "https://in.bookmyshow.com/api/v2/showtimes/event/ET00478890?date=20260321&regionCode=BANG"),
    ("Event Details", "https://in.bookmyshow.com/api/explore/v1/discover/event/ET00478890"),
    ("Showtime Widget", "https://in.bookmyshow.com/api/v1/content/showtimes?eventCode=ET00478890&date=20260321&region=BANG"),
    ("GraphQL", "https://in.bookmyshow.com/graphql"),
]

for name, url in api_urls:
    t0 = time.monotonic()
    try:
        if "graphql" in url:
            resp = session.post(url, json={
                "query": "query { showtimesByEvent(eventCode: \"ET00478890\", date: \"20260321\", regionCode: \"BANG\") { showDates } }"
            }, timeout=10)
        else:
            resp = session.get(url, timeout=10)
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  {name:<25}: HTTP {resp.status_code} | {elapsed:.0f}ms | Size: {len(resp.text)} | Body: {resp.text[:200]}")
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  {name:<25}: ERROR in {elapsed:.0f}ms — {e}")

print("\n" + "=" * 80)
print("ALL TESTS COMPLETE")
print("=" * 80)
