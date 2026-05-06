"""Quick debug: dump __INITIAL_STATE__ keys from BMS page."""
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent

url = "https://in.bookmyshow.com/movies/bangalore/dhurandhar-the-revenge/buytickets/ET00478890/20260321"

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
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
prefs = {
    "profile.managed_default_content_settings.images": 2,
    "profile.default_content_setting_values.notifications": 2,
}
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(30)
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
})

# ---- Test with NORMAL strategy (match real code) ----
print("Loading page (normal strategy)...")
t0 = time.monotonic()
driver.get(url)
time.sleep(1)  # Match real code
html = driver.page_source
elapsed = (time.monotonic() - t0) * 1000
print(f"  Page loaded in {elapsed:.0f}ms, HTML: {len(html)} chars")

# Parse __INITIAL_STATE__
marker = "window.__INITIAL_STATE__"
start = html.find(marker)
if start == -1:
    print("  __INITIAL_STATE__ NOT FOUND!")
    # Check for __NEXT_DATA__
    nd_marker = '"__NEXT_DATA__"'
    if nd_marker in html:
        print("  __NEXT_DATA__ found instead")
    driver.quit()
    exit()

print(f"  __INITIAL_STATE__ found at index {start}")
start = html.find("{", start)
brace_count = 0; end = start
while end < len(html):
    if html[end] == "{": brace_count += 1
    elif html[end] == "}": brace_count -= 1
    if brace_count == 0: break
    end += 1

state_json = html[start:end + 1]
print(f"  JSON length: {len(state_json)} chars")

try:
    state = json.loads(state_json)
except json.JSONDecodeError as e:
    print(f"  JSON parse error: {e}")
    print(f"  First 200 chars: {state_json[:200]}")
    driver.quit()
    exit()

# Dump top-level keys
print(f"\n  Top-level keys: {list(state.keys())}")

# Check showtimesByEvent
if "showtimesByEvent" in state:
    sbe = state["showtimesByEvent"]
    print(f"  showtimesByEvent keys: {list(sbe.keys())}")
    date_code = sbe.get("currentDateCode")
    print(f"  currentDateCode: {date_code}")
    if date_code and date_code in sbe.get("showDates", {}):
        sd = sbe["showDates"][date_code]
        print(f"  showDates[{date_code}] keys: {list(sd.keys())}")
        if "dynamic" in sd:
            dyn = sd["dynamic"]
            print(f"  dynamic keys: {list(dyn.keys())}")
            if "data" in dyn:
                ddata = dyn["data"]
                print(f"  dynamic.data keys: {list(ddata.keys())}")
                if "showtimeWidgets" in ddata:
                    widgets = ddata["showtimeWidgets"]
                    print(f"  showtimeWidgets: {len(widgets)} widgets")
                    for i, w in enumerate(widgets):
                        wtype = w.get("type", "?")
                        print(f"    Widget {i}: type={wtype}")
                        if wtype == "groupList":
                            groups = w.get("data", [])
                            print(f"      groupList has {len(groups)} groups")
                            for j, g in enumerate(groups):
                                gtype = g.get("type", "?")
                                gdata = g.get("data", [])
                                print(f"        Group {j}: type={gtype}, items={len(gdata)}")
                                if gtype == "venueGroup" and gdata:
                                    v0 = gdata[0]
                                    ad = v0.get("additionalData", {})
                                    print(f"          First venue: {ad.get('venueName', 'N/A')}, code={ad.get('venueCode', 'N/A')}")
                                    shows = v0.get("showtimes", [])
                                    print(f"          Shows: {len(shows)}")
                                    if shows:
                                        s0 = shows[0]
                                        print(f"          First show: {s0.get('title', 'N/A')}, sid={s0.get('additionalData', {}).get('sessionId', 'N/A')}")
                else:
                    print(f"  No showtimeWidgets in dynamic.data")
        elif "static" in sd:
            print(f"  Has 'static' instead of 'dynamic'")
            print(f"  static keys: {list(sd['static'].keys())}")
    elif sbe.get("showDates"):
        print(f"  Available showDates: {list(sbe['showDates'].keys())}")
    else:
        print(f"  No showDates found")
else:
    print("  No 'showtimesByEvent' key!")
    # Look for similar keys
    for key in state.keys():
        if "show" in key.lower() or "venue" in key.lower() or "event" in key.lower():
            print(f"  Interesting key: {key}")
            val = state[key]
            if isinstance(val, dict):
                print(f"    Sub-keys: {list(val.keys())[:20]}")

