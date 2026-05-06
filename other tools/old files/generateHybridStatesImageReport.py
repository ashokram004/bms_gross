import os
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- CONFIGURATION ---
MAX_TOTAL_CITY_ROWS = 50
FONT_PATH_BOLD = "arialbd.ttf"
FONT_PATH_REG = "arial.ttf"

def parse_metadata(reference_url, source_type="district"):
    """ Extracts Movie Name and Date based on the last valid URL used. """
    try:
        parsed = urlparse(reference_url)
        path_parts = [p for p in parsed.path.split('/') if p]
        
        movie_name = "Collection Report"
        show_date = datetime.now().strftime("%d %b %Y")

        if source_type == "district":
            if len(path_parts) >= 2 and "movies" in path_parts:
                slug = path_parts[1]
                if "-movie-tickets-in-" in slug:
                    movie_name = slug.split("-movie-tickets-in-")[0].replace("-", " ").title()
            q = parse_qs(parsed.query)
            if 'fromdate' in q:
                show_date = datetime.strptime(q['fromdate'][0], "%Y-%m-%d").strftime("%d %b %Y")

        elif source_type == "bms":
            # BMS Template: .../movies/{city}/{movie-name}/buytickets/...
            if "buytickets" in path_parts:
                idx = path_parts.index("buytickets")
                movie_name = path_parts[idx - 1].replace("-", " ").title()
                raw_date = path_parts[-1]
                try:
                    show_date = datetime.strptime(raw_date, "%Y%m%d").strftime("%d %b %Y")
                except: pass

        return movie_name, show_date
    except:
        return "Collection Report", datetime.now().strftime("%d %b %Y")

def get_fonts():
    try:
        return (ImageFont.truetype(FONT_PATH_BOLD, 28), ImageFont.truetype(FONT_PATH_BOLD, 18),
                ImageFont.truetype(FONT_PATH_BOLD, 15), ImageFont.truetype(FONT_PATH_REG, 15))
    except:
        d = ImageFont.load_default()
        return d, d, d, d

