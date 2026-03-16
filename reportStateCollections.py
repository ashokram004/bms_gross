import json
import time
import os
import random
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from itertools import cycle
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from openpyxl import Workbook
from fake_useragent import UserAgent
from datetime import datetime, timedelta
import difflib
from collections import defaultdict, deque
import math

from utils.generatePremiumStatesImageReport import generate_premium_states_image_report
from utils.generateHybridStatesHTMLReport import generate_hybrid_states_html_report

# =========================== CONFIGURATION ===========================
INPUT_STATE_LIST = ["Telangana", "Andhra Pradesh", "Karnataka"]

DISTRICT_CONFIG_PATH = os.path.join("utils", "district_cities_config.json")
BMS_CONFIG_PATH      = os.path.join("utils", "bms_cities_config.json")

DISTRICT_MAP_PATH = os.path.join("utils", "district_area_city_mapping.json")
BMS_MAP_PATH      = os.path.join("utils", "bms_area_city_mapping.json")

DISTRICT_URL          = "https://www.district.in/movies/ustaad-bhagat-singh-movie-tickets-in-{city}-MV161614"
SHOW_DATE             = "2026-03-19"
DISTRICT_URL_TEMPLATE = DISTRICT_URL + "?frmtid=v833gyzof7&fromdate=" + SHOW_DATE
BMS_URL_TEMPLATE      = "https://in.bookmyshow.com/movies/{city}/ustaad-bhagat-singh/buytickets/ET00339939/20260319"

ENCRYPTION_KEY = "kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"
BOOKED_STATES  = {"2"}
SLEEP_TIME     = 1.0
MAX_WORKERS    = 3   # Workers per source (District and BMS each get 3)

PROXY_LIST = []
proxy_pool = cycle(PROXY_LIST) if PROXY_LIST else None


# =========================== HELPER FUNCTIONS ===========================

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


# =========================== MAPPING SYSTEM ===========================

def load_mapping_dict(file_path):
    mapping = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for state, cities in data.items():
                    if isinstance(cities, list):
                        for entry in cities:
                            if "name" in entry and "reporting_city" in entry:
                                mapping[(state, entry["name"])] = entry["reporting_city"]
        except Exception as e:
            print(f"Warning: Could not parse mapping {file_path}: {e}")
    return mapping

DISTRICT_CITY_MAP = load_mapping_dict(DISTRICT_MAP_PATH)
BMS_CITY_MAP      = load_mapping_dict(BMS_MAP_PATH)

def get_normalized_city_name(state, raw_city, source):
    lookup = DISTRICT_CITY_MAP if source == "district" else BMS_CITY_MAP
    return lookup.get((state, raw_city), raw_city)


# =========================== CORE FUNCTIONS ===========================

def get_driver(proxy=None):
    ua = UserAgent()
    options = Options()
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--headless=new")
    options.add_argument("start-maximized")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-site-isolation-trials")
    options.add_argument("disable-csp")
    options.add_argument("--disable-blink-features=AutomationControlled")
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    if proxy:
        options.add_argument(f'--proxy-server={proxy}')
    return webdriver.Chrome(options=options)


# ================= TIME NORMALIZATION HELPERS =================

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

def get_district_seat_layout(driver, cinema_id, session_id):
    api_url     = "https://www.district.in/gw/consumer/movies/v1/select-seat?version=3&site_id=1&channel=mweb&child_site_id=1&platform=district"
    payload     = json.dumps({"cinemaId": int(cinema_id), "sessionId": str(session_id)})
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


# ================= DISTRICT: SINGLE CITY FETCH =================

