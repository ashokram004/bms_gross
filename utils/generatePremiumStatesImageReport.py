"""
Premium State Image Report Generator - High-Quality Shareable Reports
Generates beautiful professional image reports matching the HTML design
"""

import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime


# Color scheme matching the premium HTML theme
COLORS = {
    "bg": "#0a0a0f",
    "surface": "#13131c",
    "surface2": "#1c1c2a",
    "border": "#2a2a3d",
    "accent": "#f5a623",
    "accent2": "#e8174d",
    "text": "#e8e8f0",
    "muted": "#7070a0",
    "bms": "#e8174d",
    "district": "#ff6600",
    "good": "#00c853",
    "warn": "#ffd600",
    "bad": "#ff6d00"
}


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def get_fonts(draw):
    """Get best available fonts"""
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 84)
        heading_font = ImageFont.truetype("arialbd.ttf", 56)
        kpi_label = ImageFont.truetype("arialbd.ttf", 32)
        kpi_value = ImageFont.truetype("arialbd.ttf", 52)
        label_font = ImageFont.truetype("arialbd.ttf", 18)
        text_font = ImageFont.truetype("arial.ttf", 16)
        small_font = ImageFont.truetype("arial.ttf", 13)
        tiny_font = ImageFont.truetype("arial.ttf", 11)
    except:
        title_font = heading_font = kpi_label = kpi_value = label_font = text_font = small_font = tiny_font = ImageFont.load_default()
    
    return {
        "title": title_font,
        "heading": heading_font,
        "kpi_label": kpi_label,
        "kpi_value": kpi_value,
        "label": label_font,
        "text": text_font,
        "small": small_font,
        "tiny": tiny_font
    }


def format_currency(value):
    """Format large numbers"""
    if value >= 100000:
        return f"₹{value/100000:.2f}L"
    elif value >= 1000:
        return f"₹{value/1000:.1f}K"
    else:
        return f"₹{value:.0f}"


