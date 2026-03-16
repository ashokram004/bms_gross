import json
import os
import time
import random
from datetime import datetime, timedelta
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from openpyxl import Workbook
import difflib
from collections import defaultdict, deque
import math
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_EXCEPTION

from utils.generatePremiumCityImageReport import generate_premium_city_image_report
from utils.generateHybridCityHTMLReport import generate_hybrid_city_html_report

# =============================================================================
# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# =============================================================================

SHOW_DATE = "2026-03-18"

DISTRICT_URL_TEMPLATE = (
    "https://www.district.in/movies/dhurandhar-the-revenge-movie-tickets-in-{city}-MV211577" +
    "?frmtid=TVQjMJQmE&fromdate=" + SHOW_DATE
)
BMS_URL_TEMPLATE = "https://in.bookmyshow.com/movies/{city}/dhurandhar-the-revenge/buytickets/ET00478890/20260318"

DISTRICT_CITIES = [
    "vizag", "new-delhi", "mumbai", "ahmedabad", "pune", "surat",
    "kolkata", "lucknow", "jaipur", "chandigarh", "bengaluru", "bhopal",
    "chennai", "hyderabad"
]

BMS_CITIES = [
    "vizag-visakhapatnam", "national-capital-region-ncr", "mumbai", "ahmedabad",
    "pune", "surat", "kolkata", "lucknow", "jaipur", "chandigarh",
    "bengaluru", "bhopal", "chennai", "hyderabad"
]

# =============================================================================
# ── GLOBAL CONFIG ─────────────────────────────────────────────────────────────
# =============================================================================
BMS_KEY      = "kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"
BOOKED_CODES = {"2"}
SLEEP_TIME   = 1.0
MAX_WORKERS  = 3


def build_city_cfg(d_slug, b_slug):
    name = d_slug.replace("-", " ").title()
    return {
        "name":         name,
        "district_url": DISTRICT_URL_TEMPLATE.replace("{city}", d_slug),
        "bms_url":      BMS_URL_TEMPLATE.replace("{city}", b_slug),
        "show_date":    SHOW_DATE,
    }


# =============================================================================
# ── SHARED DRIVER ─────────────────────────────────────────────────────────────
# =============================================================================
def get_driver():
    ua = UserAgent()
    options = Options()
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--headless")
    options.add_argument("start-maximized")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-site-isolation-trials")
    options.add_argument("disable-csp")
    return webdriver.Chrome(options=options)


# =============================================================================
# ── TIME NORMALIZATION HELPERS ────────────────────────────────────────────────
# =============================================================================
def district_gmt_to_ist(dt_str):
    gmt = datetime.fromisoformat(dt_str)
    ist = gmt + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d %H:%M")

def normalize_bms_time(show_date, show_time):
    dt = datetime.strptime(f"{show_date} {show_time}", "%Y-%m-%d %I:%M %p")
    return dt.strftime("%Y-%m-%d %H:%M")

def build_seat_signature(seat_map):
    counts = sorted(seat_map.values())
    return "|".join(str(c) for c in counts)


# =============================================================================
# ── DISTRICT SEAT LAYOUT API ──────────────────────────────────────────────────
# =============================================================================
def get_district_seat_layout(driver, cinema_id, session_id):
    api_url = "https://www.district.in/gw/consumer/movies/v1/select-seat?version=3&site_id=1&channel=mweb&child_site_id=1&platform=district"
    payload  = json.dumps({"cinemaId": int(cinema_id), "sessionId": str(session_id)})
    guest_token = str(random.randint(1, 9999999999))
    js = f"""
    var cb = arguments[0];
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "{api_url}", true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("x-guest-token", "{guest_token}");
    xhr.onload = function() {{ cb(xhr.responseText); }};
    xhr.onerror = function() {{ cb(null); }};
    xhr.send('{payload}');
    """
    try:
        resp = driver.execute_async_script(js)
        if resp:
            return json.loads(resp)
    except Exception:
        pass
    return None


