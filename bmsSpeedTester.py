"""
BMS Rate Limit & Speed Tester
=============================
Empirically tests BMS seat layout API to determine:
1. Max requests/second before 429
2. Optimal concurrency level
3. Rate limit recovery time
4. Whether rotating UA / multiple sessions help
"""

import json
import time
import os
import sys
import requests
import threading
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from fake_useragent import UserAgent
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv
load_dotenv()

# ── Config ──
ENCRYPTION_KEY = "kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"
API_URL = "https://services-in.bookmyshow.com/doTrans.aspx"
BMS_PAGE_URL = "https://in.bookmyshow.com/movies/bengaluru/dhurandhar-the-revenge/buytickets/ET00478890/20260321"

_thread_local = threading.local()
ua = UserAgent()


def _create_chrome_driver():
    options = Options()
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--headless")
    options.add_argument("start-maximized")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-site-isolation-trials")
    options.add_argument("disable-csp")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=options)


def extract_initial_state_from_page(driver, url):
    driver.get(url)
    html = driver.page_source
    marker = "window.__INITIAL_STATE__"
    start = html.find(marker)
    if start == -1:
        return None
    start = html.find("{", start)
    brace_count, end = 0, start
    while end < len(html):
        if html[end] == "{":
            brace_count += 1
        elif html[end] == "}":
            brace_count -= 1
        if brace_count == 0:
            break
        end += 1
    return json.loads(html[start:end + 1])


def extract_venues(state):
    try:
        sbe = state["showtimesByEvent"]
        date_code = sbe["currentDateCode"]
        widgets = sbe["showDates"][date_code]["dynamic"]["data"]["showtimeWidgets"]
        for widget in widgets:
            if widget.get("type") == "groupList":
                for group in widget["data"]:
                    if group.get("type") == "venueGroup":
                        return group["data"]
    except (KeyError, TypeError):
        pass
    return []


def collect_test_targets(venues, max_targets=50):
    """Collect venue_code + session_id pairs for testing."""
    targets = []
    for v in venues:
        v_code = v["additionalData"]["venueCode"]
        v_name = v["additionalData"]["venueName"]
        for show in v.get("showtimes", []):
            sid = str(show["additionalData"]["sessionId"])
            targets.append((v_code, sid, v_name))
            if len(targets) >= max_targets:
                return targets
    return targets


def make_bms_request(venue_code, session_id, session=None):
    """Single BMS API request. Returns (success, status_code, elapsed_ms, error)."""
    payload = (
        f"strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode={venue_code}"
        f"&lngTransactionIdentifier=0&strParam1={session_id}"
        f"&strParam2=WEB&strParam5=Y&strFormat=json"
    )
    
    if session is None:
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": ua.random,
            "Origin": "https://in.bookmyshow.com",
            "Referer": "https://in.bookmyshow.com/",
        })
    
    t0 = time.monotonic()
    try:
        resp = session.post(API_URL, data=payload, timeout=15)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        
        if resp.status_code == 429:
            return False, 429, elapsed_ms, "Rate Limited"
        
        if resp.status_code != 200:
            return False, resp.status_code, elapsed_ms, f"HTTP {resp.status_code}"
        
        data = resp.json().get("BookMyShow", {})
        if data.get("blnSuccess") == "true":
            return True, 200, elapsed_ms, None
        
        error_msg = data.get("strException", "unknown")
        is_rate_limit = any(kw in error_msg.lower() for kw in ["rate limit", "connectivity issue", "high demand"])
        if is_rate_limit:
            return False, 200, elapsed_ms, f"Soft rate limit: {error_msg[:60]}"
        
        return False, 200, elapsed_ms, error_msg[:60]
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return False, 0, elapsed_ms, "Timeout"
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return False, 0, elapsed_ms, str(e)[:60]


