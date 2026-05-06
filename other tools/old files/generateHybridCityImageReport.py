import os
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- CONFIGURATION ---
FONT_PATH_BOLD = "arialbd.ttf"
FONT_PATH_REG = "arial.ttf"

def parse_metadata(url):
    """
    Extracts Movie Name, Date, and City from the URL.
    """
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        
        # Defaults
        movie_name = "Movie Collection"
        city_name = "Hybrid City"
        show_date = datetime.now().strftime("%d %b %Y")

        # --- CASE 1: DISTRICT APP URL ---
        # Pattern: /movies/{movie}-movie-tickets-in-{city}-MV{id}
        if "movies" in path_parts:
            for p in path_parts:
                if "-movie-tickets-in-" in p:
                    parts = p.split("-movie-tickets-in-")
                    if len(parts) > 1:
                        # Movie Name (Left part)
                        movie_name = parts[0].replace("-", " ").title()
                        
                        # City Name (Right part, removing the trailing ID)
                        # "vizag-MV203929" -> "vizag"
                        right_side = parts[1]
                        if "-" in right_side:
                            # Split by dash and drop the last element (the MV ID)
                            city_segments = right_side.split("-")[:-1]
                            city_name = " ".join(city_segments).title()
                        else:
                            city_name = right_side.title()
                    break
            
            # Date from Query
            q = parse_qs(parsed.query)
            if 'fromdate' in q:
                show_date = datetime.strptime(q['fromdate'][0], "%Y-%m-%d").strftime("%d %b %Y")
        
        # --- CASE 2: BOOKMYSHOW URL ---
        # Pattern: /movies/{city}/{movie}/buytickets/{id}/{date}
        elif "buytickets" in path_parts:
            idx = path_parts.index("buytickets")
            if idx >= 2:
                # Movie is i-1
                movie_name = path_parts[idx - 1].replace("-", " ").title()
                # City is i-2
                city_name = path_parts[idx - 2].replace("-", " ").title()
            
            # Date is usually the last part
            raw_date = path_parts[-1]
            try:
                show_date = datetime.strptime(raw_date, "%Y%m%d").strftime("%d %b %Y")
            except: pass

        return movie_name, show_date, city_name
    except:
        return "Movie Collection", datetime.now().strftime("%d %b %Y"), "Hybrid City"

def get_fonts():
    try:
        return (ImageFont.truetype(FONT_PATH_BOLD, 28), ImageFont.truetype(FONT_PATH_BOLD, 18),
                ImageFont.truetype(FONT_PATH_BOLD, 15), ImageFont.truetype(FONT_PATH_REG, 15))
    except:
        d = ImageFont.load_default()
        return d, d, d, d