# =============================================================================
# ── DISTRICT SINGLE-CITY FETCH ────────────────────────────────────────────────
# =============================================================================
def fetch_district_data(driver, city_cfg, processed_district_sids):
    district_full_url = city_cfg['district_url']
    city_name = city_cfg["name"]
    print(f"\n🚀 [District][{city_name}] STARTING FETCH...")
    results = []

    try:
        driver.set_script_timeout(10)
        driver.get(district_full_url)
        html = driver.page_source
        time.sleep(2)
        marker = 'id="__NEXT_DATA__"'
        start  = html.find(marker)
        if start == -1:
            return []

        start = html.find('>', start) + 1
        end   = html.find('</script>', start)
        data  = json.loads(html[start:end])

        sessions = data['props']['pageProps']['data']['serverState']['movieSessions']
        if not sessions:
            print(f"   ⚠️ [District][{city_name}] No sessions found")
            return []

        key     = list(sessions.keys())[0]
        cinemas = sessions[key].get('arrangedSessions', [])

        for cin in cinemas:
            venue = cin['entityName']
            print(f"   🏛️  [District][{city_name}] Venue: {venue}")

            for s in cin.get('sessions', []):
                sid = str(s.get('sid', ''))
                cid = s.get('cid')

                if sid in processed_district_sids:
                    continue
                processed_district_sids.add(sid)

                code_to_label  = {}
                default_prices = {}
                for a in s.get('areas', []):
                    code_to_label[a['code']]  = a['label']
                    default_prices[a['code']] = float(a['price'])

                b_gross, p_gross, b_tkts, t_tkts = 0, 0, 0, 0
                seat_map        = defaultdict(int)
                label_price_map = {}

                layout_res = None
                if cid:
                    layout_res = get_district_seat_layout(driver, cid, sid)

                if layout_res and 'seatLayout' in layout_res:
                    col_areas = layout_res['seatLayout'].get('colAreas', {})
                    obj_areas = col_areas.get('objArea', [])

                    for area in obj_areas:
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
                    print(f"   ⚡ [District][{city_name}] Using Cached Data for {sid}")
                    for a in s.get('areas', []):
                        tot, av, pr = a['sTotal'], a['sAvail'], a['price']
                        bk = tot - av
                        seat_map[a['label']] = tot
                        label_price_map[a['label']] = float(pr)
                        b_tkts += bk; t_tkts += tot
                        b_gross += (bk * pr); p_gross += (tot * pr)

                price_seat_map  = defaultdict(int)
                price_seat_list = []
                for label, count in seat_map.items():
                    pr = label_price_map.get(label, 0.0)
                    price_seat_map[float(pr)] += count
                    price_seat_list.append((float(pr), count))

                occ             = round((b_tkts / t_tkts) * 100, 2) if t_tkts else 0
                normalized_time = district_gmt_to_ist(s['showTime'])

                print(
                    f"   🎬 [District][{city_name}] {venue[:20]:<20} | {normalized_time} | "
                    f"Occ: {occ:>5}% | Gross: ₹{b_gross:<8,}"
                )

                results.append({
                    "source": "district",
                    "sid": sid,
                    "venue": venue,
                    "showTime": s['showTime'],
                    "normalized_show_time": normalized_time,
                    "seat_category_map": dict(seat_map),
                    "price_seat_map": dict(price_seat_map),
                    "price_seat_signature": sorted(price_seat_list),
                    "seat_signature": build_seat_signature(seat_map),
                    "total_tickets": abs(t_tkts),
                    "booked_tickets": min(abs(b_tkts), abs(t_tkts)),
                    "total_gross": abs(p_gross),
                    "booked_gross": min(abs(int(b_gross)), abs(int(p_gross))),
                    "occupancy": min(100, abs(occ)),
                    "is_fallback": False,
                    "city": city_name,
                })

        print(f"✅ [District][{city_name}] Found {len(results)} shows.")

    except Exception as e:
        print(f"❌ [District][{city_name}] Error: {e}")

    return results


# =============================================================================
# ── DISTRICT CITY-CHUNK WORKER ────────────────────────────────────────────────
# =============================================================================
def district_worker(city_cfgs_chunk):
    all_results = []
    driver = get_driver()
    try:
        for city_cfg in city_cfgs_chunk:
            processed_district_sids = set()
            city_results = fetch_district_data(driver, city_cfg, processed_district_sids)
            all_results.extend(city_results)
            time.sleep(SLEEP_TIME)
    except Exception as e:
        print(f"❌ [District Worker] Fatal error: {e}")
    finally:
        driver.quit()
    return all_results