# ═══════════════════════════════════════════════════════
# TEST 1: Sequential burst — find rate limit boundary
# ═══════════════════════════════════════════════════════
def test_sequential_burst(targets, num_requests=30):
    """Fire requests as fast as possible sequentially."""
    print(f"\n{'='*70}")
    print(f"TEST 1: Sequential Burst — {num_requests} requests, no delay")
    print(f"{'='*70}")
    
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": ua.random,
        "Origin": "https://in.bookmyshow.com",
        "Referer": "https://in.bookmyshow.com/",
    })
    
    results = []
    rate_limited_at = None
    t_start = time.monotonic()
    
    for i in range(min(num_requests, len(targets))):
        v_code, sid, _ = targets[i % len(targets)]
        success, status, ms, err = make_bms_request(v_code, sid, session)
        elapsed_total = time.monotonic() - t_start
        
        marker = "✅" if success else ("🛑" if status == 429 or (err and "rate limit" in str(err).lower()) else "❌")
        print(f"  {marker} #{i+1:>3} | {ms:>5}ms | Status: {status} | {err or 'OK'}")
        
        results.append({
            "index": i+1, "success": success, "status": status,
            "ms": ms, "error": err, "total_elapsed": elapsed_total
        })
        
        if (status == 429 or (err and "rate limit" in str(err).lower())) and rate_limited_at is None:
            rate_limited_at = i + 1
    
    total_time = time.monotonic() - t_start
    successes = sum(1 for r in results if r["success"])
    rate_limits = sum(1 for r in results if r["status"] == 429 or (r["error"] and "rate limit" in str(r["error"]).lower()))
    avg_ms = sum(r["ms"] for r in results) / len(results) if results else 0
    
    print(f"\n  📊 Results:")
    print(f"     Total time:      {total_time:.1f}s")
    print(f"     Successful:      {successes}/{len(results)}")
    print(f"     Rate limited:    {rate_limits}")
    print(f"     Avg response:    {avg_ms:.0f}ms")
    print(f"     Requests/sec:    {len(results)/total_time:.1f}")
    if rate_limited_at:
        print(f"     First 429 at:    request #{rate_limited_at}")
    
    return results, rate_limited_at


# ═══════════════════════════════════════════════════════
# TEST 2: Timed intervals — find safe RPS
# ═══════════════════════════════════════════════════════
def test_timed_intervals(targets, rps_values=None):
    """Test specific requests-per-second rates."""
    if rps_values is None:
        rps_values = [2, 4, 6, 8, 10, 15, 20]
    
    print(f"\n{'='*70}")
    print(f"TEST 2: Timed Intervals — testing RPS: {rps_values}")
    print(f"{'='*70}")
    
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": ua.random,
        "Origin": "https://in.bookmyshow.com",
        "Referer": "https://in.bookmyshow.com/",
    })
    
    rps_results = {}
    
    for rps in rps_values:
        interval = 1.0 / rps
        num_requests = min(15, len(targets))  # 15 requests per RPS level
        
        print(f"\n  ⏱️  Testing {rps} RPS (interval: {interval*1000:.0f}ms)...")
        successes = 0
        rate_limits = 0
        total_ms = 0
        
        for i in range(num_requests):
            t_req_start = time.monotonic()
            v_code, sid, _ = targets[i % len(targets)]
            success, status, ms, err = make_bms_request(v_code, sid, session)
            total_ms += ms
            
            if success:
                successes += 1
            if status == 429 or (err and "rate limit" in str(err).lower()):
                rate_limits += 1
            
            # Maintain the target interval
            elapsed = time.monotonic() - t_req_start
            sleep_needed = interval - elapsed
            if sleep_needed > 0:
                time.sleep(sleep_needed)
        
        avg_ms = total_ms / num_requests
        print(f"     ✅ {successes}/{num_requests} success | 🛑 {rate_limits} rate limits | Avg: {avg_ms:.0f}ms")
        
        rps_results[rps] = {
            "successes": successes, "rate_limits": rate_limits,
            "total": num_requests, "avg_ms": avg_ms
        }
        
        # If we got rate limited, wait before next test
        if rate_limits > 0:
            print(f"     ⏳ Rate limited — waiting 15s before next test...")
            time.sleep(15)
    
    # Find optimal RPS
    safe_rps = max(
        (rps for rps, data in rps_results.items() if data["rate_limits"] == 0),
        default=0
    )
    print(f"\n  📊 Optimal safe RPS (no rate limits): {safe_rps}")
    return rps_results, safe_rps


