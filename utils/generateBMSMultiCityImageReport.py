import os
from urllib.parse import urlparse
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- CONFIGURATION ---
MAX_ROWS_TO_DISPLAY = 25
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

    except Exception as e:
        print(f"⚠️ Could not parse URL metadata: {e}")
    
    return "Movie Collection Report", datetime.now().strftime("%d %b %Y")

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
        font_large = ImageFont.load_default()
        font_header = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font_reg = ImageFont.load_default()
    return font_large, font_header, font_bold, font_reg

def generate_multi_city_image_report(all_results, reference_url, output_path):
    print("🎨 Generating Multi-City Image Report...")

    # --- 1. EXTRACT METADATA FROM URL ---
    movie_name, show_date = parse_url_metadata(reference_url)

    # --- 2. AGGREGATE BY CITY ---
    city_data = {}
    
    for r in all_results:
        city = r["city"]
        city_display = city.replace("-", " ").title()
        
        if city_display not in city_data:
            city_data[city_display] = {
                "gross": 0, 
                "total_seats": 0,
                "booked_tickets": 0, 
                "shows": 0
            }
        
        city_data[city_display]["gross"] += r["booked_gross"]
        city_data[city_display]["total_seats"] += r["total_tickets"]
        city_data[city_display]["booked_tickets"] += r["booked_tickets"]
        city_data[city_display]["shows"] += 1

    full_table = []
    for city, data in city_data.items():
        if data["total_seats"] > 0:
            occ = round((data["booked_tickets"] / data["total_seats"]) * 100, 1)
        else:
            occ = 0

        full_table.append({
            "city": city,
            "gross": data["gross"],
            "tickets": data["booked_tickets"],
            "shows": data["shows"],
            "occupancy": occ
        })

    full_table.sort(key=lambda x: x["gross"], reverse=True)

    # --- 3. TOTALS & SLICING ---
    grand_total_gross = sum(r["gross"] for r in full_table)
    grand_total_tickets = sum(r["tickets"] for r in full_table)
    grand_total_shows = sum(r["shows"] for r in full_table)
    
    total_seats_global = sum(city_data[c]["total_seats"] for c in city_data)
    grand_occ = round((grand_total_tickets / total_seats_global) * 100, 1) if total_seats_global else 0

    display_rows = full_table[:MAX_ROWS_TO_DISPLAY]
    remaining_rows = full_table[MAX_ROWS_TO_DISPLAY:]

    if remaining_rows:
        display_rows.append({
            "city": f"Others ({len(remaining_rows)} cities)",
            "gross": sum(r["gross"] for r in remaining_rows),
            "tickets": sum(r["tickets"] for r in remaining_rows),
            "shows": sum(r["shows"] for r in remaining_rows),
            "occupancy": round(sum(r["occupancy"] for r in remaining_rows) / len(remaining_rows), 1)
        })

    # --- 4. LAYOUT ---
    COLOR_HEADER_BG = (237, 125, 49)    # Orange
    COLOR_SUBHEADER_BG = (189, 215, 238) # Blue
    COLOR_ROW_EVEN = (255, 255, 255)
    COLOR_ROW_ODD = (242, 242, 242)
    COLOR_FOOTER_BG = (169, 208, 142)   # Green
    COLOR_TEXT = (0, 0, 0)
    COLOR_TEXT_WHITE = (255, 255, 255)
    
    padding = 20
    row_height = 30
    header_height = 45
    
    cols = [
        {"key": "city", "title": "City Name", "width": 300, "align": "left"},
        {"key": "shows", "title": "Shows", "width": 80, "align": "center"},
        {"key": "tickets", "title": "Tickets", "width": 100, "align": "center"},
        {"key": "gross", "title": "Gross (INR)", "width": 140, "align": "right"},
        {"key": "occupancy", "title": "Occ %", "width": 80, "align": "center"},
    ]
    
    table_width = sum(c["width"] for c in cols)
    image_width = table_width + (padding * 2)
    image_height = padding + 40 + 30 + header_height + row_height + (len(display_rows) * row_height) + row_height + padding
    
    img = Image.new('RGB', (image_width, image_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font_large, font_header, font_bold, font_reg = get_fonts()

    current_y = padding

    # --- A. TITLE SECTION (DYNAMIC) ---
    draw.text((padding, current_y), movie_name, font=font_large, fill=COLOR_HEADER_BG)
    current_y += 35
    
    gen_time = datetime.now().strftime("%I:%M %p")
    subtitle = f"BMS Multi-City Collection Report  |  {show_date}  |  Generated at: {gen_time}"
    draw.text((padding, current_y), subtitle, font=font_reg, fill=(80, 80, 80))
    current_y += 35

    # --- B. HEADER ---
    draw.rectangle([(padding, current_y), (image_width - padding, current_y + header_height)], fill=COLOR_HEADER_BG)
    draw.text((image_width // 2, current_y + (header_height/2)), f"Top Performing Cities ({len(full_table)} Total)", font=font_header, fill=COLOR_TEXT_WHITE, anchor="mm")
    current_y += header_height

    # --- C. SUB-HEADER ---
    draw.rectangle([(padding, current_y), (image_width - padding, current_y + row_height)], fill=COLOR_SUBHEADER_BG)
    x_cursor = padding
    for col in cols:
        text_y = current_y + (row_height/2)
        if col["align"] == "center":
            draw.text((x_cursor + col["width"]/2, text_y), col["title"], font=font_bold, fill=COLOR_TEXT, anchor="mm")
        elif col["align"] == "right":
            draw.text((x_cursor + col["width"] - 10, text_y), col["title"], font=font_bold, fill=COLOR_TEXT, anchor="rm")
        else:
            draw.text((x_cursor + 10, text_y), col["title"], font=font_bold, fill=COLOR_TEXT, anchor="lm")
        x_cursor += col["width"]
    current_y += row_height

    # --- D. ROWS ---
    for index, row in enumerate(display_rows):
        bg_color = COLOR_ROW_EVEN if index % 2 == 0 else COLOR_ROW_ODD
        if "Others (" in row["city"]: bg_color = (230, 230, 230)

        draw.rectangle([(padding, current_y), (image_width - padding, current_y + row_height)], fill=bg_color)
        x_cursor = padding
        for col in cols:
            val = row[col["key"]]
            if col["key"] == "gross": val = f"{val:,.0f}"
            elif col["key"] == "occupancy": val = f"{val}%"
            else: val = str(val)

            text_y = current_y + (row_height/2)
            if col["align"] == "center":
                draw.text((x_cursor + col["width"]/2, text_y), val, font=font_reg, fill=COLOR_TEXT, anchor="mm")
            elif col["align"] == "right":
                draw.text((x_cursor + col["width"] - 10, text_y), val, font=font_reg, fill=COLOR_TEXT, anchor="rm")
            else:
                trunc = truncate_text(draw, val, font_reg, col["width"] - 20)
                draw.text((x_cursor + 10, text_y), trunc, font=font_reg, fill=COLOR_TEXT, anchor="lm")
            x_cursor += col["width"]
        current_y += row_height

    # --- E. FOOTER ---
    draw.rectangle([(padding, current_y), (image_width - padding, current_y + row_height)], fill=COLOR_FOOTER_BG)
    draw.text((padding + 10, current_y + (row_height/2)), "Grand Total", font=font_bold, fill=COLOR_TEXT, anchor="lm")
    
    x_cursor = padding + cols[0]["width"] 
    # Shows
    draw.text((x_cursor + cols[1]["width"]/2, current_y + (row_height/2)), str(grand_total_shows), font=font_bold, fill=COLOR_TEXT, anchor="mm")
    x_cursor += cols[1]["width"]
    # Tickets
    draw.text((x_cursor + cols[2]["width"]/2, current_y + (row_height/2)), str(grand_total_tickets), font=font_bold, fill=COLOR_TEXT, anchor="mm")
    x_cursor += cols[2]["width"]
    # Gross
    draw.text((x_cursor + cols[3]["width"] - 10, current_y + (row_height/2)), f"{grand_total_gross:,.0f}", font=font_bold, fill=COLOR_TEXT, anchor="rm")
    x_cursor += cols[3]["width"]
    # Occ
    draw.text((x_cursor + cols[4]["width"]/2, current_y + (row_height/2)), f"{grand_occ}%", font=font_bold, fill=COLOR_TEXT, anchor="mm")

    img.save(output_path)
    print(f"🖼️ Image Saved: {output_path}")