def fetch_district_city(driver, state, city, processed_sids):
    """
    Fetch District data for one city entry.
    processed_sids is local to the calling worker — fully isolated.
    """
    city_results   = []
    reporting_city = get_normalized_city_name(state, city['name'], "district")
    url            = DISTRICT_URL_TEMPLATE.format(city=city['slug'])

    try:
        driver.set_script_timeout(10)
        driver.get(url)
        time.sleep(1)
        html = driver.page_source

        marker = 'id="__NEXT_DATA__"'
        idx    = html.find(marker)
        if idx == -1:
            return []

        start = html.find('>', idx) + 1
        end   = html.find('</script>', start)
        data  = json.loads(html[start:end])

        sessions = data['props']['pageProps']['data']['serverState']['movieSessions']
        key      = list(sessions.keys())[0]
        cinemas  = sessions[key].get('arrangedSessions', [])

        for cin in cinemas:
            venue = cin['entityName']
            for s in cin.get('sessions', []):
                sid = str(s.get('sid', ''))
                cid = s.get('cid')

                if sid in processed_sids:
                    continue
                processed_sids.add(sid)

                price_map     = {}
                code_to_label = {}
                for area in s.get('areas', []):
                    price_map[area['code']]     = float(area['price'])
                    code_to_label[area['code']] = area['label']

                b_gross, p_gross, b_tkts, t_tkts = 0, 0, 0, 0
                seat_map       = defaultdict(int)
                price_seat_map = defaultdict(int)

                layout_res = None
                if cid:
                    layout_res = get_district_seat_layout(driver, cid, sid)

                if layout_res and 'seatLayout' in layout_res:
                    col_areas = layout_res['seatLayout'].get('colAreas', {})
                    obj_areas = col_areas.get('objArea', [])

                    for area in obj_areas:
                        area_code = area.get('AreaCode')
                        price     = area.get('AreaPrice', price_map.get(area_code, 0))
                        label     = code_to_label.get(area_code, area_code)

                        for row in area.get('objRow', []):
                            for seat in row.get('objSeat', []):
                                status = seat.get('SeatStatus')
                                t_tkts += 1; p_gross += price
                                seat_map[label] += 1
                                price_seat_map[float(price)] += 1
                                if status != '0' and status != 0:
                                    b_tkts += 1; b_gross += price
                else:
                    print(f"      ⚠️  [District][{city['name']}] API failed for {sid}. Using cached data.")
                    for a in s.get('areas', []):
                        tot, av, pr = a['sTotal'], a['sAvail'], a['price']
                        bk = tot - av
                        seat_map[a['label']]      = tot
                        b_tkts += bk; t_tkts += tot
                        b_gross += (bk * pr); p_gross += (tot * pr)
                        price_seat_map[float(pr)] += tot

                price_seat_list = [(pr, count) for pr, count in price_seat_map.items()]
                occ             = round((b_tkts / t_tkts) * 100, 2) if t_tkts else 0
                normalized_time = district_gmt_to_ist(s['showTime'])

                city_results.append({
                    "source":               "district",
                    "sid":                  sid,
                    "state":                state,
                    "city":                 reporting_city,
                    "venue":                venue,
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

        if city_results:
            gross = sum(x['booked_gross'] for x in city_results)
            print(f"✅ [District] {city['name']:<15} -> {reporting_city:<15} | Shows: {len(city_results):<3} | Gross: ₹{gross:<10,}")

    except Exception as e:
        print(f"❌ [District][{state}][{city['name']}] Error: {e}")

    return city_results


# ================= DISTRICT: CHUNK WORKER =================

def district_worker(city_chunk):
    """
    Worker handling a flat chunk of (state, city_dict) pairs for District.
    Owns its own driver and SID set — no cross-worker state shared.
    """
    all_results    = []
    processed_sids = set()
    driver         = get_driver()

    try:
        for state, city in city_chunk:
            results = fetch_district_city(driver, state, city, processed_sids)
            all_results.extend(results)
            time.sleep(SLEEP_TIME)
    except Exception as e:
        print(f"❌ [District Worker] Fatal error: {e}")
    finally:
        driver.quit()

    return all_results


# ================= BMS LOGIC =================

def extract_initial_state_from_page(driver, url):
    try:
        driver.get(url)
        time.sleep(2)
        html   = driver.page_source
        marker = "window.__INITIAL_STATE__"
        start  = html.find(marker)
        if start == -1:
            return None
        start = html.find("{", start)
        brace_count = 0; end = start
        while end < len(html):
            if html[end] == "{":   brace_count += 1
            elif html[end] == "}": brace_count -= 1
            if brace_count == 0:   break
            end += 1
        return json.loads(html[start:end + 1])
    except:
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
    except:
        pass
    return []

def get_seat_layout(driver, venue_code, session_id):
    api_url     = "https://services-in.bookmyshow.com/doTrans.aspx"
    max_retries = 2
    js = """
        var cb = arguments[0]; var x = new XMLHttpRequest();
        x.open("POST", "%s", true);
        x.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
        x.onload = function() { cb(x.responseText); };
        x.send("strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode=%s&lngTransactionIdentifier=0&strParam1=%s&strParam2=WEB&strParam5=Y&strFormat=json");
    """ % (api_url, venue_code, session_id)

    for i in range(max_retries + 1):
        try:
            driver.set_script_timeout(10)
            resp = driver.execute_async_script(js)
            data = json.loads(resp).get("BookMyShow", {})
            if data.get("blnSuccess") == "true":
                return data.get("strData"), None
            error_msg = data.get("strException", "")
            if "Rate limit" in error_msg:
                if i < max_retries:
                    time.sleep(60)
                    continue
                return None, "Rate limit exceeded"
            return None, error_msg
        except Exception as e:
            return None, str(e)
    return None, "Unknown Error"

def decrypt_data(enc):
    decoded = b64decode(enc)
    cipher  = AES.new(ENCRYPTION_KEY.encode(), AES.MODE_CBC, iv=bytes(16))
    return unpad(cipher.decrypt(decoded), AES.block_size).decode()

def calculate_show_collection(decrypted, price_map):
    header, rows_part = decrypted.split("||")
    rows              = rows_part.split("|")

    cat_map         = {}
    local_price_map = price_map.copy()
    last_price      = 0.0

    for p in header.split("|"):
        parts = p.split(":")
        if len(parts) >= 3:
            cat_map[parts[1]] = parts[2]
            current_price = local_price_map.get(parts[2], 0.0)
            if current_price > 0:  last_price = current_price
            elif last_price > 0:   local_price_map[parts[2]] = last_price

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
            if seat[0] == block and status in BOOKED_STATES:
                booked[area] = booked.get(area, 0) + 1

    t_tkts, b_tkts, t_gross, b_gross = 0, 0, 0, 0
    for area, total in seats.items():
        bk      = booked.get(area, 0)
        pr      = local_price_map.get(area, 0)
        t_tkts += total; b_tkts += bk
        t_gross += total * pr; b_gross += bk * pr

    occ = round((b_tkts / t_tkts) * 100, 2) if t_tkts else 0
    return t_tkts, b_tkts, int(t_gross), int(b_gross), occ, seats, local_price_map


# ================= BMS: VENUE WORKER =================

def process_venue_list(venues, city_name, reporting_city, state_name, district_sids, local_bms_sids, proxy=None):
    """
    Processes a chunk of venues for one city.
    local_bms_sids is owned by the calling city worker — no cross-worker sharing.
    """
    results     = []
    total_gross = 0
    driver      = get_driver(proxy)

    try:
        for venue in venues:
            v_name = venue["additionalData"]["venueName"]
            v_code = venue["additionalData"]["venueCode"]

            screen_details_map = {}
            shows              = venue.get("showtimes", [])
            shows.sort(key=lambda s: s["additionalData"].get("availStatus", "0"), reverse=True)
            show_queue    = deque(shows)
            deferred_sids = set()

            while show_queue:
                show      = show_queue.popleft()
                sid       = str(show["additionalData"]["sessionId"])
                show_time = show["title"]

                raw_screen = show.get("screenAttr", "")
                screenName = raw_screen if raw_screen else "Main Screen"

                if sid in local_bms_sids:
                    continue
                local_bms_sids.add(sid)

                if sid in district_sids:
                    print(f"   ⏭️  [BMS][{city_name}] Skipping {sid} (Found in District)")
                    continue

                soldOut        = False
                seat_map       = {}
                is_fallback    = False
                price_seat_map = {}

                try:
                    cats      = show["additionalData"].get("categories", [])
                    price_map = {c["areaCatCode"]: float(c["curPrice"]) for c in cats}

                    enc, error_msg = get_seat_layout(driver, v_code, sid)
                    data           = None

                    if not enc:
                        if not price_map:
                            continue
                        max_price   = max(price_map.values())
                        is_fallback = True
                        for p in price_map.values():
                            price_seat_map[float(p)] = 0

                        if error_msg and "sold out" in error_msg.lower():
                            print(f"      🔴 [BMS][{city_name}] Sold Out: {sid}. Checking recovery...")
                            recovered_capacity = None
                            recovered_seat_map = None

                            if screenName in screen_details_map:
                                recovered_seat_map = screen_details_map[screenName]
                                recovered_capacity = sum(recovered_seat_map.values())
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
                                            n_res = calculate_show_collection(n_dec, {})
                                            if n_res[0] > 0:
                                                recovered_capacity = n_res[0]
                                                recovered_seat_map = n_res[5]
                                                print(f"         ✨ Recovered using {target_sid}")
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
                                print(f"         ❌ [BMS][{city_name}] Recovery failed. Using default {FALLBACK_SEATS}.")

                            occ     = 100.0
                            soldOut = True
                            data    = {"total_tickets": t_tkts, "booked_tickets": b_tkts,
                                       "total_gross": t_gross, "booked_gross": b_gross, "occupancy": occ}

                        elif error_msg and "Rate limit" in error_msg:
                            print(f"      🚫 [BMS][{city_name}] Rate Limit for {v_name[:15]}")
                            continue

                        else:
                            print(f"      ⚠️  [BMS][{city_name}] Error for {sid}: {error_msg}")
                            if screenName in screen_details_map:
                                cached_seat_map = screen_details_map[screenName]
                                seat_map        = cached_seat_map
                                t_tkts          = sum(cached_seat_map.values())
                                b_tkts          = int(t_tkts * 0.5)
                                ps_map          = defaultdict(int)
                                t_gross_calc    = 0
                                for ac, count in cached_seat_map.items():
                                    pr = float(price_map.get(ac, 0))
                                    ps_map[pr] += count; t_gross_calc += count * pr
                                price_seat_map = dict(ps_map)
                                t_gross     = int(t_gross_calc)
                                b_gross     = int(t_gross * 0.5)
                                occ         = 50.0
                                is_fallback = False
                                print(f"         ⚡ Smart Fallback: {screenName} ({t_tkts} seats)")
                            elif sid not in deferred_sids and len(show_queue) > 0:
                                deferred_sids.add(sid)
                                local_bms_sids.discard(sid)
                                show_queue.append(show)
                                continue
                            else:
                                t_tkts  = 400; b_tkts  = 200
                                t_gross = int(400 * max_price); b_gross = int(200 * max_price)
                                occ     = 50.0
                                print(f"         ❌ [BMS][{city_name}] Hard Fallback 400/200")
                            data = {"total_tickets": t_tkts, "booked_tickets": b_tkts,
                                    "total_gross": t_gross, "booked_gross": b_gross, "occupancy": occ}
                    else:
                        decrypted = decrypt_data(enc)
                        res       = calculate_show_collection(decrypted, price_map)
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
                        tag = "(SOLD OUT)" if soldOut else ""
                        print(
                            f"   🎬 [BMS][{city_name}] {v_name[:15]:<15} | {normalized_time} | "
                            f"Occ: {data['occupancy']:>5}% | Gross: ₹{data['booked_gross']:<8,} {tag}"
                        )
                        data.update({
                            "source":               "bms",
                            "sid":                  sid,
                            "state":                state_name,
                            "city":                 reporting_city,
                            "venue":                v_name,
                            "showTime":             show_time,
                            "normalized_show_time": normalized_time,
                            "seat_category_map":    seat_map,
                            "price_seat_map":       price_seat_map,
                            "price_seat_signature": data.get("price_seat_signature", []),
                            "seat_signature":       build_seat_signature(seat_map),
                            "is_fallback":          is_fallback,
                        })
                        results.append(data)
                        total_gross += data["booked_gross"]

                except Exception:
                    continue

                time.sleep(SLEEP_TIME)

    except Exception as e:
        print(f"❌ [BMS] Venue Worker Error: {e}")
    finally:
        driver.quit()

    return results, total_gross


# ================= BMS: SINGLE CITY FETCH =================

def fetch_bms_city(city_name, city_slug, state_name, district_sids, proxy=None):
    """
    Scrape the BMS page for one city, then fan out to MAX_WORKERS venue workers.
    Creates its own local_bms_sids set — per-city, no cross-city contamination.
    """
    reporting_city = get_normalized_city_name(state_name, city_name, "bms")
    url            = BMS_URL_TEMPLATE.format(city=city_slug)
    driver         = get_driver(proxy)
    city_results   = []
    city_total     = 0

    try:
        state_data = extract_initial_state_from_page(driver, url)
        venues     = extract_venues(state_data) if state_data else []
    except Exception:
        venues = []
    finally:
        driver.quit()

    if not venues:
        return [], 0, url

    local_bms_sids = set()   # per-city isolation
    chunk_size     = math.ceil(len(venues) / MAX_WORKERS)
    venue_chunks   = [venues[i:i + chunk_size] for i in range(0, len(venues), chunk_size)]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as venue_executor:
        futures = [
            venue_executor.submit(
                process_venue_list, chunk, city_name, reporting_city,
                state_name, district_sids, local_bms_sids, proxy
            )
            for chunk in venue_chunks
        ]
        for future in as_completed(futures):
            try:
                res, total = future.result()
                city_results.extend(res)
                city_total  += total
            except Exception as e:
                print(f"❌ [BMS][{city_name}] Venue worker exception: {e}")

    if city_results:
        print(f"✅ [BMS] {city_name:<15} -> {reporting_city:<15} | Shows: {len(city_results):<3} | Gross: ₹{city_total:<10,}")

    return city_results, city_total, url


# ================= BMS: CITY-CHUNK WORKER =================

def bms_city_chunk_worker(city_chunk, district_sids):
    """
    Worker handling a flat chunk of (state, city_name, city_slug) tuples for BMS.
    district_sids is a frozenset passed in after District phase completes.
    """
    all_results    = []
    last_valid_url = ""
    proxy          = next(proxy_pool) if proxy_pool else None

    for state_name, city_name, city_slug in city_chunk:
        print(f"\n🚀 [BMS][{state_name}][{city_name}] STARTING FETCH...")
        try:
            results, _, url = fetch_bms_city(city_name, city_slug, state_name, district_sids, proxy)
            all_results.extend(results)
            if url:
                last_valid_url = url
        except Exception as e:
            print(f"❌ [BMS][{state_name}][{city_name}] Fatal error: {e}")

    return all_results, last_valid_url


# ================= EXCEL GENERATOR =================

def generate_consolidated_excel(all_results, filename):
    print("\nGenerating Consolidated Excel Report...")
    wb          = Workbook()
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    # 1. STATE WISE
    ws_state = wb.active
    ws_state.title = "State Wise"
    ws_state.append(["State", "Cities", "Theatres", "Shows", "Total Seats", "Booked Seats", "Total Gross", "Booked Gross", "Occ %"])
    state_map, city_tracker, theatre_tracker = {}, {}, {}

    for r in all_results:
        st = r["state"]
        if st not in state_map:
            state_map[st]    = {"shows": 0, "t_seats": 0, "b_seats": 0, "p_gross": 0, "b_gross": 0}
            city_tracker[st] = set(); theatre_tracker[st] = set()
        d = state_map[st]
        d["shows"] += 1; d["t_seats"] += r["total_tickets"]; d["b_seats"] += r["booked_tickets"]
        d["p_gross"] += r["total_gross"]; d["b_gross"] += r["booked_gross"]
        city_tracker[st].add(r["city"]); theatre_tracker[st].add(r["venue"])

    for st, d in state_map.items():
        avg_occ = round((d["b_seats"] / d["t_seats"]) * 100, 2) if d["t_seats"] > 0 else 0
        ws_state.append([st, len(city_tracker[st]), len(theatre_tracker[st]), d["shows"],
                         d["t_seats"], d["b_seats"], d["p_gross"], d["b_gross"], avg_occ])

    # 2. CITY WISE
    ws_city = wb.create_sheet(title="City Wise")
    ws_city.append(["State", "City", "Theatres", "Shows", "Total Seats", "Booked Seats", "Total Gross", "Booked Gross", "Occ %"])
    city_map, city_theatre_tracker = {}, {}

    for r in all_results:
        k = (r["state"], r["city"])
        if k not in city_map:
            city_map[k]             = {"shows": 0, "t_seats": 0, "b_seats": 0, "p_gross": 0, "b_gross": 0}
            city_theatre_tracker[k] = set()
        d = city_map[k]
        d["shows"] += 1; d["t_seats"] += r["total_tickets"]; d["b_seats"] += r["booked_tickets"]
        d["p_gross"] += r["total_gross"]; d["b_gross"] += r["booked_gross"]
        city_theatre_tracker[k].add(r["venue"])

    for (st, ct), d in city_map.items():
        avg_occ = round((d["b_seats"] / d["t_seats"]) * 100, 2) if d["t_seats"] > 0 else 0
        ws_city.append([st, ct, len(city_theatre_tracker[(st, ct)]), d["shows"],
                        d["t_seats"], d["b_seats"], d["p_gross"], d["b_gross"], avg_occ])

    # 3. THEATRE WISE
    ws_th = wb.create_sheet(title="Theatre Wise")
    ws_th.append(["Source", "State", "City", "Venue", "Shows", "Total Seats", "Booked Seats", "Total Gross", "Booked Gross", "Occ %"])
    th_map = {}
    for r in all_results:
        k = (r["source"], r["state"], r["city"], r["venue"])
        if k not in th_map:
            th_map[k] = {"shows": 0, "t_seats": 0, "b_seats": 0, "p_gross": 0, "b_gross": 0}
        d = th_map[k]
        d["shows"] += 1; d["t_seats"] += r["total_tickets"]; d["b_seats"] += r["booked_tickets"]
        d["p_gross"] += r["total_gross"]; d["b_gross"] += r["booked_gross"]

    for (src, st, ct, vn), d in th_map.items():
        avg_occ = round((d["b_seats"] / d["t_seats"]) * 100, 2) if d["t_seats"] > 0 else 0
        ws_th.append([src, st, ct, vn, d["shows"], d["t_seats"], d["b_seats"],
                      d["p_gross"], d["b_gross"], avg_occ])

    # 4. SHOW WISE
    ws_show = wb.create_sheet(title="Show Wise")
    ws_show.append(["Source", "State", "City", "Venue", "Time", "SID",
                    "Total Seats", "Booked Seats", "Total Gross", "Booked Gross", "Occ %"])
    for r in all_results:
        ws_show.append([r["source"], r["state"], r["city"], r["venue"],
                        r["normalized_show_time"], r["sid"],
                        r["total_tickets"], r["booked_tickets"],
                        r["total_gross"], r["booked_gross"], r["occupancy"]])

    # 5. SUMMARY
    ws_sum      = wb.create_sheet(title="Summary")
    agg_p_gross = sum(r["total_gross"]    for r in all_results)
    agg_b_gross = sum(r["booked_gross"]   for r in all_results)
    agg_t_seats = sum(r["total_tickets"]  for r in all_results)
    agg_b_seats = sum(r["booked_tickets"] for r in all_results)
    overall_occ = round((agg_b_seats / agg_t_seats) * 100, 2) if agg_t_seats > 0 else 0

    ws_sum.append(["Metric", "Value"])
    for row in [("States Processed", len(state_map)), ("Total Cities", len(city_map)),
                ("Total Shows", len(all_results)), ("Total Booked Gross", agg_b_gross),
                ("Overall Occupancy %", overall_occ),
                ("Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))]:
        ws_sum.append(list(row))

    path = os.path.join(reports_dir, filename)
    wb.save(path)
    print(f"Consolidated Excel Saved: {path}")


# ================= MAIN EXECUTION FLOW =================

if __name__ == "__main__":
    # ── Load configs ──────────────────────────────────────────────────────────
    if not os.path.exists(DISTRICT_CONFIG_PATH) or not os.path.exists(BMS_CONFIG_PATH):
        print("❌ Config files missing. Exiting.")
        exit(1)

    with open(DISTRICT_CONFIG_PATH, 'r', encoding='utf-8') as f:
        district_config = json.load(f)
    with open(BMS_CONFIG_PATH, 'r', encoding='utf-8') as f:
        bms_config = json.load(f)

    # Build flat city lists
    district_flat = [
        (state, city)
        for state in INPUT_STATE_LIST
        for city in district_config.get(state, [])
    ]
    bms_flat = [
        (state, city['name'], city['slug'])
        for state in INPUT_STATE_LIST
        for city in bms_config.get(state, [])
    ]

    total_d = len(district_flat)
    total_b = len(bms_flat)
    print(f"🎬 Parallel States run — District: {total_d} cities | BMS: {total_b} cities")
    print(f"   District workers : {MAX_WORKERS}  (~{math.ceil(total_d / MAX_WORKERS)} cities each)")
    print(f"   BMS city-workers : {MAX_WORKERS}  (~{math.ceil(total_b / MAX_WORKERS)} cities each)")
    print(f"   BMS venue-workers: {MAX_WORKERS}  (per city, inside each BMS city-worker)\n")

    d_chunk_size    = math.ceil(total_d / MAX_WORKERS)
    b_chunk_size    = math.ceil(total_b / MAX_WORKERS)
    district_chunks = [district_flat[i:i + d_chunk_size] for i in range(0, total_d, d_chunk_size)]
    bms_chunks      = [bms_flat[i:i + b_chunk_size]      for i in range(0, total_b, b_chunk_size)]

    all_dist_data  = []
    all_bms_data   = []
    last_valid_url = ""

    # ── Phase 1: District workers ─────────────────────────────────────────────
    # Must complete first so we can hand district_known_sids to BMS workers.
    # Within this phase all MAX_WORKERS District workers run in parallel.
    print("🚦 Phase 1 — Running District workers in parallel...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as district_pool:
        district_futures = {
            district_pool.submit(district_worker, chunk): f"District-Worker-{i}"
            for i, chunk in enumerate(district_chunks)
        }
        done, _ = wait(district_futures.keys())
        for future in done:
            label = district_futures[future]
            try:
                results = future.result()
                all_dist_data.extend(results)
                print(f"✅ {label} done — {len(results)} District shows collected.")
            except Exception as e:
                print(f"❌ {label} raised an exception: {e}")

    district_known_sids = frozenset(r['sid'] for r in all_dist_data if r['sid'])
    print(f"\n📋 District complete — {len(all_dist_data)} shows, {len(district_known_sids)} unique SIDs.")

    # Save a mid-run District-only Excel (matches original behaviour)
    if all_dist_data:
        ts_mid = datetime.now().strftime("%H%M")
        generate_consolidated_excel(all_dist_data, f"District_Only_{ts_mid}.xlsx")

    # ── Phase 2: BMS workers (parallel, using district SIDs) ──────────────────
    print("\n🚦 Phase 2 — Running BMS workers in parallel...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as bms_pool:
        bms_futures = {
            bms_pool.submit(bms_city_chunk_worker, chunk, district_known_sids): f"BMS-Worker-{i}"
            for i, chunk in enumerate(bms_chunks)
        }
        done, not_done = wait(bms_futures.keys())
        for future in done:
            label = bms_futures[future]
            try:
                results, url = future.result()
                all_bms_data.extend(results)
                if url:
                    last_valid_url = url
                print(f"✅ {label} done — {len(results)} BMS shows collected.")
            except Exception as e:
                print(f"❌ {label} raised an exception: {e}")
        if not_done:
            print(f"⚠️  {len(not_done)} BMS worker(s) did not complete.")

    # ── Phase 3: Merge (safe — all workers finished) ──────────────────────────

    def dedup_same_platform(records, source_label):
        """
        Remove duplicate show records produced by parallel workers of the same source.
        A duplicate is defined as two records sharing the same SID.
        When duplicates exist, keep the one with the higher booked_gross.
        """
        seen    = {}
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

    all_dist_data = dedup_same_platform(all_dist_data, "District")
    all_bms_data  = dedup_same_platform(all_bms_data,  "BMS")

    print(f"\n🔄 Merging {len(all_dist_data)} District + {len(all_bms_data)} BMS shows...")

    final_data     = []
    SEAT_TOLERANCE = 5

    district_index = defaultdict(list)
    for r in all_dist_data:
        key = (r['state'], r['city'], r['normalized_show_time'])
        district_index[key].append(r)

    for bms in all_bms_data:
        key         = (bms['state'], bms['city'], bms['normalized_show_time'])
        candidates  = district_index.get(key, [])
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

        # 4. Fuzzy venue + strict price set
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
                    match_found.update({
                        'total_tickets':   bms['total_tickets'],
                        'booked_tickets':  bms['booked_tickets'],
                        'total_gross':     bms['total_gross'],
                        'booked_gross':    bms['booked_gross'],
                        'occupancy':       bms['occupancy'],
                        'seat_category_map': bms['seat_category_map'],
                        'price_seat_map':  bms['price_seat_map'],
                        'seat_signature':  bms['seat_signature'],
                    })
                final_data.append(match_found)
        else:
            final_data.append(bms)

    for sublist in district_index.values():
        final_data.extend(sublist)

    # ── Phase 4: Reports ──────────────────────────────────────────────────────
    if final_data:
        ts_final        = datetime.now().strftime("%Y%m%d_%H%M%S")
        ref_url_final   = last_valid_url if last_valid_url else DISTRICT_URL_TEMPLATE.format(city="city")
        extracted_movie = extract_movie_name_from_url(ref_url_final)

        generate_consolidated_excel(final_data, f"Total_States_Report_{ts_final}.xlsx")

        generate_premium_states_image_report(
            final_data,
            f"reports/Total_States_Report_Premium_{ts_final}.png",
            movie_name=extracted_movie,
            show_date=SHOW_DATE,
        )
        generate_hybrid_states_html_report(
            final_data,
            f"reports/Total_States_Report_{ts_final}.html",
            movie_name=extracted_movie,
            show_date=SHOW_DATE,
        )

        print(f"\n🏁 All done. Reports saved with timestamp {ts_final}")
    else:
        print("❌ No data found.")