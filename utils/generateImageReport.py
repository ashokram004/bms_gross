import os
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- CONFIGURATION ---
MAX_ROWS_TO_DISPLAY = 25
FONT_PATH_BOLD = "arialbd.ttf"
FONT_PATH_REG = "arial.ttf"

def parse_url_metadata(url, source_type="district"):
    """
    Extracts City, Movie Name, and Date. 
    Supports 'bms' and 'district' source types.
    """
    try:
        parsed_url = urlparse(url)
        path_parts = [p for p in parsed_url.path.split('/') if p]

        if source_type.lower() == "district":
            # Extract Date from query param
            query_params = parse_qs(parsed_url.query)
            raw_date = query_params.get('fromdate', [None])[0]
            show_date = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d %b %Y") if raw_date else "Today"

            # Extract Movie and City from slug
            slug = path_parts[-1] if path_parts else ""
            if "-movie-tickets-in-" in slug:
                movie_part, city_part = slug.split("-movie-tickets-in-")
                movie_name = movie_part.replace("-", " ").title()
                city_name = city_part.split("-MV")[0].replace("-", " ").title()
                return city_name, movie_name, show_date

        elif source_type.lower() == "bms":
            if "buytickets" in path_parts:
                idx = path_parts.index("buytickets")
                city = path_parts[idx - 2].replace("-", " ").title()
                movie = path_parts[idx - 1].replace("-", " ").title()
                date_raw = path_parts[-1]
                try:
                    show_date = datetime.strptime(date_raw, "%Y%m%d").strftime("%d %b %Y")
                except:
                    show_date = date_raw
                return city, movie, show_date

    except Exception as e:
        print(f"⚠️ Metadata parse error: {e}")
    
    return "District", "Movie Report", datetime.now().strftime("%d %b %Y")

def truncate_text(draw, text, font, max_width):
    if draw.textlength(text, font=font) <= max_width:
        return text
    while draw.textlength(text + "...", font=font) > max_width and len(text) > 0:
        text = text[:-1]
    return text + "..."

def get_fonts():
    try:
        font_large = ImageFont.truetype(FONT_PATH_BOLD, 26)
        font_header = ImageFont.truetype(FONT_PATH_BOLD, 18)
        font_bold = ImageFont.truetype(FONT_PATH_BOLD, 15)
        font_reg = ImageFont.truetype(FONT_PATH_REG, 15)
    except IOError:
        font_large = font_header = font_bold = font_reg = ImageFont.load_default()
    return font_large, font_header, font_bold, font_reg

