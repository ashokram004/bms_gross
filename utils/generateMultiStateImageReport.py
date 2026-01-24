import os
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- CONFIGURATION ---
MAX_TOTAL_CITY_ROWS = 50
FONT_PATH_BOLD = "arialbd.ttf"
FONT_PATH_REG = "arial.ttf"

def parse_url_metadata(url):
    """
    Dynamically extracts movie name and date from District URL.
    """
    try:
        parsed_url = urlparse(url)
        path_parts = [p for p in parsed_url.path.split('/') if p]
        query_params = parse_qs(parsed_url.query)

        # 1. Movie Name: Extract from /movies/{name}-movie-tickets-in-...
        movie_name = "Movie Collection Report"
        if len(path_parts) >= 2 and path_parts[0] == "movies":
            slug = path_parts[1]
            if "-movie-tickets-in-" in slug:
                movie_name = slug.split("-movie-tickets-in-")[0].replace("-", " ").title()

        # 2. Date: Extract from 'fromdate' query param (Default to Jan 25)
        raw_date = query_params.get('fromdate', [None])[0]
        if raw_date:
            show_date = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d %b %Y")
        else:
            show_date = datetime.now().strftime("%d %b %Y")

        return movie_name, show_date
    except:
        return "Movie Collection", datetime.now().strftime("%d %b %Y")

def get_fonts():
    try:
        f_large = ImageFont.truetype(FONT_PATH_BOLD, 28)
        f_header = ImageFont.truetype(FONT_PATH_BOLD, 18)
        f_bold = ImageFont.truetype(FONT_PATH_BOLD, 15)
        f_reg = ImageFont.truetype(FONT_PATH_REG, 15)
    except:
        f_large = f_header = f_bold = f_reg = ImageFont.load_default()
    return f_large, f_header, f_bold, f_reg

