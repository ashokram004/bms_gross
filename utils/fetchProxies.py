"""
Free Proxy Scraper & Tester for BMS + District
================================================
Fetches free proxy lists from multiple sources, tests each proxy against
both BMS and District endpoints, and saves the working ones to a JSON file.

Run daily/weekly:  python utils/fetchProxies.py

Output:  utils/working_proxies.json
"""

import json
import os
import re
import sys
import time
import threading
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from fake_useragent import UserAgent

# ── CONFIG ───────────────────────────────────────────────────────────────────
PROXY_TEST_TIMEOUT   = 10      # seconds per proxy test
MAX_TEST_WORKERS     = 50      # parallel proxy testers
MAX_ACCEPTABLE_MS    = 5000    # discard proxies slower than this (ms)
OUTPUT_PATH          = os.path.join(os.path.dirname(os.path.abspath(__file__)), "working_proxies.json")

# BMS test: lightweight POST that returns a small JSON (invalid SID = fast error, proves connectivity)
BMS_TEST_URL     = "https://services-in.bookmyshow.com/doTrans.aspx"
BMS_TEST_PAYLOAD = (
    "strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode=TEST"
    "&lngTransactionIdentifier=0&strParam1=0"
    "&strParam2=WEB&strParam5=Y&strFormat=json"
)

# District test: lightweight GET (just need HTTP 200 from the domain)
DISTRICT_TEST_URL = "https://www.district.in/"

ua = UserAgent()


# ── PROXY SOURCES ────────────────────────────────────────────────────────────