# =============================================================================
# ── BMS SEAT LAYOUT + DECRYPT ─────────────────────────────────────────────────
# =============================================================================
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
            if current_price > 0:
                last_price = current_price
            elif last_price > 0:
                local_price_map[parts[2]] = last_price

    seats, booked = {}, {}
    for row in rows:
        if not row:
            continue
        parts = row.split(":")
        if len(parts) < 3:
            continue
        block = parts[3][0] if len(parts) > 3 else parts[2][0]
        area  = cat_map.get(block)
        if not area:
            continue
        for seat in parts:
            if len(seat) < 2:
                continue
            status = seat[1]
            if seat[0] == block and status in ("1", "2"):
                seats[area] = seats.get(area, 0) + 1
            if seat[0] == block and status in BOOKED_CODES:
                booked[area] = booked.get(area, 0) + 1

    t_tkts, b_tkts, t_gross, b_gross = 0, 0, 0, 0
    for area, total in seats.items():
        bk    = booked.get(area, 0)
        pr    = local_price_map.get(area, 0)
        t_tkts += total; b_tkts += bk
        t_gross += total * pr; b_gross += bk * pr

    occ = round((b_tkts / t_tkts) * 100, 2) if t_tkts else 0
    return t_tkts, b_tkts, int(t_gross), int(b_gross), occ, seats, local_price_map

def get_seat_layout(driver, venue_code, session_id):
    api = "https://services-in.bookmyshow.com/doTrans.aspx"
    js  = f"""
    var cb = arguments[0]; var x = new XMLHttpRequest();
    x.open("POST", "{api}", true);
    x.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    x.onload = function() {{ cb(x.responseText); }};
    x.send("strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode={venue_code}&strParam1={session_id}&strParam2=WEB&strParam5=Y&strFormat=json");
    """
    for attempt in range(3):
        try:
            driver.set_script_timeout(10)
            resp  = driver.execute_async_script(js)
            j     = json.loads(resp).get("BookMyShow", {})
            if j.get("blnSuccess") == "true":
                return j.get("strData"), None
            err = j.get("strException", "")
            if "Rate limit" in err:
                if attempt < 2:
                    time.sleep(60)
                    continue
                return None, "Rate limit exceeded"
            return None, err
        except Exception as e:
            return None, str(e)
    return None, "Unknown Error"


