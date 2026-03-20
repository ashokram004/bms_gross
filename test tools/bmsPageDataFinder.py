"""Find where BMS page stores venue/show data in the HTML."""
import time
import json
import re
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

# Load with normal + wait for JS
print("Loading page...")
t0 = time.monotonic()
driver.get(url)
time.sleep(2)  # Extra wait for XHR data
html = driver.page_source
elapsed = (time.monotonic() - t0) * 1000
print(f"Page loaded in {elapsed:.0f}ms, HTML: {len(html)} chars")

# Search for venue-related markers
markers = [
    "venueCode", "venueName", "sessionId", "GETSEATLAYOUT",
    "showtimesByEvent", "showtimeWidgets", "venueGroup",
    "groupList", "availStatus", "areaCatCode", "curPrice",
    "buytickets", "__NEXT_DATA__", "__INITIAL_STATE__",
    "self.__next_f", "showtimes", "currentDateCode",
    "window.__INITIAL_STATE__", "window.__NEXT_DATA__",
    "showDates", "dynamic", "static",
]

print("\nMarker search:")
for m in markers:
    count = html.count(m)
    if count > 0:
        idx = html.find(m)
        context = html[max(0,idx-50):idx+len(m)+50]
        context = context.replace('\n', '\\n').replace('\r', '')
        print(f"  '{m}': {count} occurrences, first at index {idx}")
        print(f"    Context: ...{context}...")

# Check if there's JSON data in script tags
print("\n\nScript tags analysis:")
script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
scripts = script_pattern.findall(html)
print(f"  Found {len(scripts)} script tags")
for i, script_body in enumerate(scripts):
    sl = len(script_body)
    if sl > 100:  # Only large scripts
        # Check for data indicators
        has_venue = "venue" in script_body.lower()
        has_show = "showtime" in script_body.lower()
        has_session = "sessionId" in script_body or "session_id" in script_body
        has_state = "__INITIAL_STATE__" in script_body
        has_next = "__next_f" in script_body or "__NEXT" in script_body
        
        flags = []
        if has_venue: flags.append("VENUE")
        if has_show: flags.append("SHOWTIME")
        if has_session: flags.append("SESSION")
        if has_state: flags.append("STATE")
        if has_next: flags.append("NEXT")
        
        if flags or sl > 5000:
            print(f"  Script {i}: {sl} chars {'| FLAGS: ' + ', '.join(flags) if flags else ''}")
            print(f"    First 200: {script_body[:200].replace(chr(10), '\\n')}")

# Try executing JS to get data directly
print("\n\nDirect JS extraction attempt:")
try:
    # Try getting __INITIAL_STATE__ via JS execution instead of page source parsing
    result = driver.execute_script("return JSON.stringify(Object.keys(window.__INITIAL_STATE__ || {}))")
    print(f"  __INITIAL_STATE__ keys (via JS): {result}")
except Exception as e:
    print(f"  __INITIAL_STATE__ JS error: {e}")

# Look for React/Next.js data stores
try:
    result = driver.execute_script("""
        var data = {};
        // Check for various data stores
        if (window.__NEXT_DATA__) data.NEXT_DATA_keys = Object.keys(window.__NEXT_DATA__);
        if (window.__INITIAL_STATE__) data.INITIAL_STATE_keys = Object.keys(window.__INITIAL_STATE__);
        if (window.__APP_DATA__) data.APP_DATA = true;
        if (window.__APOLLO_STATE__) data.APOLLO_STATE = true;
        if (window.__RELAY_STORE__) data.RELAY = true;
        
        // Check for showtime data specifically
        var state = window.__INITIAL_STATE__;
        if (state) {
            for (var key in state) {
                var val = state[key];
                if (typeof val === 'object' && val !== null) {
                    data['state.' + key + '.keys'] = Object.keys(val).slice(0, 10);
                }
            }
        }
        
        // Check for self.__next_f (RSC payloads)
        if (typeof self !== 'undefined' && self.__next_f) {
            data.next_f_count = self.__next_f.length;
        }
        
        return JSON.stringify(data, null, 2);
    """)
    print(f"  Window data stores:\n{result}")
except Exception as e:
    print(f"  Window data error: {e}")

# Try to find showtimesByEvent in ANY JS variable
try:
    result = driver.execute_script("""
        // Deep search for showtimesByEvent
        function findKey(obj, target, path, depth) {
            if (depth > 5) return null;
            if (!obj || typeof obj !== 'object') return null;
            for (var key in obj) {
                if (key === target) return path + '.' + key;
                if (typeof obj[key] === 'object' && obj[key] !== null) {
                    var found = findKey(obj[key], target, path + '.' + key, depth + 1);
                    if (found) return found;
                }
            }
            return null;
        }
        
        var result = findKey(window.__INITIAL_STATE__, 'showtimesByEvent', 'state', 0);
        if (!result) result = findKey(window.__NEXT_DATA__, 'showtimesByEvent', 'next', 0);
        return result || 'NOT FOUND';
    """)
    print(f"  showtimesByEvent path: {result}")
except Exception as e:
    print(f"  search error: {e}")

# Check for XHR-loaded data by looking at performance entries
try:
    result = driver.execute_script("""
        var entries = performance.getEntriesByType('resource');
        var apiCalls = entries.filter(function(e) {
            return e.name.includes('api') || e.name.includes('showtime') || 
                   e.name.includes('venue') || e.name.includes('buyticket') ||
                   e.name.includes('doTrans') || e.name.includes('graphql') ||
                   e.name.includes('session') || e.name.includes('event');
        });
        return JSON.stringify(apiCalls.map(function(e) {
            return {name: e.name.substring(0, 150), duration: Math.round(e.duration), size: e.transferSize};
        }), null, 2);
    """)
    print(f"\n  API/data network calls:\n{result}")
except Exception as e:
    print(f"  Network analysis error: {e}")

# Also get ALL XHR/fetch resource URLs (not just filtered ones)
try:
    result = driver.execute_script("""
        var entries = performance.getEntriesByType('resource');
        var xhrFetch = entries.filter(function(e) {
            return e.initiatorType === 'xmlhttprequest' || e.initiatorType === 'fetch';
        });
        return JSON.stringify(xhrFetch.map(function(e) {
            return {url: e.name.substring(0, 200), duration: Math.round(e.duration), size: e.transferSize, type: e.initiatorType};
        }), null, 2);
    """)
    print(f"\n  XHR/Fetch calls:\n{result}")
except Exception as e:
    print(f"  XHR analysis error: {e}")

driver.quit()
print("\nDone.")