def generate_hybrid_image_report(all_results, ref_url, output_path, ref_source="district"):
    print("🎨 Generating Consolidated Hybrid Image Report...")
    movie_name, show_date = parse_metadata(ref_url, ref_source)
    f_large, f_header, f_bold, f_reg = get_fonts()

    # --- 1. AGGREGATE DATA (MERGED) ---
    state_groups = {}
    for r in all_results:
        st, ct = r.get("state", "Unknown"), r.get("city", "Unknown")
        # Handle BMS data which might not have 'state' populated originally
        if st == "Unknown" and ct.lower() in ["hyderabad", "warangal", "nizamabad"]: st = "Telangana"
        elif st == "Unknown": st = "Andhra Pradesh" 

        if st not in state_groups: state_groups[st] = {}
        if ct not in state_groups[st]:
            # Added 'venues' set to track unique theatres
            state_groups[st][ct] = {"gross": 0, "tickets": 0, "shows": 0, "seats": 0, "venues": set()}
        
        t = state_groups[st][ct]
        t["gross"] += r["booked_gross"]
        t["tickets"] += r["booked_tickets"]
        t["shows"] += 1
        t["seats"] += r["total_tickets"]
        t["venues"].add(r["venue"]) # Track unique venue name

    # --- 2. TOP CITY SELECTION ---
    num_states = len(state_groups)
    limit = MAX_TOTAL_CITY_ROWS // num_states if num_states > 0 else 50
    
    city_list, state_summary = [], []
    total_capacity = 0  

    for state, cities in state_groups.items():
        s_gross = sum(c["gross"] for c in cities.values())
        s_tkts = sum(c["tickets"] for c in cities.values())
        s_seats = sum(c["seats"] for c in cities.values())
        s_shows = sum(c["shows"] for c in cities.values())
        # Sum unique venues from all cities in this state
        s_theatres = sum(len(c["venues"]) for c in cities.values())
        
        s_occ = round((s_tkts / s_seats) * 100, 1) if s_seats else 0
        
        state_summary.append({
            "state": state, "gross": s_gross, "tickets": s_tkts, 
            "shows": s_shows, "theatres": s_theatres, "occ": s_occ
        })
        total_capacity += s_seats

        sorted_cities = sorted(cities.items(), key=lambda x: x[1]["gross"], reverse=True)
        for name, d in sorted_cities[:limit]:
            occ = round((d["tickets"] / d["seats"]) * 100, 1) if d["seats"] else 0
            city_list.append({
                "state": state, "city": name.replace("-", " ").title(), 
                "gross": d["gross"], "tickets": d["tickets"], 
                "shows": d["shows"], "theatres": len(d["venues"]), "occ": occ
            })

    city_list.sort(key=lambda x: x["gross"], reverse=True)
    state_summary.sort(key=lambda x: x["gross"], reverse=True)

    # --- 3. DRAWING ---
    colors = [(237, 125, 49), (189, 215, 238), (217, 217, 217), (169, 208, 142)] # Org, Blue, Grey, Grn
    padding, row_h, head_h = 25, 30, 45
    
    # Updated Column Widths: City, Theatres, Shows, Tickets, Gross, Occ
    cw = [260, 70, 70, 90, 130, 70] 
    
    w, h = sum(cw) + padding*2, padding + 150 + (len(state_summary) * row_h) + (len(city_list) * row_h) + head_h*2 + padding + 20
    
    img = Image.new('RGB', (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = padding

    # Title
    draw.text((padding, y), movie_name, font=f_large, fill=colors[0])
    y += 40
    draw.text((padding, y), f"(BMS + District) Report | {show_date} | Generated at: {datetime.now().strftime('%I:%M %p')}", font=f_reg, fill=(80,80,80))
    y += 50

    # --- STATE SUMMARY SECTION ---
    draw.rectangle([(padding, y), (w-padding, y+head_h)], fill=colors[0])
    draw.text((w//2, y+head_h/2), "STATE PERFORMANCE", font=f_header, fill=(255,255,255), anchor="mm")
    y += head_h
    
    for s in state_summary:
        draw.rectangle([(padding, y), (w-padding, y+row_h)], fill=colors[2])
        draw.text((padding+10, y+row_h/2), s["state"], font=f_bold, fill=(0,0,0), anchor="lm")
        
        # New Value Order: Theatres, Shows, Tickets, Gross, Occ
        vals = [str(s["theatres"]), str(s["shows"]), str(s["tickets"]), f"{s['gross']:,.0f}", f"{s['occ']}%"]
        
        # Dynamic X calculation based on Column Widths (cw)
        current_x = padding + cw[0] # Start after City column
        for i, v in enumerate(vals):
            col_w = cw[i+1] # Skip city width
            # Alignment: Right align Gross (index 3), others Center
            align = "rm" if i == 3 else "mm"
            
            if align == "mm":
                px = current_x + (col_w / 2)
            else:
                px = current_x + col_w - 10 # -10 padding for right align
                
            draw.text((px, y+row_h/2), v, font=f_bold, fill=(0,0,0), anchor=align)
            current_x += col_w
            
        y += row_h
    y += 30

    # --- CITY BREAKDOWN SECTION ---
    draw.rectangle([(padding, y), (w-padding, y+head_h)], fill=colors[0])
    draw.text((w//2, y+head_h/2), f"TOP {len(city_list)} CITIES", font=f_header, fill=(255,255,255), anchor="mm")
    y += head_h
    draw.rectangle([(padding, y), (w-padding, y+row_h)], fill=colors[1])
    
    # Headers
    hdrs = ["City", "Theatres", "Shows", "Tickets", "Gross (INR)", "Occ %"]
    x = padding
    for i, t in enumerate(hdrs):
        align = "lm" if i==0 else "mm"
        px = x+10 if i==0 else x + (cw[i]/2)
        draw.text((px, y+row_h/2), t, font=f_bold, fill=(0,0,0), anchor=align)
        x += cw[i]
    y += row_h

    # City Rows
    for i, c in enumerate(city_list):
        bg = (255,255,255) if i%2==0 else (245,245,245)
        draw.rectangle([(padding, y), (w-padding, y+row_h)], fill=bg)
        draw.text((padding+10, y+row_h/2), f"{c['city']} ({c['state'][:2].upper()})", font=f_reg, fill=(0,0,0), anchor="lm")
        
        vals = [str(c["theatres"]), str(c["shows"]), str(c["tickets"]), f"{c['gross']:,.0f}", f"{c['occ']}%"]
        
        current_x = padding + cw[0]
        for j, v in enumerate(vals):
            col_w = cw[j+1]
            align = "rm" if j == 3 else "mm"
            
            if align == "mm":
                px = current_x + (col_w / 2)
            else:
                px = current_x + col_w - 10
                
            draw.text((px, y+row_h/2), v, font=f_reg, fill=(0,0,0), anchor=align)
            current_x += col_w
            
        y += row_h

    # --- FOOTER ---
    draw.rectangle([(padding, y), (w-padding, y+row_h)], fill=colors[3])
    draw.text((padding+10, y+row_h/2), "Total", font=f_bold, fill=(0,0,0), anchor="lm")
    
    tg = sum(s["gross"] for s in state_summary)
    tk = sum(s["tickets"] for s in state_summary)
    ts = sum(s["shows"] for s in state_summary)
    t_th = sum(s["theatres"] for s in state_summary) # Total Theatres
    t_occ = round((tk / total_capacity) * 100, 1) if total_capacity > 0 else 0

    # Draw Totals using same dynamic X logic
    vals = [str(t_th), str(ts), str(tk), f"{tg:,.0f}", f"{t_occ}%"]
    current_x = padding + cw[0]
    
    for i, v in enumerate(vals):
        col_w = cw[i+1]
        align = "rm" if i == 3 else "mm"
        if align == "mm":
            px = current_x + (col_w / 2)
        else:
            px = current_x + col_w - 10
        draw.text((px, y+row_h/2), v, font=f_bold, fill=(0,0,0), anchor=align)
        current_x += col_w

    img.save(output_path)
    print(f"🖼️ Hybrid Report Saved: {output_path}")