# =============================================================================
# ── BMS VENUE WORKER ──────────────────────────────────────────────────────────
# =============================================================================
def process_venue_list(venues, city_cfg, processed_district_sids, processed_bms_sids):
    city_name = city_cfg["name"]
    show_date = city_cfg["show_date"]
    results   = []
    driver    = get_driver()

    try:
        for v in venues:
            v_name = v["additionalData"]["venueName"]
            v_code = v["additionalData"]["venueCode"]
            print(f"   🏛️  [BMS][{city_name}] Venue: {v_name} | Shows: {len(v.get('showtimes', []))}")

            screen_details_map = {}
            shows      = v.get("showtimes", [])
            shows.sort(key=lambda s: s["additionalData"].get("availStatus", "0"), reverse=True)
            show_queue    = deque(shows)
            deferred_sids = set()

            while show_queue:
                show      = show_queue.popleft()
                sid       = str(show["additionalData"]["sessionId"])
                show_time = show["title"]

                if sid in processed_bms_sids:
                    continue
                if sid in processed_district_sids:
                    print(f"   ⏭️  [BMS][{city_name}] Skipping {sid} (Found in District)")
                    continue
                processed_bms_sids.add(sid)

                raw_screen = show.get("screenAttr", "")
                screenName = raw_screen if raw_screen else "Main Screen"
                cats       = show["additionalData"].get("categories", [])
                price_map  = {c["areaCatCode"]: float(c["curPrice"]) for c in cats}

                try:
                    enc, error_msg = get_seat_layout(driver, v_code, sid)
                    data           = None
                    soldOut        = False
                    seat_map       = {}
                    is_fallback    = False
                    price_seat_map = {}

                    if not enc:
                        if not price_map:
                            continue
                        max_price   = max(price_map.values())
                        is_fallback = True
                        for p in price_map.values():
                            price_seat_map[float(p)] = 0

                        if error_msg and "sold out" in error_msg.lower():
                            print(f"      🔴 [BMS][{city_name}] Sold Out: {sid}. Checking recovery...")
                            recovered_capacity  = None
                            recovered_seat_map  = None

                            if screenName in screen_details_map:
                                recovered_seat_map  = screen_details_map[screenName]
                                recovered_capacity  = sum(recovered_seat_map.values())
                                print(f"         ⚡ Using cached layout ({recovered_capacity} seats)")

                            if not recovered_capacity:
                                try:
                                    base_sid = int(sid)
                                    for offset in range(7, 0, -1):
                                        target_sid = str(base_sid + offset)
                                        time.sleep(1)
                                        n_enc, n_err = get_seat_layout(driver, v_code, target_sid)
                                        if n_enc:
                                            n_dec = decrypt_data(n_enc)
                                            n_res = calculate_bms_collection(n_dec, {})
                                            if n_res[0] > 0:
                                                recovered_capacity = n_res[0]
                                                recovered_seat_map = n_res[5]
                                                print(f"         ✨ Recovered using {target_sid}")
                                                break
                                except Exception:
                                    pass

                            if recovered_capacity:
                                calc_gross = sum(
                                    count * price_map.get(ac, 0)
                                    for ac, count in recovered_seat_map.items()
                                )
                                if calc_gross > 0:
                                    t_tkts = b_tkts = recovered_capacity
                                    t_gross = b_gross = calc_gross
                                    screen_details_map[screenName] = recovered_seat_map
                                    seat_map       = recovered_seat_map
                                    is_fallback    = False
                                    ps_map         = defaultdict(int)
                                    for ac, count in seat_map.items():
                                        ps_map[float(price_map.get(ac, 0))] += count
                                    price_seat_map = dict(ps_map)
                                else:
                                    recovered_capacity = None

                            if not recovered_capacity:
                                FALLBACK_SEATS = 400
                                t_tkts = b_tkts = FALLBACK_SEATS
                                t_gross = b_gross = int(FALLBACK_SEATS * max_price)
                                print(f"         ⚠️ [BMS][{city_name}] No cache. Using default {FALLBACK_SEATS}.")

                            occ     = 100.0
                            soldOut = True
                            data    = {"total_tickets": t_tkts, "booked_tickets": b_tkts,
                                       "total_gross": t_gross, "booked_gross": b_gross, "occupancy": occ}

                        elif error_msg and "Rate limit" in error_msg:
                            print(f"      🚫 [BMS][{city_name}] Rate Limit for {v_name[:15]}")
                            continue

                        else:
                            print(f"      ⚠️  [BMS][{city_name}] Error {sid}: {error_msg}")
                            if screenName in screen_details_map:
                                cached_seat_map = screen_details_map[screenName]
                                seat_map  = cached_seat_map
                                t_tkts    = sum(cached_seat_map.values())
                                b_tkts    = int(t_tkts * 0.5)
                                ps_map    = defaultdict(int)
                                t_gross_c = 0
                                for ac, count in cached_seat_map.items():
                                    pr = float(price_map.get(ac, 0))
                                    ps_map[pr] += count; t_gross_c += count * pr
                                price_seat_map = dict(ps_map)
                                t_gross = int(t_gross_c); b_gross = int(t_gross * 0.5)
                                occ     = 50.0; is_fallback = False
                                print(f"         ⚡ Smart Fallback: {screenName} ({t_tkts} seats)")
                            elif sid not in deferred_sids and len(show_queue) > 0:
                                deferred_sids.add(sid)
                                processed_bms_sids.discard(sid)
                                show_queue.append(show)
                                continue
                            else:
                                t_tkts = 400; b_tkts = 200
                                t_gross = int(400 * max_price); b_gross = int(200 * max_price)
                                occ = 50.0
                                print(f"         ❌ [BMS][{city_name}] Hard Fallback 400/200")

                            data = {"total_tickets": t_tkts, "booked_tickets": b_tkts,
                                    "total_gross": t_gross, "booked_gross": b_gross, "occupancy": occ}
                    else:
                        decrypted = decrypt_data(enc)
                        res       = calculate_bms_collection(decrypted, price_map)
                        data      = {"total_tickets": res[0], "booked_tickets": res[1],
                                     "total_gross": res[2], "booked_gross": res[3], "occupancy": res[4]}
                        seat_map  = res[5]
                        final_pm  = res[6]

                        if data["total_tickets"] > 0:
                            ps_map = defaultdict(int); ps_list = []
                            for ac, count in seat_map.items():
                                pr = float(final_pm.get(ac, 0))
                                ps_map[pr] += count; ps_list.append((pr, count))
                            price_seat_map             = dict(ps_map)
                            data["price_seat_signature"] = sorted(ps_list)
                            screen_details_map[screenName] = seat_map

                    if data:
                        normalized_time = normalize_bms_time(show_date, show_time)
                        tag = "(SOLD OUT)" if soldOut else ""
                        print(
                            f"   🎬 [BMS][{city_name}] {v_name[:15]:<15} | {normalized_time} | "
                            f"Occ: {data['occupancy']:>5}% | Gross: ₹{data['booked_gross']:<8,} {tag}"
                        )
                        results.append({
                            "source": "bms", "sid": str(sid), "venue": v_name,
                            "showTime": show_time, "normalized_show_time": normalized_time,
                            "seat_category_map": seat_map, "price_seat_map": price_seat_map,
                            "price_seat_signature": data.get("price_seat_signature", []),
                            "seat_signature": build_seat_signature(seat_map),
                            "total_tickets":  abs(data["total_tickets"]),
                            "booked_tickets": min(abs(data["booked_tickets"]), abs(data["total_tickets"])),
                            "total_gross":    abs(data["total_gross"]),
                            "booked_gross":   min(abs(data["booked_gross"]), abs(data["total_gross"])),
                            "occupancy":      min(100, abs(data["occupancy"])),
                            "is_fallback":    is_fallback,
                            "city":           city_name,
                        })

                except Exception:
                    pass

                time.sleep(SLEEP_TIME)

    except Exception as e:
        print(f"❌ [BMS][{city_name}] Worker Error: {e}")
    finally:
        driver.quit()
    return results


