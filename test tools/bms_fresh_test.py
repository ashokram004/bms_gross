"""Test fresh driver per city vs driver pool for BMS Cloudflare behavior."""
import time, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent

BMS_TPL = "https://in.bookmyshow.com/movies/{}/dhurandhar-the-revenge/buytickets/ET00478890/20260321"

CITIES = [
    ("Bengaluru",  "bengaluru"),
    ("Mysuru",     "mysuru-mysore"),
    ("Hyderabad",  "hyderabad"),
    ("Hubballi",   "hubballi-hubli"),
    ("Mangaluru",  "mangaluru-mangalore"),
    ("Anekal",     "anekal"),
    ("Tumakuru",   "tumakuru-tumkur"),
    ("Udupi",      "udupi"),
]

def make_driver():
    ua = UserAgent()
    options = Options()
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.page_load_strategy = "normal"
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    d = webdriver.Chrome(options=options)
    d.set_page_load_timeout(25)
    d.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
    d.execute_cdp_cmd("Network.enable", {})
    d.execute_cdp_cmd("Network.setBlockedURLs", {
        "urls": ["*google*","*facebook*","*analytics*","*.woff","*.woff2","*.ttf","*doubleclick*","*gtag*"]
    })
    return d

def parse_venues(html):
    if "Cloudflare" in html[:1000] and "blocked" in html[:1000]:
        return -2, "CF_BLOCKED"
    m = "window.__INITIAL_STATE__"
    s = html.find(m)
    if s == -1:
        return -1, "no_state"
    s = html.find("{", s)
    bc = 0; e = s
    while e < len(html):
        if html[e] == "{": bc += 1
        elif html[e] == "}": bc -= 1
        if bc == 0: break
        e += 1
    try:
        state = json.loads(html[s:e+1])
        sbe = state.get("showtimesByEvent", {})
        dc = sbe.get("currentDateCode")
        if dc:
            widgets = sbe["showDates"][dc]["dynamic"]["data"]["showtimeWidgets"]
            for w in widgets:
                if w.get("type") == "groupList":
                    for g in w["data"]:
                        if g.get("type") == "venueGroup":
                            return len(g["data"]), "ok"
    except:
        pass
    return 0, "no_shows"

def test_city_fresh(args):
    name, slug = args
    driver = make_driver()
    t0 = time.monotonic()
    try:
        driver.get(BMS_TPL.format(slug))
        html = driver.page_source
        elapsed = (time.monotonic() - t0) * 1000
        v, status = parse_venues(html)
        return name, elapsed, v, status, len(html)
    except Exception as e:
        return name, (time.monotonic()-t0)*1000, -3, str(e)[:50], 0
    finally:
        driver.quit()

print("=" * 70)
print("TEST: Fresh driver per city, 4 parallel workers")
print("=" * 70)
t_start = time.monotonic()
with ThreadPoolExecutor(max_workers=4) as ex:
    futs = [ex.submit(test_city_fresh, c) for c in CITIES]
    for f in as_completed(futs):
        name, ms, v, status, sz = f.result()
        print(f"  {name:<15}: {ms:>6.0f}ms | venues={v:>3} | {status} | html={sz}")
total = time.monotonic() - t_start
print(f"\nTotal wall time: {total:.1f}s for {len(CITIES)} cities with 4 workers")
print(f"Avg per city: {total/len(CITIES)*4:.1f}s (per worker slot)")