def generate_premium_states_image_report(all_results, output_path, movie_name="Movie Collection", show_date=None):
    """Generate professional image report for state-wise data"""
    
    print("🎨 Generating Premium Multi-State Image Report...")
    
    if show_date is None:
        show_date = datetime.now().strftime("%d %b %Y")
    
    # --- AGGREGATE BY STATE ---
    state_stats = {}
    state_venue_map = {}
    
    for r in all_results:
        state = r.get("state", "Unknown")
        venue = r["venue"]
        
        if state not in state_stats:
            state_stats[state] = {
                "gross": 0, "tickets": 0, "seats": 0, "shows": 0,
                "venues": set(), "source_count": {"district": 0, "bms": 0}
            }
        
        state_stats[state]["gross"] += r["booked_gross"]
        state_stats[state]["tickets"] += r["booked_tickets"]
        state_stats[state]["seats"] += r["total_tickets"]
        state_stats[state]["shows"] += 1
        state_stats[state]["venues"].add(venue)
        
        source = r.get("source", "district").lower()
        if source in state_stats[state]["source_count"]:
            state_stats[state]["source_count"][source] += 1
        
        if state not in state_venue_map:
            state_venue_map[state] = {}
        
        if venue not in state_venue_map[state]:
            state_venue_map[state][venue] = {
                "gross": 0, "tickets": 0, "shows": 0, "seats": 0
            }
        
        state_venue_map[state][venue]["gross"] += r["booked_gross"]
        state_venue_map[state][venue]["tickets"] += r["booked_tickets"]
        state_venue_map[state][venue]["shows"] += 1
        state_venue_map[state][venue]["seats"] += r["total_tickets"]
    
    # State list
    state_list = []
    for state, stats in state_stats.items():
        occ = round((stats["tickets"] / stats["seats"]) * 100, 1) if stats["seats"] else 0
        state_list.append({
            "name": state, "gross": stats["gross"], "tickets": stats["tickets"],
            "shows": stats["shows"], "venues": len(stats["venues"]), "occupancy": occ,
            "district_shows": stats["source_count"]["district"],
            "bms_shows": stats["source_count"]["bms"]
        })
    
    state_list.sort(key=lambda x: x["gross"], reverse=True)
    
    # Calculate totals
    total_gross = sum(s["gross"] for s in state_list)
    total_tickets = sum(s["tickets"] for s in state_list)
    total_occupancy = round((sum(r["booked_tickets"] for r in all_results) / sum(r["total_tickets"] for r in all_results) * 100), 1) if all_results else 0
    total_theatres = sum(s["venues"] for s in state_list)
    
    source_gross_bms = sum(r["booked_gross"] for r in all_results if r.get("source") == "bms")
    source_gross_dist = total_gross - source_gross_bms
    
    # --- CREATE IMAGE ---
    img_width = 1600
    
    # Calculate height: header + summary + platforms + 2 columns of top states + footer
    header_height = 180
    summary_height = 160
    platforms_height = 140
    table_header_height = 50
    row_height = 35
    col_rows = 10
    table_height = table_header_height + (col_rows * row_height)
    footer_height = 60
    padding = 40
    
    img_height = header_height + summary_height + platforms_height + table_height + footer_height + (padding * 2)
    
    img = Image.new('RGB', (img_width, img_height), color=hex_to_rgb(COLORS["bg"]))
    draw = ImageDraw.Draw(img)
    fonts = get_fonts(draw)
    
    y = 20
    
    # --- HEADER ---
    draw.text((40, y), "📽 MULTI-STATE BOX OFFICE", font=fonts["title"], fill=hex_to_rgb(COLORS["accent"]))
    y += 100
    draw.text((40, y), movie_name, font=fonts["heading"], fill=hex_to_rgb(COLORS["text"]))
    y += 70
    draw.text((40, y), f"🌍 Multi-State Release  •  📅 {show_date}", font=fonts["label"], fill=hex_to_rgb(COLORS["muted"]))
    
    y += 90
    
    # --- LARGE SUMMARY METRICS (4 columns) ---
    summary_y = y
    metric_width = (img_width - 80) // 4
    metric_padding = 20
    
    metrics = [
        ("TOTAL GROSS", format_currency(total_gross), COLORS["accent"]),
        ("TICKETS SOLD", f"{total_tickets:,}", COLORS["accent2"]),
        ("AVG OCCUPANCY", f"{total_occupancy}%", COLORS["good"]),
        ("STATES", str(len(state_list)), COLORS["accent"])
    ]
    
    for idx, (label, value, color) in enumerate(metrics):
        x = 40 + idx * (metric_width + metric_padding)
        draw.rectangle([x, summary_y, x + metric_width, summary_y + 140], 
                      fill=hex_to_rgb(COLORS["surface"]), outline=hex_to_rgb(color))
        draw.text((x + 15, summary_y + 15), label, font=fonts["kpi_label"], fill=hex_to_rgb(color))
        draw.text((x + 15, summary_y + 55), value, font=fonts["kpi_value"], fill=hex_to_rgb(color))
    
    y = summary_y + 160
    
    # --- PLATFORM BREAKDOWN (side by side) ---
    platform_width = (img_width - 100) // 2
    
    # BMS Card
    bms_x = 40
    draw.rectangle([bms_x, y, bms_x + platform_width, y + 120], 
                   fill=hex_to_rgb(COLORS["surface"]), outline=hex_to_rgb(COLORS["bms"]), width=3)
    draw.text((bms_x + 20, y + 15), "BookMyShow", font=fonts["kpi_label"], fill=hex_to_rgb(COLORS["bms"]))
    draw.text((bms_x + 20, y + 55), format_currency(source_gross_bms), font=fonts["kpi_value"], fill=hex_to_rgb(COLORS["bms"]))
    
    # District Card
    dist_x = bms_x + platform_width + 20
    draw.rectangle([dist_x, y, dist_x + platform_width, y + 120], 
                   fill=hex_to_rgb(COLORS["surface"]), outline=hex_to_rgb(COLORS["district"]), width=3)
    draw.text((dist_x + 20, y + 15), "District App", font=fonts["kpi_label"], fill=hex_to_rgb(COLORS["district"]))
    draw.text((dist_x + 20, y + 55), format_currency(source_gross_dist), font=fonts["kpi_value"], fill=hex_to_rgb(COLORS["district"]))
    
    y += 150
    
    # --- TWO-COLUMN TABLE LAYOUT ---
    left_x = 40
    right_x = 40 + (img_width - 80) // 2 + 10
    col_width = (img_width - 80) // 2 - 10
    
    # Table header for left column
    draw.rectangle([left_x, y, left_x + col_width, y + 50], fill=hex_to_rgb(COLORS["surface2"]))
    draw.text((left_x + 10, y + 12), "STATE (TOP 10)", font=fonts["label"], fill=hex_to_rgb(COLORS["accent"]))
    draw.text((left_x + col_width - 150, y + 12), "GROSS", font=fonts["label"], fill=hex_to_rgb(COLORS["accent"]))
    
    # Table header for right column
    draw.rectangle([right_x, y, right_x + col_width, y + 50], fill=hex_to_rgb(COLORS["surface2"]))
    draw.text((right_x + 10, y + 12), "STATE (11-20)", font=fonts["label"], fill=hex_to_rgb(COLORS["accent"]))
    draw.text((right_x + col_width - 150, y + 12), "GROSS", font=fonts["label"], fill=hex_to_rgb(COLORS["accent"]))
    
    y += 55
    
    # Render top 20 states in two columns
    top_states = state_list[:20]
    
    for idx in range(10):
        # Left column
        if idx < len(top_states):
            s = top_states[idx]
            row_y = y + (idx * row_height)
            
            if idx % 2 == 0:
                draw.rectangle([left_x, row_y, left_x + col_width, row_y + row_height], 
                             fill=hex_to_rgb(COLORS["surface"]))
            
            # State name
            draw.text((left_x + 10, row_y + 8), s["name"], font=fonts["small"], fill=hex_to_rgb(COLORS["text"]))
            
            # Theatres and occupancy (small)
            theatre_occ = f"{s['venues']} venues • {s['occupancy']}%"
            draw.text((left_x + 10, row_y + 22), theatre_occ, font=fonts["tiny"], fill=hex_to_rgb(COLORS["muted"]))
            
            # Gross (right aligned)
            gross_text = format_currency(s["gross"])
            draw.text((left_x + col_width - 140, row_y + 8), gross_text, font=fonts["small"], fill=hex_to_rgb(COLORS["accent"]))
        
        # Right column
        if idx + 10 < len(top_states):
            s = top_states[idx + 10]
            row_y = y + (idx * row_height)
            
            if idx % 2 == 0:
                draw.rectangle([right_x, row_y, right_x + col_width, row_y + row_height], 
                             fill=hex_to_rgb(COLORS["surface"]))
            
            # State name
            draw.text((right_x + 10, row_y + 8), s["name"], font=fonts["small"], fill=hex_to_rgb(COLORS["text"]))
            
            # Theatres and occupancy (small)
            theatre_occ = f"{s['venues']} venues • {s['occupancy']}%"
            draw.text((right_x + 10, row_y + 22), theatre_occ, font=fonts["tiny"], fill=hex_to_rgb(COLORS["muted"]))
            
            # Gross (right aligned)
            gross_text = format_currency(s["gross"])
            draw.text((right_x + col_width - 140, row_y + 8), gross_text, font=fonts["small"], fill=hex_to_rgb(COLORS["accent"]))
    
    y += (10 * row_height) + 40
    
    # --- FOOTER ---
    footer_text = f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')} | Data from BookMyShow & District"
    draw.text((40, y), footer_text, font=fonts["small"], fill=hex_to_rgb(COLORS["muted"]))
    
    # Ensure reports directory exists
    reports_dir = os.path.dirname(output_path)
    if reports_dir:
        os.makedirs(reports_dir, exist_ok=True)
    
    img.save(output_path, quality=95)
    print(f"✅ Premium Multi-State Image Report generated: {output_path}")
