"""
Premium Box Office Image Generator - Deep Space Glassmorphism UI 
Tailored for BMS vs District Data
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from datetime import datetime
import os
import platform

# ── CANVAS ───────────────────────────────────────────────────────────────────
W   = 2560      
PAD = 80        

WATERMARK_ENABLED = False
WATERMARK_TEXT    = "WkndCinema"
WATERMARK_OPACITY = 90
WATERMARK_ANGLE   = 35

# ── GLASSMORPHISM TEXT PALETTE ───────────────────────────────────────────────
TEXT_BRIGHT = (255, 255, 255)   
TEXT        = (232, 232, 240)   
MUTED       = (160, 160, 180)   
GREEN       = (74,  222, 128)  
ORANGE      = (251, 146,  60)  
RED         = (248, 113, 113)  
ACCENT      = (245, 166,  35)  
BMS_C       = (232,  23,  77)  
DST_C       = (152,  68, 222)

# ── HELPERS ──────────────────────────────────────────────────────────────────

def format_currency_inr(value):
    """Formats currency into Indian numbering system (Crores, Lakhs)"""
    if value >= 10000000: return f"₹{value/10000000:.2f} Cr"
    elif value >= 100000: return f"₹{value/100000:.2f} L"
    elif value >= 1000: return f"₹{value/1000:.2f} K"
    else: return f"₹{value:.0f}"

def get_font(size, bold=False):
    """Attempts to load a robust font for ₹ support, falls back gracefully."""
    fonts_to_try = [
        r"C:\Windows\Fonts\NotoSans-Bold.ttf" if bold else r"C:\Windows\Fonts\NotoSans-Regular.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "Helvetica-Bold.ttf" if bold else "Helvetica.ttf"
    ]
    for font_name in fonts_to_try:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()

def draw_glass_panel(bg_img, draw, xy, radius=16):
    """Draws a translucent glassmorphic panel over the background."""
    x1, y1, x2, y2 = xy
    
    # Extract background, blur, and brighten
    region = bg_img.crop((int(x1), int(y1), int(x2), int(y2)))
    blurred_region = region.filter(ImageFilter.GaussianBlur(30))
    enhancer = ImageEnhance.Brightness(blurred_region)
    blurred_region = enhancer.enhance(1.2)
    
    # Create mask for rounded corners
    mask = Image.new('L', blurred_region.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, x2-x1, y2-y1), radius=radius, fill=255)
    
    # Paste blurred glass onto main image
    bg_img.paste(blurred_region, (int(x1), int(y1)), mask)
    
    # Overlay tints and highlights
    overlay = Image.new('RGBA', bg_img.size, (0,0,0,0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(xy, radius=radius, fill=(255, 255, 255, 12))
    overlay_draw.polygon([(x1, y1+radius), (x1+radius, y1), (x2-(x2-x1)//3, y1), (x1, y2-(y2-y1)//3)], fill=(255, 255, 255, 8))
    overlay_draw.rounded_rectangle(xy, radius=radius, outline=(255, 255, 255, 45), width=2)
    bg_img.paste(overlay, (0,0), overlay)

def aggregate_data(data):
    """Aggregates raw show data into State, City, and Theatre dictionaries."""
    state_stats, city_stats, theatre_stats = {}, {}, {}
    
    for r in data:
        st = r.get("state", "Unknown")
        ct = r.get("city", "Unknown")
        th = r.get("venue", "Unknown")
        g = r.get("booked_gross", 0)
        t = r.get("booked_tickets", 0)
        s = r.get("total_tickets", 0)
        
        # State
        if st not in state_stats: state_stats[st] = {'name': st, 'shows': 0, 'tickets': 0, 'booked': 0, 'gross': 0, 'venues': set()}
        state_stats[st]['shows'] += 1
        state_stats[st]['tickets'] += s
        state_stats[st]['booked'] += t
        state_stats[st]['gross'] += g
        state_stats[st]['venues'].add(th)

        # City
        if ct not in city_stats: city_stats[ct] = {'name': ct, 'shows': 0, 'tickets': 0, 'booked': 0, 'gross': 0, 'venues': set()}
        city_stats[ct]['shows'] += 1
        city_stats[ct]['tickets'] += s
        city_stats[ct]['booked'] += t
        city_stats[ct]['gross'] += g
        city_stats[ct]['venues'].add(th)

        # Theatre
        if th not in theatre_stats: theatre_stats[th] = {'name': th, 'shows': 0, 'tickets': 0, 'booked': 0, 'gross': 0}
        theatre_stats[th]['shows'] += 1
        theatre_stats[th]['tickets'] += s
        theatre_stats[th]['booked'] += t
        theatre_stats[th]['gross'] += g
        
    def finalize(d):
        out = []
        for k, v in d.items():
            row = v.copy()
            if 'venues' in row: row['venues'] = len(row['venues'])
            row['occ'] = (row['booked'] / row['tickets'] * 100) if row['tickets'] > 0 else 0
            out.append(row)
        return sorted(out, key=lambda x: x['gross'], reverse=True)

    return finalize(state_stats), finalize(city_stats), finalize(theatre_stats)


# ── MAIN GENERATOR ───────────────────────────────────────────────────────────

def generate_premium_states_image_report(data, filename, movie_name="Movie Collection", show_date="N/A", last_updated_str="N/A", country_name="India"):
    
    if not data:
        print("No data available for image generation.")
        return None

    # 1. PREPARE DATA
    total_venues = len(set(r['venue'] for r in data))
    total_shows = len(data)
    total_tickets = sum(r['total_tickets'] for r in data)
    total_booked = sum(r['booked_tickets'] for r in data)
    total_gross = sum(r['booked_gross'] for r in data)
    overall_occ = (total_booked / total_tickets * 100) if total_tickets > 0 else 0

    # Platform Data
    bms_data = [r for r in data if r.get('source') == 'bms']
    dst_data = [r for r in data if r.get('source') == 'district']
    
    bms_gross = sum(r['booked_gross'] for r in bms_data)
    bms_booked = sum(r['booked_tickets'] for r in bms_data)
    dst_gross = sum(r['booked_gross'] for r in dst_data)
    dst_booked = sum(r['booked_tickets'] for r in dst_data)

    states_list, cities_list, theatres_list = aggregate_data(data)

    # 2. DYNAMIC HEIGHT CALCULATION
    header_h = 160
    kpi_h = 200 
    platform_h = 240
    
    # 10 rows max + 1 remaining
    st_rows = min(11, len(states_list) + (1 if len(states_list) > 10 else 0))
    st_h = 220 + (st_rows * 60) 
    
    max_bot_rows = max(len(cities_list[:10]), len(theatres_list[:10]))
    bot_rows = max_bot_rows + (1 if len(cities_list) > 10 or len(theatres_list) > 10 else 0)
    bot_h = 220 + (bot_rows * 60)
    
    footer_h = 80
    
    H = PAD + header_h + kpi_h + 40 + platform_h + 40 + st_h + 40 + bot_h + 40 + footer_h + PAD

    # 3. BACKGROUND SETUP (Muted Obsidian Slate)
    base_bg = Image.new('RGB', (4, 4))
    base_bg.putpixel((0,0), (8, 10, 15))   
    base_bg.putpixel((3,0), (12, 14, 20))  
    base_bg.putpixel((0,3), (10, 12, 18))  
    base_bg.putpixel((3,3), (15, 18, 24))  
    img = base_bg.resize((W, int(H)), Image.Resampling.BICUBIC)
    
    orb_layer = Image.new('RGBA', (W, int(H)), (0,0,0,0))
    orb_draw = ImageDraw.Draw(orb_layer)
    orb_draw.ellipse([-600, -600, 1200, 1200], fill=(51, 65, 85, 100)) 
    orb_draw.ellipse([W-1400, int(H)//2 - 800, W+600, int(H)//2 + 800], fill=(30, 41, 59, 120)) 
    orb_draw.ellipse([W//2 - 1000, int(H)-1000, W//2 + 1000, int(H)+1000], fill=(245, 131, 32, 12)) 
    
    orb_layer = orb_layer.filter(ImageFilter.GaussianBlur(250))
    img.paste(orb_layer, (0,0), orb_layer)

    draw = ImageDraw.Draw(img)

    # Fonts
    f_title = get_font(64, bold=True)
    f_sub = get_font(28)
    f_kpi_val = get_font(72, bold=True)
    f_kpi_lbl = get_font(22, bold=True)
    f_kpi_sub = get_font(26, bold=True)
    
    f_sec = get_font(36, bold=True)   
    f_th = get_font(24, bold=True)    
    f_row = get_font(28, bold=True)   
    f_row_b = get_font(28, bold=True) 
    
    f_plat_lbl = get_font(32, bold=True)
    f_plat_val = get_font(85, bold=True)

    if WATERMARK_ENABLED:
        try:
            wm_font = get_font(180, bold=True)
            wm_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            wm_draw = ImageDraw.Draw(wm_layer)
            tw, th = wm_draw.textbbox((0,0), WATERMARK_TEXT, font=wm_font)[2:]
            wm_x, wm_y = (W-tw)//2, (H-th)//2
            wm_draw.text((wm_x, wm_y), WATERMARK_TEXT, font=wm_font, fill=(255, 255, 255, WATERMARK_OPACITY))
            wm_layer = wm_layer.rotate(WATERMARK_ANGLE, expand=False, center=(W//2, H//2))
            img.paste(wm_layer, (0,0), wm_layer)
        except: pass

    # --- HEADER ---
    draw.text((PAD, PAD), movie_name, font=f_title, fill=TEXT_BRIGHT)
    sub_text = f"{country_name} Advance Sales • Show Date: {show_date}"
    draw.text((PAD, PAD+85), sub_text, font=f_sub, fill=ACCENT)

    meta_x = W - PAD
    draw.text((meta_x, PAD+20), f"Report: {datetime.now().strftime('%d %b %Y, %I:%M %p')} IST", font=f_sub, fill=TEXT, anchor="ra")
    
    ov_line = Image.new('RGBA', img.size, (0,0,0,0))
    ImageDraw.Draw(ov_line).line([(PAD, PAD+150), (W-PAD, PAD+150)], fill=(255,255,255,40), width=3)
    img.paste(ov_line, (0,0), ov_line)

    # --- KPIs ---
    kpi_y = PAD + 180
    kpi_width = (W - (2*PAD) - (4*30)) // 5 
    
    def draw_kpi(idx, label, val, sub_val, highlight_col=(245, 131, 32, 200)):
        x = PAD + (idx * (kpi_width + 30))
        draw_glass_panel(img, draw, [x, kpi_y, x+kpi_width, kpi_y+180], radius=24)
        
        ov_strip = Image.new('RGBA', img.size, (0,0,0,0))
        ImageDraw.Draw(ov_strip).rounded_rectangle([x, kpi_y, x+8, kpi_y+180], radius=6, fill=highlight_col)
        img.paste(ov_strip, (0,0), ov_strip)
        
        draw.text((x+40, kpi_y+35), label.upper(), font=f_kpi_lbl, fill=MUTED)
        right_margin_x = x + kpi_width - 30
        draw.text((right_margin_x, kpi_y+39), str(sub_val), font=f_kpi_sub, fill=MUTED, anchor="rt")
        draw.text((x+40, kpi_y+75), val, font=f_kpi_val, fill=TEXT_BRIGHT)

    draw_kpi(0, "Total Gross", format_currency_inr(total_gross), "", highlight_col=(245, 131, 32, 200))
    draw_kpi(1, "Tickets Sold", f"{total_booked:,}", f"{total_tickets:,} cap")
    draw_kpi(2, "Total Venues", f"{total_venues:,}", "")
    draw_kpi(3, "Total Shows", f"{total_shows:,}", "")
    draw_kpi(4, "Occupancy", f"{overall_occ:.1f}%", f"{total_tickets:,} seats")

    # --- PLATFORM CARDS ---
    plat_y = kpi_y + 220
    plat_w = (W - (2*PAD) - 40) // 2
    
    def draw_platform_card(x, title, gross, booked, shows, bar_color):
        draw_glass_panel(img, draw, [x, plat_y, x+plat_w, plat_y+platform_h], radius=24)
        
        ov_strip = Image.new('RGBA', img.size, (0,0,0,0))
        ImageDraw.Draw(ov_strip).rounded_rectangle([x, plat_y, x+plat_w, plat_y+8], radius=8, fill=bar_color)
        img.paste(ov_strip, (0,0), ov_strip)
        
        draw.text((x+40, plat_y+40), title, font=f_plat_lbl, fill=MUTED)
        draw.text((x+40, plat_y+90), format_currency_inr(gross), font=f_plat_val, fill=bar_color)
        
        # Bottom stats
        pct = (gross / total_gross * 100) if total_gross else 0
        draw.text((x+40, plat_y+190), f"Tickets: {booked:,}   |   Shows: {shows:,}   |   Share: {pct:.1f}%", font=f_sub, fill=TEXT_BRIGHT)

    draw_platform_card(PAD, "DISTRICT APP", dst_gross, dst_booked, len(dst_data), (152, 68, 222, 255))
    draw_platform_card(PAD + plat_w + 40, "BOOKMYSHOW (Deduped)", bms_gross, bms_booked, len(bms_data), (232, 23, 77, 255))


    # --- SHARED TABLE DRAW FUNCTION ---
    def draw_table(x, y, w, h, title, cols, data_rows, highlight_name=False):
        draw_glass_panel(img, draw, [x, y, x+w, y+h], radius=24)
        draw.text((x+35, y+35), title, font=f_sec, fill=TEXT_BRIGHT)
        
        th_y = y + 90
        
        overlay = Image.new('RGBA', img.size, (0,0,0,0))
        ov_draw = ImageDraw.Draw(overlay)
        ov_draw.rectangle([x, th_y, x+w, th_y+55], fill=(0, 0, 0, 80))
        ov_draw.line([(x, th_y), (x+w, th_y)], fill=(255,255,255,30), width=1)
        ov_draw.line([(x, th_y+55), (x+w, th_y+55)], fill=(255,255,255,30), width=1)
        img.paste(overlay, (0,0), overlay)

        for c in cols:
            anchor = "la" if c['align'] == 'left' else "ra"
            cx = x + c['pos'] if c['align'] == 'left' else x + w - c['pos']
            draw.text((cx, th_y+15), c['name'].upper(), font=f_th, fill=MUTED, anchor=anchor)

        cy = th_y + 80
        for row in data_rows:
            for c in cols:
                anchor = "la" if c['align'] == 'left' else "ra"
                cx = x + c['pos'] if c['align'] == 'left' else x + w - c['pos']
                
                val = str(row[c['key']])
                color = TEXT
                font_to_use = f_row
                
                if c['key'] == 'name':
                    color = ACCENT if highlight_name else TEXT_BRIGHT
                    font_to_use = f_row_b
                elif c['key'] == 'gross':
                    font_to_use = f_row_b
                    color = TEXT_BRIGHT
                elif c['key'] == 'occ':
                    color = TEXT_BRIGHT
                elif 'Remaining' in str(row.get('name','')):
                    color = MUTED
                    
                draw.text((cx, cy), val, font=font_to_use, fill=color, anchor=anchor)
                
            ov_line = Image.new('RGBA', img.size, (0,0,0,0))
            ImageDraw.Draw(ov_line).line([(x+40, cy+45), (x+w-40, cy+45)], fill=(255,255,255,15), width=1)
            img.paste(ov_line, (0,0), ov_line)
            
            cy += 60

    # Table Row Builders
    def build_rows(raw_list, is_theatre=False, is_state=False):
        out = []
        top_10 = raw_list[:10]
        
        for r in top_10:
            name = str(r['name'])
            if not is_state and len(name) > 30: name = name[:27] + "..."
            
            row_dict = {
                'name': name,
                'shows': f"{r['shows']:,}",
                'booked': f"{r['booked']:,}",
                'gross': format_currency_inr(r['gross']),
                'occ': f"{r['occ']:.1f}%"
            }
            if is_state or not is_theatre:
                row_dict['venues'] = f"{r['venues']:,}"
                
            out.append(row_dict)
            
        if len(raw_list) > 10:
            rem = raw_list[10:]
            r_shows = sum(x['shows'] for x in rem)
            r_tix = sum(x['tickets'] for x in rem)
            r_booked = sum(x['booked'] for x in rem)
            r_gross = sum(x['gross'] for x in rem)
            r_occ = (r_booked / r_tix * 100) if r_tix > 0 else 0
            
            lbl = f"Remaining {len(rem)} Venues" if is_theatre else f"Remaining {len(rem)} Areas"
            row_dict = {
                'name': lbl,
                'shows': f"{r_shows:,}",
                'booked': f"{r_booked:,}",
                'gross': format_currency_inr(r_gross),
                'occ': f"{r_occ:.1f}%"
            }
            if is_state or not is_theatre:
                r_venues = sum(x.get('venues', 0) for x in rem)
                row_dict['venues'] = f"{r_venues:,}"
            out.append(row_dict)
            
        return out


    # --- ROW 3: STATE TABLE (FULL WIDTH) ---
    st_y = plat_y + platform_h + 40
    st_w = W - (2 * PAD)
    
    st_cols = [
        {'name': 'State', 'key': 'name', 'pos': 40, 'align': 'left'},
        {'name': 'Gross', 'key': 'gross', 'pos': 40, 'align': 'right'},
        {'name': 'Occ %', 'key': 'occ', 'pos': 300, 'align': 'right'},
        {'name': 'Booked', 'key': 'booked', 'pos': 550, 'align': 'right'},
        {'name': 'Shows', 'key': 'shows', 'pos': 800, 'align': 'right'},
        {'name': 'Venues', 'key': 'venues', 'pos': 1050, 'align': 'right'},
    ]
    
    draw_table(PAD, st_y, st_w, st_h, "State Rankings", st_cols, build_rows(states_list, is_state=True))

    # --- ROW 4: CITY & THEATRE TABLES (HALF WIDTH) ---
    bot_y = st_y + st_h + 40
    bot_w = (W - (2*PAD) - 40) // 2
    
    city_cols = [
        {'name': 'City', 'key': 'name', 'pos': 35, 'align': 'left'},
        {'name': 'Gross', 'key': 'gross', 'pos': 35, 'align': 'right'},
        {'name': 'Occ %', 'key': 'occ', 'pos': 220, 'align': 'right'},
        {'name': 'Booked', 'key': 'booked', 'pos': 380, 'align': 'right'},
        {'name': 'Shows', 'key': 'shows', 'pos': 550, 'align': 'right'},
        {'name': 'Vens', 'key': 'venues', 'pos': 700, 'align': 'right'},
    ]
    
    th_cols = [
        {'name': 'Theatre', 'key': 'name', 'pos': 35, 'align': 'left'},
        {'name': 'Gross', 'key': 'gross', 'pos': 35, 'align': 'right'},
        {'name': 'Occ %', 'key': 'occ', 'pos': 240, 'align': 'right'},
        {'name': 'Booked', 'key': 'booked', 'pos': 420, 'align': 'right'},
        {'name': 'Shows', 'key': 'shows', 'pos': 600, 'align': 'right'},
    ]

    draw_table(PAD, bot_y, bot_w, bot_h, "Top Cities", city_cols, build_rows(cities_list))
    draw_table(PAD + bot_w + 40, bot_y, bot_w, bot_h, "Top Theatres", th_cols, build_rows(theatres_list, is_theatre=True))

    # --- FOOTER ---
    footer_y = bot_y + bot_h + 40
    
    ov_line2 = Image.new('RGBA', img.size, (0,0,0,0))
    ImageDraw.Draw(ov_line2).line([(PAD, footer_y), (W-PAD, footer_y)], fill=(255,255,255,40), width=2)
    img.paste(ov_line2, (0,0), ov_line2)
    
    footer_text = f"WkndCinema • Data from BookMyShow & District • Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
    tw_foot, th_foot = draw.textbbox((0,0), footer_text, font=f_sub)[2:]
    draw.text(((W-tw_foot)//2, footer_y+30), footer_text, font=f_sub, fill=MUTED)

    # Save
    try:
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
        img.save(filename, quality=95)
        print(f"📸 Visual report saved to {filename}")
        return filename
    except Exception as e:
        print(f"Error saving image: {e}")
        return None