# ═══════════════════════════════════════════════════════
# TEST 3: Concurrent requests — thread scaling
# ═══════════════════════════════════════════════════════
def test_concurrent(targets, thread_counts=None):
    """Test different concurrency levels."""
    if thread_counts is None:
        thread_counts = [1, 2, 3, 5, 8]
    
    print(f"\n{'='*70}")
    print(f"TEST 3: Concurrent Requests — threads: {thread_counts}")
    print(f"{'='*70}")
    
    concurrency_results = {}
    
    for num_threads in thread_counts:
        num_requests = min(15, len(targets))
        
        print(f"\n  🧵 Testing {num_threads} threads, {num_requests} requests...")
        
        results_list = []
        
        def worker(idx):
            # Each thread gets its own session
            s = requests.Session()
            s.headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": ua.random,
                "Origin": "https://in.bookmyshow.com",
                "Referer": "https://in.bookmyshow.com/",
            })
            v_code, sid, _ = targets[idx % len(targets)]
            return make_bms_request(v_code, sid, s)
        
        t_start = time.monotonic()
        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(worker, i) for i in range(num_requests)]
            for f in as_completed(futures):
                results_list.append(f.result())
        total_time = time.monotonic() - t_start
        
        successes = sum(1 for s, _, _, _ in results_list if s)
        rate_limits = sum(1 for _, st, _, e in results_list if st == 429 or (e and "rate limit" in str(e).lower()))
        avg_ms = sum(ms for _, _, ms, _ in results_list) / len(results_list)
        throughput = len(results_list) / total_time
        
        print(f"     ✅ {successes}/{num_requests} | 🛑 {rate_limits} rate limits | "
              f"Avg: {avg_ms:.0f}ms | Throughput: {throughput:.1f} req/s | Wall: {total_time:.1f}s")
        
        concurrency_results[num_threads] = {
            "successes": successes, "rate_limits": rate_limits,
            "total": num_requests, "avg_ms": avg_ms,
            "throughput": throughput, "wall_time": total_time
        }
        
        if rate_limits > 0:
            print(f"     ⏳ Rate limited — waiting 15s before next test...")
            time.sleep(15)
    
    return concurrency_results


# ═══════════════════════════════════════════════════════
# TEST 4: Rate limit recovery time
# ═══════════════════════════════════════════════════════
def test_recovery_time(targets):
    """After getting rate limited, test how quickly we can resume."""
    print(f"\n{'='*70}")
    print(f"TEST 4: Rate Limit Recovery Time")
    print(f"{'='*70}")
    
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": ua.random,
        "Origin": "https://in.bookmyshow.com",
        "Referer": "https://in.bookmyshow.com/",
    })
    
    # First, trigger a rate limit by firing fast
    print("  Step 1: Triggering rate limit with rapid-fire burst...")
    rate_hit = False
    for i in range(50):
        v_code, sid, _ = targets[i % len(targets)]
        success, status, ms, err = make_bms_request(v_code, sid, session)
        if status == 429 or (err and "rate limit" in str(err).lower()):
            print(f"     Rate limited at request #{i+1}")
            rate_hit = True
            break
    
    if not rate_hit:
        print("     ⚠️  Couldn't trigger rate limit in 50 requests — BMS may not rate limit sequential requests")
        return None
    
    # Now test recovery at different intervals
    wait_times = [3, 5, 8, 10, 15, 20, 30]
    print(f"\n  Step 2: Testing recovery after wait times: {wait_times}s")
    
    recovery_results = {}
    for wait in wait_times:
        print(f"\n     Waiting {wait}s...", end="", flush=True)
        time.sleep(wait)
        
        v_code, sid, _ = targets[0]
        success, status, ms, err = make_bms_request(v_code, sid, session)
        recovered = success or (status == 200)
        
        marker = "✅" if recovered else "🛑"
        print(f" {marker} Status: {status} | {ms}ms | {err or 'OK'}")
        recovery_results[wait] = {"recovered": recovered, "status": status, "ms": ms}
        
        if recovered:
            # Trigger rate limit again for next test
            for i in range(50):
                v_code2, sid2, _ = targets[i % len(targets)]
                s2, st2, _, e2 = make_bms_request(v_code2, sid2, session)
                if st2 == 429 or (e2 and "rate limit" in str(e2).lower()):
                    break
    
    min_recovery = min((w for w, r in recovery_results.items() if r["recovered"]), default=None)
    print(f"\n  📊 Minimum recovery time: {min_recovery}s" if min_recovery else "\n  📊 No recovery observed")
    return recovery_results


