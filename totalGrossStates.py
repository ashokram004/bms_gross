import json
import os
import time
import random
from datetime import datetime
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from openpyxl import Workbook
from fake_useragent import UserAgent

# --- IMPORT IMAGE GENERATORS ---
from utils.generateDistrictMultiStateImageReport import generate_multi_state_image_report
from utils.generateHybridStatesImageReport import generate_hybrid_image_report

# ================= CONFIGURATION =================
# Shared Settings
INPUT_STATE_LIST = ["Andhra Pradesh", "Telangana"] 
SHOW_DATE = "2026-01-25"

# Config Paths
DISTRICT_CONFIG_PATH = os.path.join("utils", "district_cities_config.json")
BMS_CONFIG_PATH = os.path.join("utils", "bms_cities_config.json")

# URLs
DISTRICT_URL_BASE = "https://www.district.in/movies/mana-shankara-varaprasad-garu-movie-tickets-in-"
BMS_URL_TEMPLATE = "https://in.bookmyshow.com/movies/{city}/mana-shankara-vara-prasad-garu/buytickets/ET00457184/20260124"

BMS_KEY = "kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"
BOOKED_CODES = {"2"} 

# ================= SHARED DRIVER =================
def get_driver():
    ua = UserAgent()
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("start-maximized")
    options.add_argument(f"user-agent={ua.random}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")
    return webdriver.Chrome(options=options)