# ---- Test eager strategy + driver reuse ----
print("\n\n--- Testing EAGER mode + driver reuse ---")
driver.quit()

options2 = Options()
options2.add_argument(f"user-agent={ua.random}")
options2.add_argument("--headless=new")
options2.add_argument("start-maximized")
options2.add_argument("--disable-web-security")
options2.add_argument("--disable-site-isolation-trials")
options2.add_argument("--disable-blink-features=AutomationControlled")
options2.add_argument("--no-sandbox")
options2.add_argument("--disable-dev-shm-usage")
options2.add_argument("disable-csp")
options2.page_load_strategy = 'eager'
prefs2 = {
    "profile.managed_default_content_settings.images": 2,
    "profile.default_content_setting_values.notifications": 2,
}
options2.add_experimental_option("prefs", prefs2)
options2.add_experimental_option("excludeSwitches", ["enable-automation"])
options2.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(options=options2)
driver.set_page_load_timeout(30)
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
})

# First city
t0 = time.monotonic()
driver.get(url)
time.sleep(0.5)  # Brief wait for JS
html = driver.page_source
elapsed = (time.monotonic() - t0) * 1000
has_init = "__INITIAL_STATE__" in html
print(f"  Bangalore (eager): {elapsed:.0f}ms, __INITIAL_STATE__: {has_init}, HTML: {len(html)}")

if has_init:
    start = html.find("window.__INITIAL_STATE__")
    start = html.find("{", start)
    brace_count = 0; end = start
    while end < len(html):
        if html[end] == "{": brace_count += 1
        elif html[end] == "}": brace_count -= 1
        if brace_count == 0: break
        end += 1
    state = json.loads(html[start:end + 1])
    sbe = state.get("showtimesByEvent", {})
    dc = sbe.get("currentDateCode")
    print(f"  showtimesByEvent exists: {'showtimesByEvent' in state}, dateCode: {dc}")
    if dc and dc in sbe.get("showDates", {}):
        sd = sbe["showDates"][dc]
        print(f"  showDates keys: {list(sd.keys())}")
        if "dynamic" in sd:
            ddata = sd["dynamic"].get("data", {})
            widgets = ddata.get("showtimeWidgets", [])
            print(f"  Widgets: {len(widgets)}")
            for w in widgets:
                if w.get("type") == "groupList":
                    for g in w.get("data", []):
                        if g.get("type") == "venueGroup":
                            venues = g.get("data", [])
                            print(f"  VENUES FOUND: {len(venues)}")
        else:
            print(f"  Keys in showDates[{dc}]: {list(sd.keys())}")

# Reuse for 5 cities
test_cities = [
    ("Mysore", "https://in.bookmyshow.com/movies/mysore/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
    ("Hubli", "https://in.bookmyshow.com/movies/hubli/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
    ("Mangalore", "https://in.bookmyshow.com/movies/mangalore/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
    ("Belgaum", "https://in.bookmyshow.com/movies/belgaum/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
    ("Shimoga", "https://in.bookmyshow.com/movies/shimoga/dhurandhar-the-revenge/buytickets/ET00478890/20260321"),
]

print(f"\n  --- Reuse test: 5 cities with same driver ---")
for city, city_url in test_cities:
    t0 = time.monotonic()
    driver.get(city_url)
    time.sleep(0.5)
    html = driver.page_source
    elapsed = (time.monotonic() - t0) * 1000
    has_init = "__INITIAL_STATE__" in html
    
    venue_count = 0
    if has_init:
        start = html.find("window.__INITIAL_STATE__")
        start = html.find("{", start)
        brace_count = 0; end = start
        while end < len(html):
            if html[end] == "{": brace_count += 1
            elif html[end] == "}": brace_count -= 1
            if brace_count == 0: break
            end += 1
        try:
            st = json.loads(html[start:end + 1])
            sbe = st.get("showtimesByEvent", {})
            dc = sbe.get("currentDateCode")
            if dc and dc in sbe.get("showDates", {}):
                sd = sbe["showDates"][dc]
                if "dynamic" in sd:
                    ddata = sd["dynamic"].get("data", {})
                    for w in ddata.get("showtimeWidgets", []):
                        if w.get("type") == "groupList":
                            for g in w.get("data", []):
                                if g.get("type") == "venueGroup":
                                    venue_count = len(g.get("data", []))
        except:
            pass
    
    print(f"    {city:<15}: {elapsed:.0f}ms | __INITIAL_STATE__: {has_init} | Venues: {venue_count}")

driver.quit()
print("\nDone.")