def _fetch_url(url, label):
    """GET a URL and return text, or empty string on failure."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": ua.random})
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"   ⚠ [{label}] Failed: {e}")
        return ""


def source_github_lists():
    """Fetch from well-known GitHub-hosted proxy lists (updated hourly/daily by bots)."""
    urls = [
        # ("TheSpeedX/http",  "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"),
        # ("TheSpeedX/socks5","https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"),
        # ("clarketm",        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt"),
        # ("monosans/http",   "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"),
        # ("monosans/socks5", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/socks5.txt"),
        # ("hookzof",         "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"),
        # ("roosterkid",      "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"),
        # ("MuRongPIG/http",  "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt"),
        # ("MuRongPIG/socks5","https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt"),
    ]
    proxies = set()
    for label, url in urls:
        text = _fetch_url(url, label)
        for line in text.strip().splitlines():
            line = line.strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', line):
                proxies.add(line)
    return proxies


def source_proxyscrape():
    """ProxyScrape free API — HTTP and SOCKS5."""
    proxies = set()
    for proto in ["http", "socks5"]:
        url = f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol={proto}&timeout=10000&country=all&ssl=all&anonymity=all"
        text = _fetch_url(url, f"proxyscrape/{proto}")
        for line in text.strip().splitlines():
            line = line.strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', line):
                proxies.add(line)
    return proxies


def source_geonode():
    """GeoNode free proxy API."""
    proxies = set()
    try:
        url = "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc"
        text = _fetch_url(url, "geonode")
        if text:
            data = json.loads(text)
            for p in data.get("data", []):
                ip = p.get("ip")
                port = p.get("port")
                if ip and port:
                    proxies.add(f"{ip}:{port}")
    except Exception as e:
        print(f"   ⚠ [geonode] Parse error: {e}")
    return proxies


def collect_all_proxies():
    """Gather proxies from all sources, deduplicated."""
    print("📡 Fetching proxies from all sources...\n")
    all_proxies = set()

    sources = [
        ("GitHub lists",  source_github_lists),
        ("ProxyScrape",   source_proxyscrape),
        ("GeoNode",       source_geonode),
    ]

    for name, fn in sources:
        try:
            found = fn()
            print(f"   ✅ {name}: {len(found)} proxies")
            all_proxies |= found
        except Exception as e:
            print(f"   ❌ {name}: {e}")

    print(f"\n📊 Total unique proxies collected: {len(all_proxies)}")
    return all_proxies


# ── PROXY TESTING ────────────────────────────────────────────────────────────

def _test_proxy_bms(proxy_str, proxy_type="http"):
    """Test a single proxy against BMS API. Returns response time in ms or None."""
    proxy_url = f"{proxy_type}://{proxy_str}" if "://" not in proxy_str else proxy_str
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        start = time.monotonic()
        r = requests.post(
            BMS_TEST_URL,
            data=BMS_TEST_PAYLOAD,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": ua.random,
            },
            proxies=proxies,
            timeout=PROXY_TEST_TIMEOUT,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        # BMS returns JSON even for invalid requests — we just need non-429 connectivity
        if r.status_code == 200:
            body = r.text
            if "429" in body or "rate limit" in body.lower():
                return None  # proxy itself is rate-limited
            return elapsed_ms
    except Exception:
        pass
    return None


def _test_proxy_district(proxy_str, proxy_type="http"):
    """Test a single proxy against District. Returns response time in ms or None."""
    proxy_url = f"{proxy_type}://{proxy_str}" if "://" not in proxy_str else proxy_str
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        start = time.monotonic()
        r = requests.get(
            DISTRICT_TEST_URL,
            headers={"User-Agent": ua.random},
            proxies=proxies,
            timeout=PROXY_TEST_TIMEOUT,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if r.status_code == 200:
            return elapsed_ms
    except Exception:
        pass
    return None


def test_single_proxy(proxy_str):
    """Test one proxy against BMS and District independently.
    Returns result dict if it works with at least one platform, else None.
    Fields: works_with = 'both' | 'bms_only' | 'district_only'
    """
    # Try HTTP first, then SOCKS5
    for ptype in ["http", "socks5"]:
        bms_ms  = _test_proxy_bms(proxy_str, ptype)
        bms_ok  = bms_ms is not None and bms_ms <= MAX_ACCEPTABLE_MS

        dist_ms = _test_proxy_district(proxy_str, ptype)
        dist_ok = dist_ms is not None and dist_ms <= MAX_ACCEPTABLE_MS

        if not bms_ok and not dist_ok:
            continue  # try next protocol

        # At least one platform works with this protocol
        if bms_ok and dist_ok:
            works_with = "both"
            avg = (bms_ms + dist_ms) // 2
        elif bms_ok:
            works_with = "bms_only"
            avg = bms_ms
        else:
            works_with = "district_only"
            avg = dist_ms

        return {
            "proxy": proxy_str,
            "type": ptype,
            "works_with": works_with,
            "bms_ms": bms_ms if bms_ok else None,
            "district_ms": dist_ms if dist_ok else None,
            "avg_ms": avg,
            "tested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    return None


_file_lock = threading.Lock()


def _read_output_file():
    """Read the output JSON. Returns dict with proxies list and tested set."""
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return {"generated_at": "", "total_working": 0, "total_tested": 0, "tested": [], "proxies": []}


def _write_output_file(data):
    """Write data dict to the output JSON."""
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _save_proxy_result(proxy_str, result=None):
    """Mark a proxy as tested and optionally save it as working (thread-safe)."""
    with _file_lock:
        data = _read_output_file()
        tested_set = set(data.get("tested", []))

        if proxy_str in tested_set:
            return  # already recorded

        tested_set.add(proxy_str)
        data["tested"] = list(tested_set)
        data["total_tested"] = len(tested_set)

        if result:
            existing = {p["proxy"] for p in data["proxies"]}
            if result["proxy"] not in existing:
                data["proxies"].append(result)
                data["total_working"] = len(data["proxies"])

        data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_output_file(data)


def test_all_proxies(proxy_set):
    """Test all proxies in parallel and return the working ones."""
    total_before_skip = len(proxy_set)

    # Load already-tested proxies from previous run to skip them
    already_tested = set()
    if os.path.exists(OUTPUT_PATH):
        data = _read_output_file()
        already_tested = set(data.get("tested", []))

    to_test = proxy_set - already_tested
    skipped = total_before_skip - len(to_test)

    if skipped > 0:
        print(f"\n⏩ Resuming: skipping {skipped} already-tested proxies")

    total = len(to_test)
    if total == 0:
        print("\n✅ All proxies already tested. Nothing to do.")
        # Return previously found working proxies
        data = _read_output_file()
        return data.get("proxies", [])

    print(f"\n🔍 Testing {total} proxies ({MAX_TEST_WORKERS} parallel workers, {PROXY_TEST_TIMEOUT}s timeout)...\n")

    working   = []
    completed = [0]
    start     = time.monotonic()

    # Pre-load working proxies from a partial previous run
    if os.path.exists(OUTPUT_PATH):
        data = _read_output_file()
        working = list(data.get("proxies", []))
        if working:
            print(f"   📂 Carrying forward {len(working)} working proxies from previous run")

    def _test(proxy_str):
        result = test_single_proxy(proxy_str)
        _save_proxy_result(proxy_str, result)  # mark tested + save if working
        completed[0] += 1
        c = completed[0]
        if c % 200 == 0 or c == total:
            elapsed = time.monotonic() - start
            w = len(working)
            print(f"   📊 Progress: {c}/{total} tested | {w} working | {elapsed:.0f}s elapsed")
        return result

    with ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as pool:
        futures = {pool.submit(_test, p): p for p in to_test}
        for f in as_completed(futures):
            try:
                result = f.result()
                if result:
                    working.append(result)
                    proxy = result["proxy"]
                    ptype = result["type"]
                    tag   = result["works_with"].upper()
                    bms_s = f"{result['bms_ms']}ms" if result['bms_ms'] is not None else "—"
                    dst_s = f"{result['district_ms']}ms" if result['district_ms'] is not None else "—"
                    print(f"   ✅ {proxy} ({ptype}) [{tag}] — BMS: {bms_s}, District: {dst_s}")
            except Exception:
                pass

    # Sort by average speed (fastest first)
    working.sort(key=lambda x: x["avg_ms"])
    return working


# ── OUTPUT ───────────────────────────────────────────────────────────────────

def save_results(working, tested_list=None):
    """Final save — re-sort by speed, preserve tested list."""
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_working": len(working),
        "total_tested": len(tested_list) if tested_list else 0,
        "tested": tested_list or [],
        "proxies": working,  # already sorted by avg_ms
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved {len(working)} working proxies (sorted by speed) to: {OUTPUT_PATH}")


def load_existing_proxies():
    """Load previously saved proxies for re-testing."""
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            old = data.get("proxies", [])
            print(f"📂 Loaded {len(old)} previously working proxies for re-testing")
            return {p["proxy"] for p in old}
        except Exception:
            pass
    return set()


# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Free Proxy Scraper & Tester (BMS + District)")
    print("=" * 60)
    print()

    overall_start = time.monotonic()

    # 1. Collect from all sources
    all_proxies = collect_all_proxies()

    # 2. Add previously working proxies (re-test them too)
    old_proxies = load_existing_proxies()
    all_proxies |= old_proxies

    if not all_proxies:
        print("❌ No proxies found from any source. Exiting.")
        sys.exit(1)

    # 3. Test all proxies (resumes from last offset if interrupted)
    working = test_all_proxies(all_proxies)

    # 4. Final save — re-sort by speed, keep tested list
    if working:
        data = _read_output_file()
        tested_list = data.get("tested", [])
        save_results(working, tested_list)
        both_count  = sum(1 for p in working if p["works_with"] == "both")
        bms_only    = sum(1 for p in working if p["works_with"] == "bms_only")
        dist_only   = sum(1 for p in working if p["works_with"] == "district_only")
        http_count  = sum(1 for p in working if p["type"] == "http")
        socks_count = sum(1 for p in working if p["type"] == "socks5")

        print(f"\n📋 Summary:")
        print(f"   Total tested:      {len(all_proxies)}")
        print(f"   Working:           {len(working)}")
        print(f"     ├─ Both:         {both_count}")
        print(f"     ├─ BMS only:     {bms_only}")
        print(f"     └─ District only:{dist_only}")
        print(f"   HTTP proxies:      {http_count}")
        print(f"   SOCKS5 proxies:    {socks_count}")
        print(f"   Fastest:           {working[0]['proxy']} ({working[0]['avg_ms']}ms)")
        print(f"   Slowest kept:      {working[-1]['proxy']} ({working[-1]['avg_ms']}ms)")
    else:
        print("\n❌ No working proxies found. Try again later — free proxies are volatile.")

    elapsed = time.monotonic() - overall_start
    print(f"\n⏱ Total time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