# ═══════════════════════════════════════════════════════
# TEST 5: Different User-Agents
# ═══════════════════════════════════════════════════════
def test_ua_rotation(targets):
    """Test if using different User-Agents avoids rate limits."""
    print(f"\n{'='*70}")
    print(f"TEST 5: User-Agent Rotation — fresh session per request")
    print(f"{'='*70}")
    
    num_requests = min(20, len(targets))
    results = []
    
    t_start = time.monotonic()
    for i in range(num_requests):
        # Brand new session + random UA each time 
        s = requests.Session()
        s.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": ua.random,
            "Origin": "https://in.bookmyshow.com",
            "Referer": "https://in.bookmyshow.com/",
        })
        v_code, sid, _ = targets[i % len(targets)]
        success, status, ms, err = make_bms_request(v_code, sid, s)
        
        marker = "✅" if success else ("🛑" if status == 429 else "❌")
        print(f"  {marker} #{i+1:>3} | {ms:>5}ms | {err or 'OK'}")
        results.append({"success": success, "status": status, "ms": ms})
    
    total_time = time.monotonic() - t_start
    successes = sum(1 for r in results if r["success"])
    rate_limits = sum(1 for r in results if r["status"] == 429)
    
    print(f"\n  📊 {successes}/{num_requests} success | {rate_limits} rate limits | {total_time:.1f}s total")
    return results


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🔬 BMS Rate Limit & Speed Tester")
    print("=" * 70)
    
    # Step 1: Load page and collect test targets
    print("\n📡 Loading BMS page to collect venue/show data...")
    driver = _create_chrome_driver()
    try:
        state_data = extract_initial_state_from_page(driver, BMS_PAGE_URL)
        venues = extract_venues(state_data) if state_data else []
        print(f"   Found {len(venues)} venues")
        
        targets = collect_test_targets(venues, max_targets=50)
        print(f"   Collected {len(targets)} test targets (venue+show pairs)")
        
        if not targets:
            print("❌ No valid targets found. Is the movie available in this city?")
            driver.quit()
            sys.exit(1)
        
        # Print first few targets
        for i, (vc, sid, name) in enumerate(targets[:5]):
            print(f"   #{i+1}: {name[:30]} | venue={vc} | sid={sid}")
    finally:
        driver.quit()
    
    if len(targets) < 5:
        print(f"⚠️  Only {len(targets)} targets — some tests may be limited")
    
    # ── Run Tests ──
    print(f"\n🧪 Running {5} tests with {len(targets)} targets...\n")
    
    # Test 1: Sequential burst
    burst_results, burst_limit = test_sequential_burst(targets, num_requests=30)
    
    # Brief cooldown
    print("\n⏳ Cooling down 10s...")
    time.sleep(10)
    
    # Test 2: Timed intervals
    interval_results, safe_rps = test_timed_intervals(targets)
    
    # Brief cooldown
    print("\n⏳ Cooling down 10s...")
    time.sleep(10)
    
    # Test 3: Concurrent threads
    concurrent_results = test_concurrent(targets)
    
    # Brief cooldown
    print("\n⏳ Cooling down 10s...")
    time.sleep(10)
    
    # Test 4: Recovery time
    recovery_results = test_recovery_time(targets)
    
    # Brief cooldown
    print("\n⏳ Cooling down 10s...")
    time.sleep(10)
    
    # Test 5: UA rotation
    ua_results = test_ua_rotation(targets)
    
    # ══════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ══════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"📋 FINAL SUMMARY")
    print(f"{'='*70}")
    
    print(f"\n  1. Sequential Burst:  First rate limit at request #{burst_limit or 'NONE (no limit hit)'}")
    print(f"  2. Safe Sequential RPS: {safe_rps}")
    
    if concurrent_results:
        best_threads = max(concurrent_results.items(), key=lambda x: x[1]["throughput"] if x[1]["rate_limits"] == 0 else 0)
        print(f"  3. Best Concurrency:  {best_threads[0]} threads ({best_threads[1]['throughput']:.1f} req/s)")
    
    if recovery_results:
        min_recovery = min((w for w, r in recovery_results.items() if r["recovered"]), default="N/A")
        print(f"  4. Min Recovery Time: {min_recovery}s")
    
    ua_ok = sum(1 for r in ua_results if r["success"]) if ua_results else 0
    ua_total = len(ua_results) if ua_results else 0
    print(f"  5. UA Rotation:       {ua_ok}/{ua_total} success")
    
    print(f"\n{'='*70}")
    print(f"🏁 Done!")