def generate_hybrid_city_image_report(all_results, ref_url, output_path):
    print("🎨 Generating Hybrid Single City Image Report...")
    movie_name, show_date, city_name = parse_metadata(ref_url)
    f_large, f_header, f_bold, f_reg = get_fonts()

    # --- 1. AGGREGATE BY VENUE ---
    venue_map = {}
    for r in all_results:
        v = r["venue"]
        if v not in venue_map:
            venue_map[v] = {"gross": 0, "tickets": 0, "shows": 0, "seats": 0}
        
        venue_map[v]["gross"] += r["booked_gross"]
        venue_map[v]["tickets"] += r["booked_tickets"]
        venue_map[v]["shows"] += 1
        venue_map[v]["seats"] += r["total_tickets"]

    # Convert to list and Sort by Gross
    venue_list = []
    for v, d in venue_map.items():
        occ = round((d["tickets"] / d["seats"]) * 100, 1) if d["seats"] else 0
        venue_list.append({
            "venue": v, "gross": d["gross"], 
            "tickets": d["tickets"], "shows": d["shows"], "occ": occ
        })
    
    venue_list.sort(key=lambda x: x["gross"], reverse=True)

    # --- 2. LAYOUT CALCULATIONS ---
    C_ORANGE, C_BLUE, C_GREEN = (237, 125, 49), (189, 215, 238), (169, 208, 142)
    padding, row_h, head_h = 25, 30, 45
    col_w = [350, 80, 100, 140, 80] # Venue, Shows, Tickets, Gross, Occ
    img_w = sum(col_w) + (padding * 2)
    img_h = padding + 150 + (len(venue_list) * row_h) + (head_h * 2) + padding + 20

    img = Image.new('RGB', (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = padding

    # Title
    draw.text((padding, y), movie_name, font=f_large, fill=C_ORANGE)
    y += 40
    gen_time = datetime.now().strftime("%I:%M %p")
    # ✅ Updated subtitle to include City Name
    subtitle = f"{city_name} (BMS + District) Report | {show_date} | Generated at: {gen_time}"
    draw.text((padding, y), subtitle, font=f_reg, fill=(100, 100, 100))
    y += 50

    # Header
    draw.rectangle([(padding, y), (img_w - padding, y + head_h)], fill=C_ORANGE)
    draw.text((img_w // 2, y + head_h/2), f"THEATRE WISE PERFORMANCE ({len(venue_list)} Venues)", font=f_header, fill=(255, 255, 255), anchor="mm")
    y += head_h

    # Columns
    draw.rectangle([(padding, y), (img_w - padding, y + row_h)], fill=C_BLUE)
    headers, x = ["Venue", "Shows", "Tickets", "Gross (INR)", "Occ %"], padding
    for i, h in enumerate(headers):
        align = "lm" if i==0 else "mm"
        pos = x+10 if i==0 else x+col_w[i]/2
        draw.text((pos, y + row_h/2), h, font=f_bold, fill=(0,0,0), anchor=align)
        x += col_w[i]
    y += row_h

    # Rows
    for i, v in enumerate(venue_list):
        bg = (255, 255, 255) if i % 2 == 0 else (242, 242, 242)
        draw.rectangle([(padding, y), (img_w - padding, y + row_h)], fill=bg)
        
        # Truncate long venue names to fit
        v_name_display = v['venue'][:40] + "..." if len(v['venue']) > 40 else v['venue']
        draw.text((padding+10, y + row_h/2), v_name_display, font=f_reg, fill=(0,0,0), anchor="lm")
        
        x = padding + 350
        vals = [str(v["shows"]), str(v["tickets"]), f"{v['gross']:,.0f}", f"{v['occ']}%"]
        
        draw.text((x+40, y + row_h/2), vals[0], font=f_reg, fill=(0,0,0), anchor="mm")
        draw.text((x+130, y + row_h/2), vals[1], font=f_reg, fill=(0,0,0), anchor="mm")
        draw.text((x+310, y + row_h/2), vals[2], font=f_reg, fill=(0,0,0), anchor="rm")
        draw.text((x+360, y + row_h/2), vals[3], font=f_reg, fill=(0,0,0), anchor="mm")
        y += row_h

    # Footer
    draw.rectangle([(padding, y), (img_w - padding, y + row_h)], fill=C_GREEN)
    draw.text((padding+10, y + row_h/2), "Total", font=f_bold, fill=(0,0,0), anchor="lm")
    
    t_gross = sum(v["gross"] for v in venue_list)
    t_tkts = sum(v["tickets"] for v in venue_list)
    t_shows = sum(v["shows"] for v in venue_list)
    t_seats = sum(venue_map[v["venue"]]["seats"] for v in venue_list)
    t_occ = round((t_tkts / t_seats) * 100, 1) if t_seats else 0

    x = padding + 350
    draw.text((x+40, y + row_h/2), str(t_shows), font=f_bold, fill=(0,0,0), anchor="mm")
    draw.text((x+130, y + row_h/2), str(t_tkts), font=f_bold, fill=(0,0,0), anchor="mm")
    draw.text((x+310, y + row_h/2), f"{t_gross:,.0f}", font=f_bold, fill=(0,0,0), anchor="rm")
    draw.text((x+360, y + row_h/2), f"{t_occ}%", font=f_bold, fill=(0,0,0), anchor="mm")

    img.save(output_path)
    print(f"🖼️ Hybrid City Report Saved: {output_path}")