# =============================================================================
# ── BMS CITY FETCH (page scrape + venue dispatch) ─────────────────────────────
# =============================================================================
def fetch_bms_venues_for_city(city_cfg):
    city_name = city_cfg["name"]
    bms_url   = city_cfg["bms_url"]
    driver    = get_driver()
    venues    = []
    try:
        driver.get(bms_url)
        time.sleep(2.5)
        html = driver.page_source

        marker = "window.__INITIAL_STATE__"
        start  = html.find(marker)
        if start == -1:
            print(f"   ⚠️ [BMS][{city_name}] Could not find initial state")
            return []

        start = html.find("{", start)
        brace = 0; end = start
        while end < len(html):
            if html[end] == "{": brace += 1
            elif html[end] == "}": brace -= 1
            if brace == 0: break
            end += 1

        state_data = json.loads(html[start:end + 1])
        try:
            sbe     = state_data.get("showtimesByEvent")
            dc      = sbe.get("currentDateCode")
            widgets = sbe["showDates"][dc]["dynamic"]["data"]["showtimeWidgets"]
            for w in widgets:
                if w.get("type") == "groupList":
                    for g in w["data"]:
                        if g.get("type") == "venueGroup":
                            venues = g["data"]
        except Exception:
            venues = []
    except Exception as e:
        print(f"❌ [BMS][{city_name}] Page fetch error: {e}")
    finally:
        driver.quit()
    return venues