def generate_city_image_report(results, source_url, output_path, source_type="district"):
    print(f"🎨 Generating {source_type.upper()} Image Report...")

    # --- 1. EXTRACT METADATA ---
    city_name, movie_name, show_date = parse_url_metadata(source_url, source_type)

    # --- 2. DATA AGGREGATION ---
    theater_data = {}
    for r in results:
        venue = r["venue"]
        if venue not in theater_data:
            theater_data[venue] = {"gross": 0, "tickets": 0, "shows": 0, "occupancy_sum": 0}
        
        theater_data[venue]["gross"] += r["booked_gross"]
        theater_data[venue]["tickets"] += r["booked_tickets"]
        theater_data[venue]["shows"] += 1
        theater_data[venue]["occupancy_sum"] += r["occupancy"]

    full_table = []
    for venue, data in theater_data.items():
        avg_occ = round(data["occupancy_sum"] / data["shows"], 1) if data["shows"] > 0 else 0
        full_table.append({
            "venue": venue, "gross": data["gross"], "tickets": data["tickets"],
            "shows": data["shows"], "occupancy": avg_occ
        })

    full_table.sort(key=lambda x: x["gross"], reverse=True)

    # --- 3. TOTALS & SLICING ---
    grand_total_gross = sum(r["gross"] for r in full_table)
    grand_total_tickets = sum(r["tickets"] for r in full_table)
    grand_total_shows = sum(r["shows"] for r in full_table)
    grand_avg_occ = round(sum(r["occupancy"] for r in full_table) / len(full_table), 1) if full_table else 0

    display_rows = full_table[:MAX_ROWS_TO_DISPLAY]
    remaining = full_table[MAX_ROWS_TO_DISPLAY:]

    if remaining:
        display_rows.append({
            "venue": f"Others ({len(remaining)} theaters)",
            "gross": sum(r["gross"] for r in remaining),
            "tickets": sum(r["tickets"] for r in remaining),
            "shows": sum(r["shows"] for r in remaining),
            "occupancy": round(sum(r["occupancy"] for r in remaining) / len(remaining), 1)
        })

    # --- 4. LAYOUT & DRAWING ---
    COLOR_HEADER_BG = (237, 125, 49)
    COLOR_SUBHEADER_BG = (189, 215, 238)
    COLOR_FOOTER_BG = (169, 208, 142)
    COLOR_TEXT = (0, 0, 0)
    
    padding, row_h, head_h = 20, 30, 45
    cols = [
        {"key": "venue", "title": "Theater Name", "width": 380, "align": "left"},
        {"key": "shows", "title": "Shows", "width": 70, "align": "center"},
        {"key": "tickets", "title": "Tickets", "width": 90, "align": "center"},
        {"key": "gross", "title": "Gross (INR)", "width": 120, "align": "right"},
        {"key": "occupancy", "title": "Occ %", "width": 70, "align": "center"},
    ]
    
    img_w = sum(c["width"] for c in cols) + (padding * 2)
    img_h = padding + 140 + (len(display_rows) * row_h) + row_h + padding
    
    img = Image.new('RGB', (img_w, img_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    f_large, f_head, f_bold, f_reg = get_fonts()

    curr_y = padding
    draw.text((padding, curr_y), movie_name, font=f_large, fill=COLOR_HEADER_BG)
    curr_y += 35
    draw.text((padding, curr_y), f"{city_name} | {show_date} | Generated at: {datetime.now().strftime('%I:%M %p')} | Source: {source_type.capitalize()}", font=f_reg, fill=(80,80,80))
    curr_y += 35

    # Header & Subheader Drawing
    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+head_h)], fill=COLOR_HEADER_BG)
    draw.text((img_w//2, curr_y+(head_h/2)), "Top Performing Theaters", font=f_head, fill=(255,255,255), anchor="mm")
    curr_y += head_h

    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=COLOR_SUBHEADER_BG)
    x = padding
    for c in cols:
        anchor = "mm" if c["align"]=="center" else ("rm" if c["align"]=="right" else "lm")
        draw.text((x + (c["width"]/2 if anchor=="mm" else (c["width"]-10 if anchor=="rm" else 10)), curr_y+row_h/2), c["title"], font=f_bold, fill=COLOR_TEXT, anchor=anchor)
        x += c["width"]
    curr_y += row_h

    # Rows
    for i, row in enumerate(display_rows):
        bg = (255,255,255) if i%2==0 else (242,242,242)
        draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=bg)
        x = padding
        for c in cols:
            val = f"{row[c['key']]:,.0f}" if c['key']=="gross" else (f"{row[c['key']]}%" if c['key']=="occupancy" else str(row[c['key']]))
            anchor = "mm" if c["align"]=="center" else ("rm" if c["align"]=="right" else "lm")
            txt = truncate_text(draw, val, f_reg, c["width"]-20) if c['key']=="venue" else val
            draw.text((x + (c["width"]/2 if anchor=="mm" else (c["width"]-10 if anchor=="rm" else 10)), curr_y+row_h/2), txt, font=f_reg, fill=COLOR_TEXT, anchor=anchor)
            x += c["width"]
        curr_y += row_h

    # Footer
    draw.rectangle([(padding, curr_y), (img_w-padding, curr_y+row_h)], fill=COLOR_FOOTER_BG)
    draw.text((padding+10, curr_y+row_h/2), "Grand Total", font=f_bold, fill=COLOR_TEXT, anchor="lm")
    x = padding + cols[0]["width"]
    draw.text((x + cols[1]["width"]/2, curr_y+row_h/2), str(grand_total_shows), font=f_bold, fill=COLOR_TEXT, anchor="mm")
    x += cols[1]["width"]
    draw.text((x + cols[2]["width"]/2, curr_y+row_h/2), str(grand_total_tickets), font=f_bold, fill=COLOR_TEXT, anchor="mm")
    x += cols[2]["width"]
    draw.text((x + cols[3]["width"]-10, curr_y+row_h/2), f"{grand_total_gross:,.0f}", font=f_bold, fill=COLOR_TEXT, anchor="rm")
    x += cols[3]["width"]
    draw.text((x + cols[4]["width"]/2, curr_y+row_h/2), f"{grand_avg_occ}%", font=f_bold, fill=COLOR_TEXT, anchor="mm")

    img.save(output_path)
    print(f"🖼️ Image Saved: {output_path}")