def generate_multi_state_image_report(all_results, reference_url, output_path):
    print("🎨 Generating Formal Multi-State Image Report...")
    movie_name, show_date = parse_url_metadata(reference_url)
    f_large, f_header, f_bold, f_reg = get_fonts()

    # --- 1. DATA AGGREGATION ---
    state_groups = {}
    for r in all_results:
        st, ct = r["state"], r["city"]
        if st not in state_groups: state_groups[st] = {}
        if ct not in state_groups[st]:
            state_groups[st][ct] = {"gross": 0, "tickets": 0, "shows": 0, "seats": 0}
        
        target = state_groups[st][ct]
        target["gross"] += r["booked_gross"]
        target["tickets"] += r["booked_tickets"]
        target["shows"] += 1
        target["seats"] += r["total_tickets"]

    # --- 2. ASH'S SELECTION LOGIC ---
    num_states = len(state_groups)
    cities_per_state = MAX_TOTAL_CITY_ROWS // num_states if num_states > 0 else 50
    
    city_list, state_summary = [], []
    for state, cities in state_groups.items():
        st_gross = sum(c["gross"] for c in cities.values())
        st_tkts = sum(c["tickets"] for c in cities.values())
        st_shows = sum(c["shows"] for c in cities.values())
        st_seats = sum(c["seats"] for c in cities.values())
        st_occ = round((st_tkts / st_seats) * 100, 1) if st_seats else 0
        state_summary.append({"state": state, "gross": st_gross, "tickets": st_tkts, "shows": st_shows, "occ": st_occ})

        sorted_cities = sorted(cities.items(), key=lambda x: x[1]["gross"], reverse=True)
        for name, data in sorted_cities[:cities_per_state]:
            occ = round((data["tickets"] / data["seats"]) * 100, 1) if data["seats"] else 0
            city_list.append({
                "state": state, "city": name.replace("-", " ").title(),
                "gross": data["gross"], "tickets": data["tickets"], "shows": data["shows"], "occ": occ
            })

    city_list.sort(key=lambda x: x["gross"], reverse=True)
    state_summary.sort(key=lambda x: x["gross"], reverse=True)

    # --- 3. COLORS & LAYOUT ---
    C_ORANGE, C_BLUE, C_GREY, C_GREEN = (237, 125, 49), (189, 215, 238), (217, 217, 217), (169, 208, 142)
    padding, row_h, head_h = 25, 30, 45
    col_w = [300, 80, 100, 140, 80] # Header columns
    img_w = sum(col_w) + (padding * 2)
    img_h = padding + 150 + (len(state_summary) * row_h) + (len(city_list) * row_h) + (head_h * 2) + padding

    img = Image.new('RGB', (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    curr_y = padding

    # Title & Metadata
    draw.text((padding, curr_y), movie_name, font=f_large, fill=C_ORANGE)
    curr_y += 40
    gen_time = datetime.now().strftime("%I:%M %p")
    subtitle = f"Multi-State Collection Report | Gen: {gen_time} | Date: {show_date}"
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
        # Columns: Shows, Tickets, Gross, Occ
        draw.text((x+40, curr_y+row_h/2), str(st["shows"]), font=f_bold, fill=(0,0,0), anchor="mm")
        draw.text((x+130, curr_y+row_h/2), str(st["tickets"]), font=f_bold, fill=(0,0,0), anchor="mm")
        draw.text((x+310, curr_y+row_h/2), f"{st['gross']:,.0f}", font=f_bold, fill=(0,0,0), anchor="rm")
        draw.text((x+360, curr_y+row_h/2), f"{st['occ']}%", font=f_bold, fill=(0,0,0), anchor="mm")
        curr_y += row_h

    curr_y += 30

    # SECTION: Top Cities Breakdown
    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+head_h)], fill=C_ORANGE)
    draw.text((img_w//2, curr_y+head_h/2), f"TOP {len(city_list)} CITIES BY REVENUE", font=f_header, fill=(255, 255, 255), anchor="mm")
    curr_y += head_h

    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=C_BLUE)
    headers = ["City (State)", "Shows", "Tickets", "Gross (INR)", "Occ %"]
    x = padding
    for i, h in enumerate(headers):
        anchor = "lm" if i==0 else "mm"
        pos = x+10 if i==0 else x+col_w[i]/2
        draw.text((pos, curr_y+row_h/2), h, font=f_bold, fill=(0,0,0), anchor=anchor)
        x += col_w[i]
    curr_y += row_h

    for i, ct in enumerate(city_list):
        bg = (255, 255, 255) if i % 2 == 0 else (242, 242, 242)
        draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=bg)
        draw.text((padding+10, curr_y+row_h/2), f"{ct['city']} ({ct['state'][:2].upper()})", font=f_reg, fill=(0,0,0), anchor="lm")
        x = padding + 300
        # Columns: Shows, Tickets, Gross, Occ
        draw.text((x+40, curr_y+row_h/2), str(ct["shows"]), font=f_reg, fill=(0,0,0), anchor="mm")
        draw.text((x+130, curr_y+row_h/2), str(ct["tickets"]), font=f_reg, fill=(0,0,0), anchor="mm")
        draw.text((x+310, curr_y+row_h/2), f"{ct['gross']:,.0f}", font=f_reg, fill=(0,0,0), anchor="rm")
        draw.text((x+360, curr_y+row_h/2), f"{ct['occ']}%", font=f_reg, fill=(0,0,0), anchor="mm")
        curr_y += row_h

    # SECTION: Footer (Grand Total)
    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=C_GREEN)
    draw.text((padding+10, curr_y+row_h/2), "GRAND TOTAL (ALL STATES)", font=f_bold, fill=(0,0,0), anchor="lm")
    t_gross, t_tkts, t_shows = sum(s["gross"] for s in state_summary), sum(s["tickets"] for s in state_summary), sum(s["shows"] for s in state_summary)
    x = padding + 300
    draw.text((x+40, curr_y+row_h/2), str(t_shows), font=f_bold, fill=(0,0,0), anchor="mm")
    draw.text((x+130, curr_y+row_h/2), str(t_tkts), font=f_bold, fill=(0,0,0), anchor="mm")
    draw.text((x+310, curr_y+row_h/2), f"{t_gross:,.0f}", font=f_bold, fill=(0,0,0), anchor="rm")

    img.save(output_path)
    print(f"🖼️ Full Image Report Saved: {output_path}")