# =============================================================================
# ── BMS CITY-CHUNK WORKER ─────────────────────────────────────────────────────
# =============================================================================
def bms_city_chunk_worker(city_cfgs_chunk):
    all_results = []

    for city_cfg in city_cfgs_chunk:
        city_name = city_cfg["name"]
        print(f"\n🚀 [BMS][{city_name}] STARTING FETCH...")

        venues = fetch_bms_venues_for_city(city_cfg)
        if not venues:
            print(f"   ⚠️ [BMS][{city_name}] No venues found, skipping.")
            continue

        processed_district_sids = set()
        processed_bms_sids      = set()

        print(f"   🚀 [BMS][{city_name}] Launching {MAX_WORKERS} venue-workers for {len(venues)} venues...")
        chunk_size   = math.ceil(len(venues) / MAX_WORKERS)
        venue_chunks = [venues[i:i + chunk_size] for i in range(0, len(venues), chunk_size)]

        city_results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as venue_executor:
            futures = [
                venue_executor.submit(
                    process_venue_list, chunk, city_cfg,
                    processed_district_sids, processed_bms_sids
                )
                for chunk in venue_chunks
            ]
            for future in as_completed(futures):
                try:
                    city_results.extend(future.result())
                except Exception as e:
                    print(f"❌ [BMS][{city_name}] Venue worker exception: {e}")

        print(f"✅ [BMS][{city_name}] Found {len(city_results)} shows.")
        all_results.extend(city_results)

    return all_results


# =============================================================================
# ── SAME-PLATFORM DEDUP ───────────────────────────────────────────────────────
# =============================================================================
def dedup_same_platform(records, source_label):
    """
    Remove duplicate show records produced by parallel workers of the same source.
    A duplicate is defined as two records sharing the same SID.
    When duplicates exist, keep the one with the higher booked_gross (more data).
    """
    seen    = {}   # sid -> index in best list
    best    = []
    dropped = 0

    for r in records:
        sid = r.get('sid', '')
        if not sid:
            best.append(r)
            continue
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


# =============================================================================
# ── MERGE LOGIC ───────────────────────────────────────────────────────────────
# =============================================================================
def merge_data(dist_data, bms_data, city_name):
    # Deduplicate each source independently before cross-source merge
    dist_data = dedup_same_platform(dist_data, "District")
    bms_data  = dedup_same_platform(bms_data,  "BMS")

    print(f"\n🔄 Merging Data (Cross Source Dedupe)...")
    final_data     = []
    SEAT_TOLERANCE = 5

    district_by_time = defaultdict(list)
    for r in dist_data:
        key = (r.get('city', ''), r['normalized_show_time'])
        district_by_time[key].append(r)

    for bms in bms_data:
        key        = (bms.get('city', ''), bms['normalized_show_time'])
        candidates = district_by_time.get(key, [])
        match_found = None

        # 1. Exact SID
        for cand in candidates:
            if cand['sid'] == bms['sid']:
                match_found = cand
                print(f"   🔗 SID Match: {bms['sid']}")
                break

        # 2. Price + Seat signature
        if not match_found and not bms.get('is_fallback', False):
            b_sig           = bms.get('price_seat_signature', [])
            bms_venue_clean = bms['venue'].lower()
            for cand in candidates:
                d_sig = cand.get('price_seat_signature', [])
                if not b_sig or not d_sig or len(b_sig) != len(d_sig):
                    continue
                if all(bp == dp and abs(bs - ds) <= SEAT_TOLERANCE
                       for (bp, bs), (dp, ds) in zip(b_sig, d_sig)):
                    ratio = difflib.SequenceMatcher(None, bms_venue_clean, cand['venue'].lower()).ratio()
                    if ratio > 0.4:
                        match_found = cand
                        print(f"   🔗 Price/Seat Sig Match: {bms['venue']}... == {cand['venue']}... (Tol: {SEAT_TOLERANCE}, Ratio: {int(ratio*100)}%)")
                        break

        # 3. Seat signature only
        if not match_found and not bms.get('is_fallback', False):
            b_seats         = sorted(bms.get('seat_category_map', {}).values())
            bms_venue_clean = bms['venue'].lower()
            for cand in candidates:
                d_seats = sorted(cand.get('seat_category_map', {}).values())
                if not b_seats or not d_seats or len(b_seats) != len(d_seats):
                    continue
                if all(abs(bs - ds) <= SEAT_TOLERANCE for bs, ds in zip(b_seats, d_seats)):
                    ratio = difflib.SequenceMatcher(None, bms_venue_clean, cand['venue'].lower()).ratio()
                    if ratio > 0.4:
                        match_found = cand
                        print(f"   🔗 Seat Sig Match: {bms['venue']}... == {cand['venue']}... (Tol: {SEAT_TOLERANCE}, Ratio: {int(ratio*100)}%)")
                        break

        # 4. Fuzzy venue + price set
        if not match_found and candidates:
            best_ratio      = 0; best_cand = None
            bms_venue_clean = bms['venue'].lower()
            b_prices        = {p for p in bms.get('price_seat_map', {}).keys() if p > 0}
            for cand in candidates:
                d_prices = {p for p in cand.get('price_seat_map', {}).keys() if p > 0}
                if b_prices != d_prices:
                    continue
                ratio = difflib.SequenceMatcher(None, bms_venue_clean, cand['venue'].lower()).ratio()
                if ratio > 0.55 and ratio > best_ratio:
                    best_ratio = ratio; best_cand = cand
            if best_cand:
                match_found = best_cand
                print(f"   🔗 Fuzzy Match: {bms['venue']}... == {match_found['venue']}... ({int(best_ratio*100)}%)")

        if match_found:
            candidates.remove(match_found)
            if bms.get('is_fallback', False):
                final_data.append(match_found)
            else:
                if bms['booked_gross'] > match_found['booked_gross']:
                    for k in ('total_tickets','booked_tickets','total_gross','booked_gross',
                              'occupancy','seat_category_map','price_seat_map','seat_signature'):
                        match_found[k] = bms[k]
                final_data.append(match_found)
        else:
            final_data.append(bms)

    for sublist in district_by_time.values():
        final_data.extend(sublist)

    return final_data


