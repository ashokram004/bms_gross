import os
from urllib.parse import urlparse
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- CONFIGURATION ---
MAX_TOTAL_CITY_ROWS = 50
FONT_PATH_BOLD = "arialbd.ttf"
FONT_PATH_REG = "arial.ttf"

def parse_url_metadata(url):
    """
    Extracts Movie Name and Date from BMS URL dynamically.
    URL Format: .../movies/{city}/{movie-name}/buytickets/{event-code}/{date}
    """
    try:
        path = urlparse(url).path
        parts = [p for p in path.split('/') if p]

        if "buytickets" in parts:
            idx = parts.index("buytickets")
            # Structure: .../movies/city/movie-name/buytickets/code/date
            movie_raw = parts[idx - 1]
            date_raw = parts[-1] 

            movie_name = movie_raw.replace("-", " ").title()
            
            try:
                date_obj = datetime.strptime(date_raw, "%Y%m%d")
                show_date = date_obj.strftime("%d %b %Y")
            except ValueError:
                show_date = date_raw

            return movie_name, show_date

    except Exception:
        pass
    
    return "Movie Collection Report", datetime.now().strftime("%d %b %Y")

def get_fonts():
    try:
        return (ImageFont.truetype(FONT_PATH_BOLD, 28), ImageFont.truetype(FONT_PATH_BOLD, 18),
                ImageFont.truetype(FONT_PATH_BOLD, 15), ImageFont.truetype(FONT_PATH_REG, 15))
    except IOError:
        d = ImageFont.load_default()
        return d, d, d, d