# ================= PART 1: DISTRICT LOGIC =================
def fetch_district_data(driver):
    print("\n🚀 STARTING DISTRICT APP PROCESS...")
    if not os.path.exists(DISTRICT_CONFIG_PATH):
        print(f"❌ District Config missing: {DISTRICT_CONFIG_PATH}")
        return []

    with open(DISTRICT_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    results = []
    processed_sids = set() 
    
    for state in INPUT_STATE_LIST:
        cities = config.get(state, [])
        if not cities:
            print(f"⚠️ No District cities found for {state}")
            continue

        for city in cities:
            url = f"{DISTRICT_URL_BASE}{city['slug']}-MV203929?fromdate={SHOW_DATE}"
            print(f"🌐 [{state}] Fetching {city['name']}...", end="\r")
            
            try:
                driver.get(url)
                time.sleep(1.5)
                html = driver.page_source
                
                marker = 'id="__NEXT_DATA__"'
                idx = html.find(marker)
                if idx == -1: continue
                
                start = html.find('>', idx) + 1
                end = html.find('</script>', start)
                data = json.loads(html[start:end])
                
                sessions = data['props']['pageProps']['data']['serverState']['movieSessions']
                key = list(sessions.keys())[0]
                cinemas = sessions[key]['pageData']['nearbyCinemas']

                city_res = []
                for cin in cinemas:
                    venue = cin['cinemaInfo']['name']
                    for s in cin.get('sessions', []):
                        sid = s.get('sid', '')

                        if sid in processed_sids: continue
                        processed_sids.add(sid)
                        
                        b_gross, p_gross, b_tkts, t_tkts = 0, 0, 0, 0
                        for a in s.get('areas', []):
                            tot, av, pr = a['sTotal'], a['sAvail'], a['price']
                            bk = tot - av
                            b_tkts += bk; t_tkts += tot
                            b_gross += (bk*pr); p_gross += (tot*pr)
                        
                        occ = round((b_tkts/t_tkts)*100, 2) if t_tkts else 0
                        
                        city_res.append({
                            "source": "district", 
                            "sid": str(sid),
                            "state": state, 
                            "city": city['name'], 
                            "venue": venue,
                            "showTime": s['showTime'], 
                            "total_tickets": t_tkts,
                            "booked_tickets": b_tkts, 
                            "total_gross": p_gross,
                            "booked_gross": b_gross, 
                            "occupancy": occ
                        })
                
                if city_res:
                    gross = sum(x['booked_gross'] for x in city_res)
                    print(f"✅ {city['name']:<15} | Shows: {len(city_res):<3} | Gross: ₹{gross:<10,}")
                    results.extend(city_res)
                else:
                    print(f"⚪ {city['name']:<15} | No NEW shows found.                    ")
            except Exception: pass
            
    return results

# ================= PART 2: BMS LOGIC =================
def decrypt_data(enc):
    try:
        decoded = b64decode(enc)
        cipher = AES.new(BMS_KEY.encode(), AES.MODE_CBC, iv=bytes(16))
        return unpad(cipher.decrypt(decoded), AES.block_size).decode()
    except: return None

def extract_category_map(decrypted):
    header = decrypted.split("||")[0]
    category_map = {}
    for part in header.split("|"):
        pieces = part.split(":")
        if len(pieces) >= 3:
            category_map[pieces[1]] = pieces[2]
    return category_map

def calculate_bms_collection(decrypted, price_map):
    header, rows_part = decrypted.split("||")
    rows = rows_part.split("|")
    category_map = extract_category_map(decrypted)

    seats_map, booked_map = {}, {}

    for row in rows:
        if not row: continue
        parts = row.split(":")
        if len(parts) < 3: continue
        elif len(parts) > 3: block_letter = parts[3][0]
        else: block_letter = parts[2][0]

        area_code = category_map.get(block_letter)
        if not area_code: continue

        for seat in parts:
            if len(seat) < 2: continue
            status = seat[1]
            if seat[0] == block_letter and status in ("1", "2"):
                seats_map[area_code] = seats_map.get(area_code, 0) + 1
            if status in BOOKED_CODES:
                booked_map[area_code] = booked_map.get(area_code, 0) + 1

    t_tkts = b_tkts = t_gross = b_gross = 0

    for area_code, total in seats_map.items():
        booked = booked_map.get(area_code, 0)
        price = price_map.get(area_code, 0)
        t_tkts += total
        b_tkts += booked
        t_gross += total * price
        b_gross += booked * price

    occ = round((b_tkts / t_tkts) * 100, 2) if t_tkts else 0
    return t_tkts, b_tkts, int(t_gross), int(b_gross), occ

def fetch_bms_data():
    print("\n🚀 STARTING BMS PROCESS (Dynamic from Config)...")
    
    if not os.path.exists(BMS_CONFIG_PATH):
        print(f"❌ BMS Config missing at {BMS_CONFIG_PATH}")
        return []

    # Load BMS Config
    with open(BMS_CONFIG_PATH, 'r', encoding='utf-8') as f:
        bms_config = json.load(f)

    results = []
    
    # Loop through Requested States
    for state in INPUT_STATE_LIST:
        cities = bms_config.get(state, [])
        
        if not cities:
            print(f"⚠️ No BMS cities found for state: {state}")
            continue

        print(f"📍 Processing {len(cities)} cities in {state} for BMS...")

        for city_obj in cities:
            clean_city = city_obj['name']
            city_slug = city_obj['slug']
            
            url = BMS_URL_TEMPLATE.format(city=city_slug)
            print(f"🌍 BMS Fetching: {clean_city} ({state})...", end="\r")

            # FRESH DRIVER PER CITY
            driver = get_driver()
            try:
                driver.get(url)
                time.sleep(2)
                html = driver.page_source
                
                marker = "window.__INITIAL_STATE__"
                start = html.find(marker)
                if start == -1: 
                    # print(f"⚠️ Blocked/Invalid: {clean_city}")
                    continue

                start = html.find("{", start)
                brace, end = 0, start
                while end < len(html):
                    if html[end] == "{": brace += 1
                    elif html[end] == "}": brace -= 1
                    if brace == 0: break
                    end += 1
                
                state_data = json.loads(html[start:end+1])
                venues = []
                try:
                    sbe = state_data.get("showtimesByEvent")
                    dc = sbe.get("currentDateCode")
                    widgets = sbe["showDates"][dc]["dynamic"]["data"]["showtimeWidgets"]
                    for w in widgets:
                        if w.get("type") == "groupList":
                            for g in w["data"]:
                                if g.get("type") == "venueGroup": venues = g["data"]
                except: venues = []

                city_res = []
                for v in venues:
                    v_name = v["additionalData"]["venueName"]
                    v_code = v["additionalData"]["venueCode"]
                    
                    for show in v.get("showtimes", []):
                        sid = show["additionalData"]["sessionId"]
                        show_time = show["title"]
                        cats = show["additionalData"].get("categories", [])
                        price_map = {c["areaCatCode"]: float(c["curPrice"]) for c in cats}
                        
                        api = "https://services-in.bookmyshow.com/doTrans.aspx"
                        js = f"""
                        var cb = arguments[0]; var x = new XMLHttpRequest();
                        x.open("POST", "{api}", true);
                        x.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
                        x.onload = function() {{ cb(x.responseText); }};
                        x.send("strCommand=GETSEATLAYOUT&strAppCode=WEB&strVenueCode={v_code}&strParam1={sid}&strParam2=WEB&strParam5=Y&strFormat=json");
                        """
                        
                        try:
                            resp = driver.execute_async_script(js)
                            j_resp = json.loads(resp)["BookMyShow"]
                            
                            if j_resp.get("blnSuccess") == "true":
                                decrypted = decrypt_data(j_resp.get("strData"))
                                t_tkts, b_tkts, t_gross, b_gross, occ = calculate_bms_collection(decrypted, price_map)
                            else:
                                if not price_map: continue
                                FALLBACK_SEATS = 200
                                max_price = max(price_map.values()) if price_map else 100
                                t_tkts, b_tkts = FALLBACK_SEATS, FALLBACK_SEATS
                                t_gross = int(FALLBACK_SEATS * max_price)
                                b_gross, occ = t_gross, 100.0

                            city_res.append({
                                "source": "bms",
                                "sid": str(sid),
                                "state": state,         # Uses loop variable
                                "city": clean_city,     # Uses JSON name
                                "venue": v_name,
                                "showTime": show_time,
                                "total_tickets": t_tkts,
                                "booked_tickets": b_tkts,
                                "total_gross": t_gross,
                                "booked_gross": b_gross,
                                "occupancy": occ
                            })
                        except: pass
                    
                        time.sleep(1)
                
                if city_res:
                    gross = sum(x['booked_gross'] for x in city_res)
                    print(f"✅ BMS {clean_city:<15} | Shows: {len(city_res):<3} | Gross: ₹{gross:<10,}")
                    results.extend(city_res)

            except Exception as e:
                pass
            finally:
                driver.quit()

    return results

# ================= PART 3: EXCEL GENERATOR =================
def generate_consolidated_excel(all_results, filename):
    wb = Workbook()
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    # 1. STATE WISE
    ws_state = wb.active
    ws_state.title = "State Wise"
    ws_state.append(["State", "Cities", "Theatres", "Shows", "Total Seats", "Booked Seats", "Total Gross ₹", "Booked Gross ₹", "Occ %"])
    
    state_map = {}
    city_tracker, theatre_tracker = {}, {}

    for r in all_results:
        st = r["state"]
        if st not in state_map:
            state_map[st] = {"shows":0, "t_seats":0, "b_seats":0, "p_gross":0, "b_gross":0}
            city_tracker[st] = set(); theatre_tracker[st] = set()
        
        d = state_map[st]
        d["shows"] += 1; d["t_seats"] += r["total_tickets"]; d["b_seats"] += r["booked_tickets"]
        d["p_gross"] += r["total_gross"]; d["b_gross"] += r["booked_gross"]
        city_tracker[st].add(r["city"]); theatre_tracker[st].add(r["venue"])

    for st, d in state_map.items():
        avg_occ = round((d["b_seats"] / d["t_seats"]) * 100, 2) if d["t_seats"] > 0 else 0
        ws_state.append([st, len(city_tracker[st]), len(theatre_tracker[st]), d["shows"], d["t_seats"], d["b_seats"], d["p_gross"], d["b_gross"], avg_occ])

    # 2. CITY WISE
    ws_city = wb.create_sheet(title="City Wise")
    ws_city.append(["State", "City", "Theatres", "Shows", "Total Seats", "Booked Seats", "Total Gross ₹", "Booked Gross ₹", "Occ %"])
    city_map, city_theatre_tracker = {}, {}

    for r in all_results:
        k = (r["state"], r["city"])
        if k not in city_map:
            city_map[k] = {"shows":0, "t_seats":0, "b_seats":0, "p_gross":0, "b_gross":0}
            city_theatre_tracker[k] = set()
        d = city_map[k]
        d["shows"] += 1; d["t_seats"] += r["total_tickets"]; d["b_seats"] += r["booked_tickets"]
        d["p_gross"] += r["total_gross"]; d["b_gross"] += r["booked_gross"]
        city_theatre_tracker[k].add(r["venue"])

    for (st, ct), d in city_map.items():
        avg_occ = round((d["b_seats"] / d["t_seats"]) * 100, 2) if d["t_seats"] > 0 else 0
        ws_city.append([st, ct, len(city_theatre_tracker[(st, ct)]), d["shows"], d["t_seats"], d["b_seats"], d["p_gross"], d["b_gross"], avg_occ])

    # 3. THEATRE WISE
    ws_th = wb.create_sheet(title="Theatre Wise")
    ws_th.append(["Source", "State", "City", "Venue", "Shows", "Total Seats", "Booked Seats", "Total Gross ₹", "Booked Gross ₹", "Occ %"])
    th_map = {}
    for r in all_results:
        k = (r["source"], r["state"], r["city"], r["venue"])
        if k not in th_map: th_map[k] = {"shows":0, "t_seats":0, "b_seats":0, "p_gross":0, "b_gross":0}
        d = th_map[k]
        d["shows"] += 1; d["t_seats"] += r["total_tickets"]; d["b_seats"] += r["booked_tickets"]
        d["p_gross"] += r["total_gross"]; d["b_gross"] += r["booked_gross"]

    for (src, st, ct, vn), d in th_map.items():
        avg_occ = round((d["b_seats"] / d["t_seats"]) * 100, 2) if d["t_seats"] > 0 else 0
        ws_th.append([src, st, ct, vn, d["shows"], d["t_seats"], d["b_seats"], d["p_gross"], d["b_gross"], avg_occ])

    # 4. SHOW WISE
    ws_show = wb.create_sheet(title="Show Wise")
    ws_show.append(["Source", "State", "City", "Venue", "Time", "SID", "Total Seats", "Booked Seats", "Total Gross ₹", "Booked Gross ₹", "Occ %"])
    for r in all_results:
        ws_show.append([r["source"], r["state"], r["city"], r["venue"], r["showTime"], r["sid"], r["total_tickets"], r["booked_tickets"], r["total_gross"], r["booked_gross"], r["occupancy"]])

    # 5. SUMMARY
    ws_sum = wb.create_sheet(title="Summary")
    agg_p_gross = sum(r["total_gross"] for r in all_results)
    agg_b_gross = sum(r["booked_gross"] for r in all_results)
    agg_t_seats = sum(r["total_tickets"] for r in all_results)
    agg_b_seats = sum(r["booked_tickets"] for r in all_results)
    agg_shows = len(all_results)
    overall_occ = round((agg_b_seats / agg_t_seats) * 100, 2) if agg_t_seats > 0 else 0
    
    ws_sum.append(["Metric", "Value"])
    ws_sum.append(["States Processed", len(state_map)])
    ws_sum.append(["Total Cities", len(city_map)])
    ws_sum.append(["Total Theatres", len(th_map)])
    ws_sum.append(["Total Shows", agg_shows])
    ws_sum.append(["Total Seats (Capacity)", agg_t_seats])
    ws_sum.append(["Total Booked Tickets", agg_b_seats])
    ws_sum.append(["Total Potential Gross (₹)", agg_p_gross])
    ws_sum.append(["Total Booked Gross (₹)", agg_b_gross])
    ws_sum.append(["Overall Occupancy %", overall_occ])
    ws_sum.append(["Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

    path = os.path.join(reports_dir, filename)
    wb.save(path)
    print(f"📊 Consolidated Excel Saved: {path}")

# ================= MAIN EXECUTION FLOW =================
if __name__ == "__main__":
    # 1. DISTRICT (Fast, One Driver)
    d_driver = get_driver()
    district_data = []
    try:
        district_data = fetch_district_data(d_driver)
        if district_data:
            ts = datetime.now().strftime("%H%M")
            generate_consolidated_excel(district_data, f"District_Only_{ts}.xlsx")
            img_path = f"reports/District_Report_{ts}.png"
            ref_url = DISTRICT_URL_BASE + "city?fromdate=" + SHOW_DATE
            generate_multi_state_image_report(district_data, ref_url, img_path)
    finally:
        d_driver.quit() 

    # 2. BMS (Robust, Driver per City)
    bms_data = fetch_bms_data()

    # 3. MERGE LOGIC (Smart Override)
    print("\n🔄 Merging Data Sources (Merging by Session ID)...")
    merged_map = {}
    
    # Load District first
    for r in district_data:
        sid = r["sid"]
        key = sid if sid else f"{r['city']}_{r['venue']}_{r['showTime']}"
        merged_map[key] = r

    # Merge BMS (Override if Gross is higher)
    for r in bms_data:
        sid = r["sid"]
        key = sid if sid else f"{r['city']}_{r['venue']}_{r['showTime']}"
        
        if key in merged_map:
            existing = merged_map[key]
            # Override if BMS found higher gross
            if r["booked_gross"] > existing["booked_gross"]:
                merged_map[key] = r 
        else:
            merged_map[key] = r # New exclusive BMS show

    final_data = list(merged_map.values())
    if final_data:
        ts_final = datetime.now().strftime("%Y%m%d_%H%M%S")
        generate_consolidated_excel(final_data, f"Total_States_Report_{ts_final}.xlsx")
        generate_hybrid_image_report(final_data, DISTRICT_URL_BASE, f"reports/Total_States_Report_{ts_final}.png")
    else:
        print("❌ No data found.")