# =============================================================================
# ── EXCEL GENERATOR ───────────────────────────────────────────────────────────
# =============================================================================
def generate_excel(data, filename):
    wb     = Workbook()
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    ws_th = wb.active
    ws_th.title = "Theatre Wise"
    ws_th.append(["Venue","Shows","Total Seats","Booked Seats","Total Gross ₹","Booked Gross ₹","Occ %"])
    th_map = {}
    for r in data:
        k = r["venue"]
        if k not in th_map:
            th_map[k] = {"shows":0,"t_seats":0,"b_seats":0,"p_gross":0,"b_gross":0}
        d = th_map[k]
        d["shows"] += 1; d["t_seats"] += r["total_tickets"]; d["b_seats"] += r["booked_tickets"]
        d["p_gross"] += r["total_gross"]; d["b_gross"] += r["booked_gross"]
    for v, d in th_map.items():
        occ = round((d["b_seats"]/d["t_seats"])*100, 2) if d["t_seats"] else 0
        ws_th.append([v, d["shows"], d["t_seats"], d["b_seats"], d["p_gross"], d["b_gross"], occ])

    ws_show = wb.create_sheet(title="Show Wise")
    ws_show.append(["Source","Venue","Time","SID","Total Seats","Booked Seats","Total Gross ₹","Booked Gross ₹","Occ %"])
    for r in data:
        ws_show.append([r["source"], r["venue"], r["normalized_show_time"], r["sid"],
                        r["total_tickets"], r["booked_tickets"],
                        r["total_gross"], r["booked_gross"], r["occupancy"]])

    ws_sum  = wb.create_sheet(title="Summary")
    agg_t   = sum(r["total_tickets"]  for r in data)
    agg_b   = sum(r["booked_tickets"] for r in data)
    agg_pg  = sum(r["total_gross"]    for r in data)
    agg_bg  = sum(r["booked_gross"]   for r in data)
    occ     = round((agg_b/agg_t)*100, 2) if agg_t else 0
    ws_sum.append(["Metric","Value"])
    for row in [("Total Theatres", len(th_map)), ("Total Shows", len(data)),
                ("Total Seats", agg_t), ("Booked Tickets", agg_b),
                ("Total Potential Gross", agg_pg), ("Total Booked Gross", agg_bg),
                ("Overall Occupancy %", occ),
                ("Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))]:
        ws_sum.append(list(row))

    path = os.path.join(reports_dir, filename)
    wb.save(path)
    print(f"📊 Excel Saved: {path}")


def extract_movie_name_from_url(url):
    try:
        if '/movies/' in url and '/buytickets/' in url:
            parts = url.split('/movies/')[1].split('/buytickets/')[0].split('/')
            movie_slug = parts[-1] if len(parts) > 1 else parts[0]
            return movie_slug.replace('-', ' ').title()
        if '/movies/' in url and '-movie-tickets-in-' in url:
            movie_slug = url.split('/movies/')[1].split('-movie-tickets-in-')[0]
            return movie_slug.replace('-', ' ').title()
    except Exception as e:
        print(f"Could not extract movie name from URL: {e}")
    return "Movie Collection"


# =============================================================================
# ── MAIN ──────────────────────────────────────────────────────────────────────
# =============================================================================
if __name__ == "__main__":
    total_cities = len(DISTRICT_CITIES)
    print(f"🎬 Starting parallel District + BMS run for {total_cities} cities...\n")
    print(f"   District workers : {MAX_WORKERS}  (each handles ~{math.ceil(total_cities / MAX_WORKERS)} cities)")
    print(f"   BMS city-workers : {MAX_WORKERS}  (each handles ~{math.ceil(total_cities / MAX_WORKERS)} cities)")
    print(f"   BMS venue-workers: {MAX_WORKERS}  (per city, inside each BMS city-worker)\n")

    all_city_cfgs   = [build_city_cfg(d, b) for d, b in zip(DISTRICT_CITIES, BMS_CITIES)]
    chunk_size      = math.ceil(total_cities / MAX_WORKERS)
    city_cfg_chunks = [all_city_cfgs[i:i + chunk_size] for i in range(0, total_cities, chunk_size)]

    all_dist_data = []
    all_bms_data  = []

    print("🚦 Submitting District and BMS workers in parallel...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS * 2) as top_executor:

        district_futures = {
            top_executor.submit(district_worker, chunk): f"District-Worker-{i}"
            for i, chunk in enumerate(city_cfg_chunks)
        }
        bms_futures = {
            top_executor.submit(bms_city_chunk_worker, chunk): f"BMS-Worker-{i}"
            for i, chunk in enumerate(city_cfg_chunks)
        }

        all_futures = {**district_futures, **bms_futures}

        print("⏳ Waiting for all District + BMS workers to finish...\n")
        done, not_done = wait(all_futures.keys())

        for future in done:
            worker_label = all_futures[future]
            try:
                results = future.result()
                if worker_label.startswith("District"):
                    all_dist_data.extend(results)
                    print(f"✅ {worker_label} done — {len(results)} District shows collected.")
                else:
                    all_bms_data.extend(results)
                    print(f"✅ {worker_label} done — {len(results)} BMS shows collected.")
            except Exception as e:
                print(f"❌ {worker_label} raised an exception: {e}")

        if not_done:
            print(f"⚠️  {len(not_done)} worker(s) did not complete — results may be partial.")

    # All workers finished — dedup then merge
    print(f"\n🔄 Merging {len(all_dist_data)} District + {len(all_bms_data)} BMS shows across all cities...")
    all_cities_data = merge_data(all_dist_data, all_bms_data, "ALL")

    if all_cities_data:
        ts            = datetime.now().strftime("%Y%m%d_%H%M%S")
        movie_name    = extract_movie_name_from_url(DISTRICT_URL_TEMPLATE)
        show_date_fmt = datetime.strptime(SHOW_DATE, "%Y-%m-%d").strftime("%d %b %Y")

        print(f"\n📦 Generating reports — {len(all_cities_data)} shows across {total_cities} cities...")

        generate_excel(all_cities_data, f"Cities_Report_{ts}.xlsx")

        generate_premium_city_image_report(
            all_cities_data,
            f"reports/Cities_Report_{ts}.png",
            movie_name=movie_name,
            show_date=show_date_fmt,
        )

        generate_hybrid_city_html_report(
            all_cities_data,
            DISTRICT_URL_TEMPLATE.replace("{city}", DISTRICT_CITIES[0]),
            f"reports/Cities_Report_{ts}.html"
        )

        print(f"\n🏁 All done. Reports saved with timestamp {ts}")
    else:
        print("❌ No data collected across any city.")