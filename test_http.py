"""Quick test to verify HTTP requests work for District and BMS pages."""
import requests
import json
from fake_useragent import UserAgent

ua = UserAgent()
s = requests.Session()
s.headers.update({
    'User-Agent': ua.random,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
})

print("=" * 60)
print("TEST 1: District Mumbai")
print("=" * 60)
url = 'https://www.district.in/movies/dhurandhar-the-revenge-movie-tickets-in-mumbai-MV211577?frmtid=TVQjMJQmE&fromdate=2026-03-18'
resp = s.get(url, timeout=15)
print(f"Status: {resp.status_code}")
print(f"HTML length: {len(resp.text)}")
print(f"Final URL: {resp.url}")
has_next = 'id="__NEXT_DATA__"' in resp.text
print(f"Has __NEXT_DATA__: {has_next}")
if has_next:
    html = resp.text
    marker = 'id="__NEXT_DATA__"'
    idx = html.find(marker)
    start = html.find('>', idx) + 1
    end = html.find('</script>', start)
    data = json.loads(html[start:end])
    try:
        sessions = data['props']['pageProps']['data']['serverState']['movieSessions']
        key = list(sessions.keys())[0]
        cinemas = sessions[key].get('arrangedSessions', [])
        print(f"Cinemas found: {len(cinemas)}")
        if cinemas:
            print(f"First cinema: {cinemas[0]['entityName']}")
    except Exception as e:
        print(f"Parse error: {e}")
        # Check what keys exist
        print(f"pageProps keys: {list(data.get('props', {}).get('pageProps', {}).keys())}")
else:
    print(f"First 1000 chars:\n{resp.text[:1000]}")

print()
print("=" * 60)
print("TEST 2: BMS Hyderabad")
print("=" * 60)
bms_url = 'https://in.bookmyshow.com/movies/hyderabad/dhurandhar-the-revenge/buytickets/ET00478890/20260318'
resp2 = s.get(bms_url, timeout=15)
print(f"Status: {resp2.status_code}")
print(f"HTML length: {len(resp2.text)}")
print(f"Final URL: {resp2.url}")
has_state = "window.__INITIAL_STATE__" in resp2.text
print(f"Has __INITIAL_STATE__: {has_state}")
if not has_state:
    # Check what we got
    print(f"First 1000 chars:\n{resp2.text[:1000]}")
