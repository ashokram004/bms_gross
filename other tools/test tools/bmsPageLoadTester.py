"""
BMS Page Load Speed Tester
Tests multiple approaches to fetch BMS show data without slow Selenium page loads.
"""
import time
import json
import requests

TEST_URL = "https://in.bookmyshow.com/movies/bangalore/dhurandhar-the-revenge/buytickets/ET00478890/20260321"
TEST_URLS = [
    ("Bangalore", "https://in.bookmyshow.com/movies/bangalore/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
    ("Mumbai", "https://in.bookmyshow.com/movies/mumbai/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
    ("Mysore", "https://in.bookmyshow.com/movies/mysore/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

def parse_next_data(html):
    """Extract __NEXT_DATA__ JSON from HTML."""
    marker = 'id="__NEXT_DATA__"'
    idx = html.find(marker)
    if idx == -1:
        return None
    start = html.find('>', idx) + 1
    end = html.find('</script>', start)
    if end == -1:
        return None
    try:
        return json.loads(html[start:end])
    except json.JSONDecodeError:
        return None

def parse_initial_state(html):
    """Extract window.__INITIAL_STATE__ JSON from HTML."""
    marker = "window.__INITIAL_STATE__"
    start = html.find(marker)
    if start == -1:
        return None
    start = html.find("{", start)
    if start == -1:
        return None
    brace_count = 0
    end = start
    while end < len(html):
        if html[end] == "{": brace_count += 1
        elif html[end] == "}": brace_count -= 1
        if brace_count == 0: break
        end += 1
    try:
        return json.loads(html[start:end + 1])
    except json.JSONDecodeError:
        return None

def extract_venues_from_next_data(data):
    """Try to extract venues from __NEXT_DATA__ JSON structure."""
    if not data:
        return []
    try:
        # Try common Next.js data paths
        page_props = data.get("props", {}).get("pageProps", {})
        
        # Path 1: Direct showtime data
        if "data" in page_props:
            d = page_props["data"]
            if "showtimesByEvent" in d:
                sbe = d["showtimesByEvent"]
                date_code = sbe.get("currentDateCode")
                if date_code:
                    widgets = sbe["showDates"][date_code]["dynamic"]["data"]["showtimeWidgets"]
                    for w in widgets:
                        if w.get("type") == "groupList":
                            for g in w["data"]:
                                if g.get("type") == "venueGroup":
                                    return g["data"]
        
        # Path 2: Server state
        if "serverState" in page_props.get("data", {}):
            ss = page_props["data"]["serverState"]
            if "showtimesByEvent" in ss:
                sbe = ss["showtimesByEvent"]
                date_code = sbe.get("currentDateCode")
                if date_code:
                    widgets = sbe["showDates"][date_code]["dynamic"]["data"]["showtimeWidgets"]
                    for w in widgets:
                        if w.get("type") == "groupList":
                            for g in w["data"]:
                                if g.get("type") == "venueGroup":
                                    return g["data"]
        
        # Path 3: If it's nested under initialState
        initial_state = page_props.get("initialState", {})
        if initial_state and "showtimesByEvent" in initial_state:
            sbe = initial_state["showtimesByEvent"]
            date_code = sbe.get("currentDateCode")
            if date_code:
                widgets = sbe["showDates"][date_code]["dynamic"]["data"]["showtimeWidgets"]
                for w in widgets:
                    if w.get("type") == "groupList":
                        for g in w["data"]:
                            if g.get("type") == "venueGroup":
                                return g["data"]
    except Exception as e:
        print(f"      Error parsing venues: {e}")
    return []

def extract_venues_from_initial_state(data):
    """Extract venues from __INITIAL_STATE__ JSON."""
    if not data:
        return []
    try:
        sbe = data.get("showtimesByEvent")
        if not sbe:
            return []
        date_code = sbe.get("currentDateCode")
        if not date_code:
            return []
        widgets = sbe["showDates"][date_code]["dynamic"]["data"]["showtimeWidgets"]
        for w in widgets:
            if w.get("type") == "groupList":
                for g in w["data"]:
                    if g.get("type") == "venueGroup":
                        return g["data"]
    except Exception:
        pass
    return []

# ============================================================================
# TEST 1: Pure HTTP GET with requests
# ============================================================================
print("=" * 80)
print("TEST 1: Pure HTTP GET (requests)")
print("=" * 80)

session = requests.Session()
session.headers.update(HEADERS)

for city_name, url in TEST_URLS:
    t0 = time.monotonic()
    try:
        resp = session.get(url, timeout=15)
        elapsed = (time.monotonic() - t0) * 1000
        html = resp.text
        
        has_next = "__NEXT_DATA__" in html
        has_init = "__INITIAL_STATE__" in html
        has_cf = "cf-browser-verification" in html.lower() or "just a moment" in html.lower() or "challenge-platform" in html.lower()
        
        print(f"\n  {city_name}:")
        print(f"    Status: {resp.status_code}")
        print(f"    Time: {elapsed:.0f}ms")
        print(f"    Size: {len(html)} chars")
        print(f"    Has __NEXT_DATA__: {has_next}")
        print(f"    Has __INITIAL_STATE__: {has_init}")
        print(f"    Cloudflare challenge: {has_cf}")
        
        if has_next:
            next_data = parse_next_data(html)
            venues = extract_venues_from_next_data(next_data)
            print(f"    Venues from __NEXT_DATA__: {len(venues)}")
            if venues:
                v0 = venues[0]
                print(f"    First venue: {v0.get('additionalData', {}).get('venueName', 'N/A')}")
                shows = v0.get("showtimes", [])
                print(f"    Shows in first venue: {len(shows)}")
        
        if has_init:
            init_data = parse_initial_state(html)
            venues = extract_venues_from_initial_state(init_data)
            print(f"    Venues from __INITIAL_STATE__: {len(venues)}")
        
        if not has_next and not has_init:
            # Show first 500 chars for debugging
            print(f"    First 500 chars: {html[:500]}")
            
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"\n  {city_name}: ERROR in {elapsed:.0f}ms — {e}")

# ============================================================================
# TEST 2: Selenium with page_load_strategy='eager' vs 'normal'
# ============================================================================
print("\n" + "=" * 80)
print("TEST 2: Selenium — normal vs eager vs none (with __NEXT_DATA__ parsing)")
print("=" * 80)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from fake_useragent import UserAgent
    
    strategies = ['normal', 'eager', 'none']
    
    for strategy in strategies:
        print(f"\n  --- page_load_strategy = '{strategy}' ---")
        
        ua = UserAgent()
        options = Options()
        options.add_argument(f"user-agent={ua.random}")
        options.add_argument("--headless=new")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-site-isolation-trials")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("disable-csp")
        options.page_load_strategy = strategy
        
        # Disable ALL non-essential resources
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.fonts": 2,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
        
        # Block CSS, images, fonts, media via CDP  
        if strategy in ('eager', 'none'):
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.setBlockedURLs", {
                "urls": ["*.css", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.woff", "*.woff2", "*.ttf", "*.ico", "*.mp4", "*.webp"]
            })
        
        url = TEST_URLS[0][1]  # Bangalore
        t0 = time.monotonic()
        
        if strategy == 'none':
            # For 'none', driver.get() returns immediately
            driver.get(url)
            # Poll for __NEXT_DATA__ or __INITIAL_STATE__
            max_poll = 15  # max 15 seconds
            poll_interval = 0.3
            found = False
            while (time.monotonic() - t0) < max_poll:
                html = driver.page_source
                if '__NEXT_DATA__' in html or '__INITIAL_STATE__' in html:
                    found = True
                    break
                time.sleep(poll_interval)
            elapsed = (time.monotonic() - t0) * 1000
            if not found:
                print(f"    Bangalore: __NEXT_DATA__/__INITIAL_STATE__ NOT found after {elapsed:.0f}ms")
                print(f"    HTML size: {len(html)}")
                driver.quit()
                continue
        else:
            driver.get(url)
            elapsed = (time.monotonic() - t0) * 1000
            html = driver.page_source
        
        has_next = "__NEXT_DATA__" in html
        has_init = "__INITIAL_STATE__" in html
        
        print(f"    Bangalore:")
        print(f"      Time: {elapsed:.0f}ms")
        print(f"      HTML size: {len(html)} chars")
        print(f"      Has __NEXT_DATA__: {has_next}")
        print(f"      Has __INITIAL_STATE__: {has_init}")
        
        venues = []
        if has_next:
            next_data = parse_next_data(html)
            venues = extract_venues_from_next_data(next_data)
            print(f"      Venues from __NEXT_DATA__: {len(venues)}")
        if has_init:
            init_data = parse_initial_state(html)
            venues2 = extract_venues_from_initial_state(init_data)
            print(f"      Venues from __INITIAL_STATE__: {len(venues2)}")
        
        if venues:
            v0 = venues[0]
            print(f"      First venue: {v0.get('additionalData', {}).get('venueName', 'N/A')}")
            shows = v0.get("showtimes", [])
            print(f"      Shows: {len(shows)}")
            if shows:
                s0 = shows[0]
                print(f"      First show time: {s0.get('title', 'N/A')}")
                sid = s0.get("additionalData", {}).get("sessionId", "N/A")
                print(f"      Session ID: {sid}")
        
        # Test a second city with same driver (can we reuse?)
        url2 = TEST_URLS[2][1]  # Mysore
        t1 = time.monotonic()
        if strategy == 'none':
            driver.get(url2)
            found = False
            while (time.monotonic() - t1) < max_poll:
                html2 = driver.page_source
                if '__NEXT_DATA__' in html2 or '__INITIAL_STATE__' in html2:
                    found = True
                    break
                time.sleep(poll_interval)
            elapsed2 = (time.monotonic() - t1) * 1000
        else:
            driver.get(url2)
            elapsed2 = (time.monotonic() - t1) * 1000
            html2 = driver.page_source
        
        has_next2 = "__NEXT_DATA__" in html2
        has_init2 = "__INITIAL_STATE__" in html2
        venues_r = []
        if has_next2:
            nd2 = parse_next_data(html2)
            venues_r = extract_venues_from_next_data(nd2)
        elif has_init2:
            id2 = parse_initial_state(html2)
            venues_r = extract_venues_from_initial_state(id2)
        
        print(f"    Mysore (REUSED driver):")
        print(f"      Time: {elapsed2:.0f}ms")
        print(f"      Has data: {has_next2 or has_init2}")
        print(f"      Venues: {len(venues_r)}")
        
        driver.quit()

except Exception as e:
    print(f"  Selenium test error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 3: cloudscraper (if available)
# ============================================================================
print("\n" + "=" * 80)
print("TEST 3: cloudscraper")
print("=" * 80)
try:
    import cloudscraper
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    for city_name, url in TEST_URLS[:2]:
        t0 = time.monotonic()
        resp = scraper.get(url, timeout=15)
        elapsed = (time.monotonic() - t0) * 1000
        html = resp.text
        
        has_next = "__NEXT_DATA__" in html
        has_init = "__INITIAL_STATE__" in html
        
        print(f"\n  {city_name}:")
        print(f"    Status: {resp.status_code}")
        print(f"    Time: {elapsed:.0f}ms")
        print(f"    Has __NEXT_DATA__: {has_next}")
        print(f"    Has __INITIAL_STATE__: {has_init}")
        
        if has_next:
            nd = parse_next_data(html)
            venues = extract_venues_from_next_data(nd)
            print(f"    Venues: {len(venues)}")
except ImportError:
    print("  cloudscraper not installed — skipping")
except Exception as e:
    print(f"  cloudscraper error: {e}")

print("\n" + "=" * 80)
print("ALL TESTS COMPLETE")
print("=" * 80)