def generate_multi_state_image_report(all_results, reference_url, output_path):
    print("🎨 Generating Formal BMS Multi-State Image Report...")
    movie_name, show_date = parse_url_metadata(reference_url)
    f_large, f_header, f_bold, f_reg = get_fonts()

    # --- 1. DATA AGGREGATION ---
    state_groups = {}
    for r in all_results:
        st, ct = r.get("state", "Unknown"), r.get("city", "Unknown")
        
        if st not in state_groups: state_groups[st] = {}
        if ct not in state_groups[st]:
            state_groups[st][ct] = {"gross": 0, "tickets": 0, "shows": 0, "seats": 0}
        
        target = state_groups[st][ct]
        target["gross"] += r["booked_gross"]
        target["tickets"] += r["booked_tickets"]
        target["shows"] += 1
        target["seats"] += r["total_tickets"]

    # --- 2. SELECTION LOGIC ---
    num_states = len(state_groups)
    cities_per_state = MAX_TOTAL_CITY_ROWS // num_states if num_states > 0 else 50
    
    city_list, state_summary = [], []
    grand_total_seats = 0 # To calculate global occupancy
    
    for state, cities in state_groups.items():
        st_gross = sum(c["gross"] for c in cities.values())
        st_tkts = sum(c["tickets"] for c in cities.values())
        st_shows = sum(c["shows"] for c in cities.values())
        st_seats = sum(c["seats"] for c in cities.values())
        st_occ = round((st_tkts / st_seats) * 100, 1) if st_seats else 0
        
        state_summary.append({"state": state, "gross": st_gross, "tickets": st_tkts, "shows": st_shows, "occ": st_occ})
        grand_total_seats += st_seats 

        # Sort cities by Gross
        sorted_cities = sorted(cities.items(), key=lambda x: x[1]["gross"], reverse=True)
        for name, data in sorted_cities[:cities_per_state]:
            occ = round((data["tickets"] / data["seats"]) * 100, 1) if data["seats"] else 0
            city_list.append({
                "state": state, "city": name.replace("-", " ").title(),
                "gross": data["gross"], "tickets": data["tickets"], "shows": data["shows"], "occ": occ
            })

    # Sort Global Lists by Gross
    city_list.sort(key=lambda x: x["gross"], reverse=True)
    state_summary.sort(key=lambda x: x["gross"], reverse=True)

    # --- 3. COLORS & LAYOUT ---
    C_ORANGE, C_BLUE, C_GREY, C_GREEN = (237, 125, 49), (189, 215, 238), (217, 217, 217), (169, 208, 142)
    padding, row_h, head_h = 25, 30, 45
    col_w = [300, 80, 100, 140, 80]
    
    img_w = sum(col_w) + (padding * 2)
    # Dynamic Height Calculation
    img_h = padding + 150 + (len(state_summary) * row_h) + (len(city_list) * row_h) + (head_h * 2) + padding + 20 

    img = Image.new('RGB', (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    curr_y = padding

    # Title & Metadata
    draw.text((padding, curr_y), movie_name, font=f_large, fill=C_ORANGE)
    curr_y += 40
    gen_time = datetime.now().strftime("%I:%M %p")
    subtitle = f"BMS Multi-State Collection Report | {show_date} | Generated at: {gen_time}"
    draw.text((padding, curr_y), subtitle, font=f_reg, fill=(100, 100, 100))
    curr_y += 50

    # SECTION: State Summary
    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+head_h)], fill=C_ORANGE)
    draw.text((img_w//2, curr_y+head_h/2), "STATE PERFORMANCE SUMMARY", font=f_header, fill=(255, 255, 255), anchor="mm")
    curr_y += head_h

    for st in state_summary:
        draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=C_GREY)
        draw.text((padding+10, curr_y+row_h/2), st["state"], font=f_bold, fill=(0,0,0), anchor="lm")
        
        x = padding + 300
        # Shows
        draw.text((x+40, curr_y+row_h/2), str(st["shows"]), font=f_bold, fill=(0,0,0), anchor="mm")
        # Tickets
        draw.text((x+130, curr_y+row_h/2), str(st["tickets"]), font=f_bold, fill=(0,0,0), anchor="mm")
        # Gross
        draw.text((x+310, curr_y+row_h/2), f"{st['gross']:,.0f}", font=f_bold, fill=(0,0,0), anchor="rm")
        # Occ %
        draw.text((x+360, curr_y+row_h/2), f"{st['occ']}%", font=f_bold, fill=(0,0,0), anchor="mm")
        curr_y += row_h

    curr_y += 30

    # SECTION: Top Cities Breakdown
    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+head_h)], fill=C_ORANGE)
    draw.text((img_w//2, curr_y+head_h/2), f"TOP {len(city_list)} AREAS BY REVENUE", font=f_header, fill=(255, 255, 255), anchor="mm")
    curr_y += head_h

    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=C_BLUE)
    headers, x = ["City (State)", "Shows", "Tickets", "Gross (INR)", "Occ %"], padding
    for i, h in enumerate(headers):
        align = "lm" if i==0 else "mm"
        pos = x+10 if i==0 else x+col_w[i]/2
        draw.text((pos, curr_y+row_h/2), h, font=f_bold, fill=(0,0,0), anchor=align)
        x += col_w[i]
    curr_y += row_h

    for i, ct in enumerate(city_list):
        bg = (255, 255, 255) if i % 2 == 0 else (242, 242, 242)
        draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=bg)
        
        city_display = f"{ct['city']} ({ct['state'][:2].upper()})"
        draw.text((padding+10, curr_y+row_h/2), city_display, font=f_reg, fill=(0,0,0), anchor="lm")
        
        x = padding + 300
        draw.text((x+40, curr_y+row_h/2), str(ct["shows"]), font=f_reg, fill=(0,0,0), anchor="mm")
        draw.text((x+130, curr_y+row_h/2), str(ct["tickets"]), font=f_reg, fill=(0,0,0), anchor="mm")
        draw.text((x+310, curr_y+row_h/2), f"{ct['gross']:,.0f}", font=f_reg, fill=(0,0,0), anchor="rm")
        draw.text((x+360, curr_y+row_h/2), f"{ct['occ']}%", font=f_reg, fill=(0,0,0), anchor="mm")
        curr_y += row_h

    # SECTION: Footer (Grand Total)
    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=C_GREEN)
    draw.text((padding+10, curr_y+row_h/2), "Total", font=f_bold, fill=(0,0,0), anchor="lm")
    
    t_gross = sum(s["gross"] for s in state_summary)
    t_tkts = sum(s["tickets"] for s in state_summary)
    t_shows = sum(s["shows"] for s in state_summary)
    
    # Global Occupancy
    t_occ = round((t_tkts / grand_total_seats) * 100, 1) if grand_total_seats > 0 else 0

    x = padding + 300
    draw.text((x+40, curr_y+row_h/2), str(t_shows), font=f_bold, fill=(0,0,0), anchor="mm")
    draw.text((x+130, curr_y+row_h/2), str(t_tkts), font=f_bold, fill=(0,0,0), anchor="mm")
    draw.text((x+310, curr_y+row_h/2), f"{t_gross:,.0f}", font=f_bold, fill=(0,0,0), anchor="rm")
    draw.text((x+360, curr_y+row_h/2), f"{t_occ}%", font=f_bold, fill=(0,0,0), anchor="mm")

    img.save(output_path)
    print(f"🖼️ Full BMS Image Report Saved: {output_path}")