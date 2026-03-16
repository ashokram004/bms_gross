"""
Mobile Image Report Generator - Premium Dark UI
Generates a PNG image matching the HTML reporter's design.
Mobile-optimized: 1080px wide (portrait)
"""

from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os
import math


# ── CONFIG ──────────────────────────────────────────────────────────────────
W = 1080          # Mobile width (standard 1080p portrait)
PADDING = 48
TOP_ROWS = 10     # Max rows for state/city tables

# ── WATERMARK ────────────────────────────────────────────────────────────────
WATERMARK_ENABLED = True           # Set False to disable watermark entirely
WATERMARK_TEXT    = "CINEPULSEBO"  # Text to repeat across the image
WATERMARK_OPACITY = 80            # 0–255 (lower = more transparent)
WATERMARK_ANGLE   = 35             # Diagonal angle in degrees

# Colours (match CSS vars)
BG       = (10,  10,  15)
SURFACE  = (19,  19,  28)
SURFACE2 = (28,  28,  42)
BORDER   = (42,  42,  61)
ACCENT   = (245, 166,  35)   # gold
ACCENT2  = (232,  23,  77)   # red
TEXT     = (232, 232, 240)
MUTED    = (112, 112, 160)
BMS_C    = (232,  23,  77)
DST_C    = (155,  75, 225)
WHITE    = (255, 255, 255)

GREEN    = (0,   200,  83)
ORANGE   = (255, 109,   0)
YELLOW   = (255, 214,   0)
RED      = (255,  23,  68)

# ── FONT HELPERS ─────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    """Try to load a system font, fall back to default."""
    candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    candidates_reg = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    candidates = candidates_bold if bold else candidates_reg
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# Pre-load font sizes
F_TINY   = load_font(18)
F_SMALL  = load_font(20)
F_BODY   = load_font(22)
F_BODY_B = load_font(22, bold=True)
F_MED    = load_font(32, bold=True)
F_LG     = load_font(44, bold=True)
F_XL     = load_font(64, bold=True)
F_HERO   = load_font(76, bold=True)
F_LABEL  = load_font(17)


# ── UTILITIES ────────────────────────────────────────────────────────────────
def format_currency(value):
    if value >= 10_000_000:
        return f"₹{value/10_000_000:.2f} Cr"
    elif value >= 100_000:
        return f"₹{value/100_000:.2f} L"
    elif value >= 1_000:
        return f"₹{value/1_000:.1f} K"
    return f"₹{value:.0f}"


def occ_color(occ):
    if occ >= 60:   return GREEN
    elif occ >= 50: return ORANGE
    elif occ >= 30: return YELLOW
    return RED


def text_w(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def text_h(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]


def draw_rounded_rect(draw, x1, y1, x2, y2, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill, outline=outline, width=width)


def draw_text_center(draw, cx, y, text, font, color):
    w = text_w(draw, text, font)
    draw.text((cx - w // 2, y), text, font=font, fill=color)


# ── SECTION HELPERS ──────────────────────────────────────────────────────────
def draw_section_header(draw, y, title, subtitle=""):
    draw.text((PADDING, y), title.upper(), font=F_MED, fill=TEXT)
    if subtitle:
        sub_x = PADDING + text_w(draw, title.upper(), F_MED) + 20
        draw.text((sub_x, y + 8), subtitle.upper(), font=F_LABEL, fill=MUTED)
    # divider line
    draw.line([(PADDING, y + 52), (W - PADDING, y + 52)], fill=BORDER, width=2)
    return y + 70


# ── AGGREGATE ────────────────────────────────────────────────────────────────
def aggregate(all_results):
    state_stats = {}
    city_stats  = {}

    for r in all_results:
        state  = r.get("state", "Unknown")
        city   = r.get("city",  "Unknown")
        venue  = r["venue"]
        gross  = r["booked_gross"]
        tickets= r["booked_tickets"]
        seats  = r["total_tickets"]
        source = r.get("source", "district").lower()

        # State
        if state not in state_stats:
            state_stats[state] = {"gross":0,"tickets":0,"seats":0,"shows":0,"venues":set()}
        s = state_stats[state]
        s["gross"] += gross; s["tickets"] += tickets
        s["seats"] += seats; s["shows"]   += 1; s["venues"].add(venue)

        # City
        ck = (state, city)
        if ck not in city_stats:
            city_stats[ck] = {"city":city,"state":state,"gross":0,"tickets":0,"seats":0,"shows":0,"venues":set()}
        c = city_stats[ck]
        c["gross"] += gross; c["tickets"] += tickets
        c["seats"] += seats; c["shows"]   += 1; c["venues"].add(venue)

    def build_list(d, key="gross"):
        out = []
        for k, v in d.items():
            occ = round((v["tickets"]/v["seats"])*100, 1) if v["seats"] else 0
            row = dict(v)
            row["occupancy"] = occ
            row["venues"]    = len(v["venues"])
            out.append(row)
        out.sort(key=lambda x: x["gross"], reverse=True)
        return out

    return build_list(state_stats), build_list(city_stats)


# ── WATERMARK HELPER ─────────────────────────────────────────────────────────
def _apply_watermark(img):
    """Stamp a diagonal tiled watermark across the image using RGBA compositing."""
    wm_font = load_font(72, bold=True)

    tmp_img  = Image.new("RGBA", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp_img)
    bb  = tmp_draw.textbbox((0, 0), WATERMARK_TEXT, font=wm_font)
    tw_ = bb[2] - bb[0]
    th_ = bb[3] - bb[1]

    tile_w = tw_ + 120
    tile_h = th_ + 100
    tile   = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    td     = ImageDraw.Draw(tile)
    td.text(((tile_w - tw_) // 2, (tile_h - th_) // 2), WATERMARK_TEXT,
            font=wm_font, fill=(255, 255, 255, WATERMARK_OPACITY))

    rotated = tile.rotate(WATERMARK_ANGLE, expand=True)
    rw, rh  = rotated.size

    W_, H_  = img.size
    overlay = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    for y_ in range(-rh, H_ + rh, rh):
        for x_ in range(-rw, W_ + rw, rw):
            overlay.paste(rotated, (x_, y_), rotated)

    base = img.convert("RGBA")
    out  = Image.alpha_composite(base, overlay)
    return out.convert("RGB")


# ── MAIN GENERATOR ───────────────────────────────────────────────────────────
def generate_premium_states_image_report(all_results, output_path,
                          movie_name="Movie Collection", show_date=None):
    if show_date is None:
        show_date = datetime.now().strftime("%d %b %Y")

    state_list, city_list = aggregate(all_results)

    # ── Pre-compute totals ────────────────────────────────────────────────────
    total_gross   = sum(r["booked_gross"]   for r in all_results)
    total_tickets = sum(r["booked_tickets"] for r in all_results)
    total_seats   = sum(r["total_tickets"]  for r in all_results)
    total_occ     = round((total_tickets / total_seats) * 100, 1) if total_seats else 0
    num_states    = len(state_list)
    num_venues    = len(set(r["venue"] for r in all_results))
    num_shows     = len(all_results)

    src_gross_bms   = sum(r["booked_gross"]   for r in all_results if r.get("source")=="bms")
    src_gross_dist  = sum(r["booked_gross"]   for r in all_results if r.get("source")=="district")
    src_tickets_bms = sum(r["booked_tickets"] for r in all_results if r.get("source")=="bms")
    src_tickets_dist= sum(r["booked_tickets"] for r in all_results if r.get("source")=="district")
    src_shows_bms   = sum(1 for r in all_results if r.get("source")=="bms")
    src_shows_dist  = sum(1 for r in all_results if r.get("source")=="district")

    # ── Height estimation (draw on temp canvas first, then real) ─────────────
    # We'll just compute height and draw in one pass on a tall canvas, then crop.

    def render(canvas_h, final=False):
        img  = Image.new("RGB", (W, canvas_h), BG)
        draw = ImageDraw.Draw(img)
        y    = 0

        # ── HERO ─────────────────────────────────────────────────────────────
        hero_h_max = 260
        # gradient-like bg (draw over max height, will be cropped)
        for gy in range(hero_h_max):
            t = gy / hero_h_max
            r_c = int(10  + t * 8)
            g_c = int(10  + t * 2)
            b_c = int(15  + t * 18)
            draw.line([(0, gy), (W, gy)], fill=(r_c, g_c, b_c))

        # Glow blobs (subtle)
        for gx, gy_off, col, size in [(W-100, 60, ACCENT, 200), (200, 220, ACCENT2, 160)]:
            for rad in range(size, 0, -4):
                alpha = int(12 * (rad / size))
                blob_col = tuple(min(255, c + alpha) for c in col)
                # too complex for actual radial—skip, just draw a faint ellipse
                pass

        # eyebrow
        draw.text((PADDING, y + 20), "STATE-WISE BOX OFFICE REPORT", font=F_LABEL, fill=ACCENT)

        # title — wrap at word boundaries at fixed font size
        title_y = y + 44
        title_text = movie_name.upper()
        title_font = load_font(76, bold=True)
        max_title_w = W - PADDING * 2

        # word-wrap: split into lines that fit within max_title_w
        words = title_text.split()
        lines = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if text_w(draw, test, title_font) <= max_title_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        # measure line height from actual render
        line_bb = draw.textbbox((0, 0), "Ag", font=title_font)
        line_h = line_bb[3] - line_bb[1]
        line_gap = 8

        # draw each line with shadow
        ty = title_y
        for line in lines:
            draw.text((PADDING + 2, ty + 2), line, font=title_font, fill=(20, 20, 30))
            draw.text((PADDING, ty), line, font=title_font, fill=TEXT)
            ty += line_h + line_gap
        title_px_h = ty - title_y - line_gap  # total height of all lines

        # meta pills — plain text only, no symbols
        pill_h = 36
        meta_y = title_y + title_px_h + 22
        meta_items = [
            show_date,
            f"{num_states} States",
            f"{num_venues} Theatres",
            f"{num_shows} Shows",
        ]
        mx = PADDING
        for label in meta_items:
            pill_w = text_w(draw, label, F_SMALL) + 24
            draw_rounded_rect(draw, mx, meta_y, mx + pill_w, meta_y + pill_h, 8, fill=SURFACE2)
            draw.text((mx + 12, meta_y + 8), label, font=F_SMALL, fill=MUTED)
            mx += pill_w + 10

        # hero height fits content tightly + 36px bottom padding
        hero_h = meta_y + pill_h + 36
        y += hero_h

        # ── KPI STRIP ────────────────────────────────────────────────────────
        kpis = [
            ("TOTAL GROSS",     format_currency(total_gross),   ACCENT),
            ("TICKETS SOLD",    f"{total_tickets:,}",           ACCENT),
            ("STATES",          str(num_states),                ACCENT),
            ("THEATRES",        str(num_venues),                ACCENT),
            ("AVG OCCUPANCY",   f"{total_occ}%",                occ_color(total_occ)),
            ("TOTAL SHOWS",     str(num_shows),                 ACCENT),
        ]
        kpi_cols = 3
        kpi_w    = (W - 2) // kpi_cols
        kpi_h    = 140
        # background
        draw.rectangle([0, y, W, y + kpi_h * 2], fill=SURFACE)
        for i, (label, val, col) in enumerate(kpis):
            col_i = i % kpi_cols
            row_i = i // kpi_cols
            kx = col_i * kpi_w
            ky = y + row_i * kpi_h
            # border
            draw.rectangle([kx, ky, kx + kpi_w, ky + kpi_h], outline=BORDER, width=1)
            # label
            lw = text_w(draw, label, F_LABEL)
            draw.text((kx + kpi_w//2 - lw//2, ky + 18), label, font=F_LABEL, fill=MUTED)
            # value
            vw = text_w(draw, val, F_LG)
            draw.text((kx + kpi_w//2 - vw//2, ky + 52), val, font=F_LG, fill=col)

        y += kpi_h * 2 + 40

        # ── PLATFORM BREAKDOWN ───────────────────────────────────────────────
        y = draw_section_header(draw, y, "Platform Breakdown", "BMS vs District")
        card_w = (W - PADDING * 2 - 20) // 2
        card_h = 230

        for pi, (name, gross_v, tickets_v, shows_v, col, top_col) in enumerate([
            ("BookMyShow",  src_gross_bms,  src_tickets_bms,  src_shows_bms,  BMS_C, BMS_C),
            ("District App",src_gross_dist, src_tickets_dist, src_shows_dist, DST_C, DST_C),
        ]):
            cx = PADDING + pi * (card_w + 20)
            cy = y
            draw_rounded_rect(draw, cx, cy, cx + card_w, cy + card_h, 14, fill=SURFACE, outline=BORDER, width=1)
            # top accent bar
            draw_rounded_rect(draw, cx, cy, cx + card_w, cy + 6, 4, fill=top_col)
            # name
            draw.text((cx + 20, cy + 20), name.upper(), font=F_LABEL, fill=MUTED)
            # gross
            draw.text((cx + 20, cy + 50), format_currency(gross_v), font=F_LG, fill=col)
            # stats grid
            stats = [("Shows", str(shows_v)), ("Tickets", f"{tickets_v:,}"),
                     ("% Share", f"{round((gross_v/total_gross)*100,1) if total_gross else 0}%")]
            sw = (card_w - 40) // 3
            for si, (sl, sv) in enumerate(stats):
                sx = cx + 20 + si * sw
                draw.text((sx, cy + 150), sl, font=F_LABEL, fill=MUTED)
                draw.text((sx, cy + 176), sv, font=F_BODY_B, fill=TEXT)

        y += card_h + 48

        # ── TABLE HELPER ─────────────────────────────────────────────────────
        def draw_table(draw, y, headers, rows_data, col_widths, alignments):
            """Draw a styled table. alignments: 'L' or 'R' per column."""
            row_h   = 54
            head_h  = 42
            tbl_w   = W - PADDING * 2
            tx      = PADDING

            # header bg
            draw.rectangle([tx, y, tx + tbl_w, y + head_h], fill=SURFACE2)
            draw_rounded_rect(draw, tx, y, tx + tbl_w, y + head_h, 0, fill=SURFACE2)

            cx = tx
            for hi, (hdr, cw, align) in enumerate(zip(headers, col_widths, alignments)):
                hdr_t = hdr
                max_hw = cw - 4
                while len(hdr_t) > 1 and text_w(draw, hdr_t, F_LABEL) > max_hw:
                    hdr_t = hdr_t[:-1]
                if align == 'R':
                    hw = text_w(draw, hdr_t, F_LABEL)
                    draw.text((cx + cw - hw - 6, y + 12), hdr_t, font=F_LABEL, fill=MUTED)
                else:
                    draw.text((cx + 8, y + 12), hdr_t, font=F_LABEL, fill=MUTED)
                cx += cw
            y += head_h

            for ri, row in enumerate(rows_data):
                row_bg = SURFACE if ri % 2 == 0 else BG
                draw.rectangle([tx, y, tx + tbl_w, y + row_h], fill=row_bg)
                cx = tx
                for ci, (cell, cw, align) in enumerate(zip(row, col_widths, alignments)):
                    if isinstance(cell, dict) and cell.get("type") == "occ_bar":
                        # Fixed zones inside OCC col (162px):
                        # [6px pad][70px bar track][6px gap][~76px pct text][4px pad]
                        occ_val  = cell["value"]
                        o_col    = occ_color(occ_val)
                        occ_str  = f"{occ_val}%"
                        pct_w    = text_w(draw, occ_str, F_SMALL)
                        bar_x    = cx + 6
                        bar_end  = cx + 82                        # bar zone: 6+76=82
                        bar_fill = int(76 * occ_val / 100)
                        bar_y    = y + row_h // 2 - 5
                        # track
                        draw_rounded_rect(draw, bar_x, bar_y, bar_end, bar_y + 10, 5, fill=SURFACE2)
                        # fill
                        if bar_fill > 0:
                            draw_rounded_rect(draw, bar_x, bar_y, bar_x + bar_fill, bar_y + 10, 5, fill=o_col)
                        # % text: right-aligned in remaining space (bar_end+6 .. cx+cw-4)
                        text_x = cx + cw - 4 - pct_w
                        draw.text((text_x, bar_y - 2), occ_str, font=F_SMALL, fill=o_col)
                    else:
                        cell_str = str(cell)
                        font     = F_BODY_B if ci in (1, 2) else F_BODY
                        col_fill = ACCENT if ci == len(row) - 1 else TEXT
                        # Truncate text so it never spills into the next column
                        max_text_w = cw - 16
                        while len(cell_str) > 1 and text_w(draw, cell_str, font) > max_text_w:
                            cell_str = cell_str[:-1]
                        if align == 'R':
                            cw2 = text_w(draw, cell_str, font)
                            draw.text((cx + cw - cw2 - 8, y + row_h // 2 - 11), cell_str, font=font, fill=col_fill)
                        else:
                            draw.text((cx + 8, y + row_h // 2 - 11), cell_str, font=font, fill=col_fill)
                    cx += cw
                # border line
                draw.line([(tx, y + row_h), (tx + tbl_w, y + row_h)], fill=BORDER, width=1)
                y += row_h

            # outer border
            draw_rounded_rect(draw, tx, y - row_h * len(rows_data) - head_h,
                              tx + tbl_w, y, 10, outline=BORDER, width=1)
            return y + 32

        # ── STATE TABLE ──────────────────────────────────────────────────────
        y = draw_section_header(draw, y, "State Rankings", "By Gross Collection")
        tbl_w = W - PADDING * 2
        # cols:        #    STATE  VENUES  SHOWS  TICKETS  OCCUPANCY  GROSS
        state_cws     = [46, 308, 92, 96, 140, 162, 140]
        state_headers = ["#", "STATE", "VENS", "SHOWS", "TICKETS", "OCCUPANCY", "GROSS"]
        state_aligns  = ["L", "L",     "R",      "R",     "R",       "L",          "R"]

        state_rows_data = []
        for i, s in enumerate(state_list[:TOP_ROWS], 1):
            state_rows_data.append([
                str(i),
                s.get("name", s.get("state", "?")),  # state name key
                str(s["venues"]),
                str(s["shows"]),
                f"{s['tickets']:,}",
                {"type": "occ_bar", "value": s["occupancy"]},
                format_currency(s["gross"]),
            ])

        # Fix: state_list rows use key "name" from our aggregate function — let's check
        # Actually aggregate returns dicts from state_stats which has state name as the dict key
        # We need to re-check our aggregate output
        # The build_list function copies all keys from the stats dict, state name isn't inside
        # Let's handle this in the data prep below

        y = draw_table(draw, y, state_headers, state_rows_data, state_cws, state_aligns)

        # ── CITY TABLE ───────────────────────────────────────────────────────
        y = draw_section_header(draw, y, "City Rankings", "Top 10 · By Gross")
        city_headers = ["#", "CITY", "VENS", "SHOWS", "TICKETS", "OCCUPANCY", "GROSS"]
        # cols:     #    CITY  SHOWS  TICKETS  OCCUPANCY  GROSS
        city_cws  = [46, 308, 92, 96, 140, 162, 140]
        city_aligns  = ["L", "L",  "R",   "R",     "R",       "L",          "R"]

        city_rows_data = []
        for i, c in enumerate(city_list[:TOP_ROWS], 1):
            city_rows_data.append([
                str(i),
                c["city"],
                str(c["venues"]),
                str(c["shows"]),
                f"{c['tickets']:,}",
                {"type": "occ_bar", "value": c["occupancy"]},
                format_currency(c["gross"]),
            ])

        y = draw_table(draw, y, city_headers, city_rows_data, city_cws, city_aligns)

        # ── FOOTER ───────────────────────────────────────────────────────────
        y += 20
        foot_line1 = "Generated by CinePulseBO  ·  Data: BookMyShow & District"
        foot_line2 = datetime.now().strftime("%d %b %Y, %I:%M %p")
        foot_h = 100
        draw.rectangle([0, y, W, y + foot_h], fill=SURFACE)
        fw1 = text_w(draw, foot_line1, F_SMALL)
        fw2 = text_w(draw, foot_line2, F_SMALL)
        draw.text((W // 2 - fw1 // 2, y + 18), foot_line1, font=F_SMALL, fill=MUTED)
        draw.text((W // 2 - fw2 // 2, y + 54), foot_line2, font=F_SMALL, fill=MUTED)
        y += foot_h

        return img, y

    # First pass: estimate height
    _, est_h = render(8000, final=False)

    # Second pass: render at exact height
    img, _ = render(est_h + 20, final=True)

    # Crop to content
    img = img.crop((0, 0, W, est_h + 20))

    # ── WATERMARK ────────────────────────────────────────────────────────────
    if WATERMARK_ENABLED:
        img = _apply_watermark(img)

    # Save
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    print(f"✅ Image report saved: {output_path}  ({W}×{est_h + 20}px)")
    return output_path


# ── AGGREGATE FIX: state name is the dict key, not inside value ──────────────
# Patch aggregate to include name in each row
_orig_aggregate = aggregate
def aggregate(all_results):
    state_stats = {}
    city_stats  = {}

    for r in all_results:
        state   = r.get("state", "Unknown")
        city    = r.get("city",  "Unknown")
        venue   = r["venue"]
        gross   = r["booked_gross"]
        tickets = r["booked_tickets"]
        seats   = r["total_tickets"]

        if state not in state_stats:
            state_stats[state] = {"name": state, "gross":0,"tickets":0,"seats":0,"shows":0,"venues":set()}
        s = state_stats[state]
        s["gross"] += gross; s["tickets"] += tickets
        s["seats"] += seats; s["shows"]   += 1; s["venues"].add(venue)

        ck = (state, city)
        if ck not in city_stats:
            city_stats[ck] = {"city":city,"state":state,"gross":0,"tickets":0,"seats":0,"shows":0,"venues":set()}
        c = city_stats[ck]
        c["gross"] += gross; c["tickets"] += tickets
        c["seats"] += seats; c["shows"]   += 1; c["venues"].add(venue)

    def build_list(d):
        out = []
        for k, v in d.items():
            occ = round((v["tickets"]/v["seats"])*100, 1) if v["seats"] else 0
            row = {k2: (len(v2) if isinstance(v2, set) else v2) for k2, v2 in v.items()}
            row["occupancy"] = occ
            out.append(row)
        out.sort(key=lambda x: x["gross"], reverse=True)
        return out

    return build_list(state_stats), build_list(city_stats)


# ── DEMO / TEST ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import random

    states_cities = {
        "Telangana":    ["Hyderabad", "Warangal", "Karimnagar"],
        "Andhra Pradesh": ["Vijayawada", "Visakhapatnam", "Tirupati", "Guntur"],
        "Tamil Nadu":   ["Chennai", "Coimbatore", "Madurai"],
        "Karnataka":    ["Bengaluru", "Mysuru", "Mangaluru"],
        "Kerala":       ["Kochi", "Thiruvananthapuram", "Kozhikode"],
    }

    venues_by_city = {
        "Hyderabad":    ["AMB Cinemas", "PVR IMAX Inorbit", "Cinepolis Kukatpally", "Asian Mukta A2"],
        "Vijayawada":   ["PVR CinemaS", "SVC Cinemas", "Imax Cinemas"],
        "Chennai":      ["PVR SPI Palazzo", "INOX Chennai", "AGS Cinemas"],
        "Bengaluru":    ["PVR Orion", "INOX Garuda", "Cinepolis HSR"],
        "Kochi":        ["PVR LuLu", "INOX Oberon", "PVR Gold"],
        "Warangal":     ["Sri Mayuri Theatre", "Vinayaka Cinemas"],
        "Coimbatore":   ["INOX Brookefields", "Cinepolis Fun Mall"],
        "Mysuru":       ["PVR Forum", "Cinepolis Mysuru Mall"],
        "Thiruvananthapuram": ["PVR Kims", "INOX TVM"],
        "Tirupati":     ["Sri Devi Theatre", "Nagaland Complex"],
        "Guntur":       ["Sri Ram Cinemas", "PVR Guntur"],
        "Karimnagar":   ["Vaishnavi Theatre", "MGM Complex"],
        "Visakhapatnam":["PVR CMR", "INOX Vizag", "Cinepolis Rushikonda"],
        "Madurai":      ["Inox Madurai", "AGS Cinemas Madurai"],
        "Mangaluru":    ["PVR Forum", "INOX Mangaluru"],
        "Kozhikode":    ["PVR Kozhikode", "INOX Kozhikode"],
    }

    random.seed(42)
    sample_data = []

    for state, cities in states_cities.items():
        for city in cities:
            venues = venues_by_city.get(city, [f"{city} Cinema 1", f"{city} Cinema 2"])
            for venue in venues:
                for _ in range(random.randint(2, 6)):
                    total   = random.choice([150, 200, 250, 300, 400])
                    booked  = random.randint(int(total * 0.25), total)
                    price   = random.choice([180, 200, 250, 300, 350, 400])
                    source  = random.choice(["bms", "district"])
                    sample_data.append({
                        "state":          state,
                        "city":           city,
                        "venue":          venue,
                        "booked_tickets": booked,
                        "total_tickets":  total,
                        "booked_gross":   booked * price,
                        "source":         source,
                    })

    generate_image_report(
        sample_data,
        output_path="box_office_report.png",
        movie_name="KALKI 2898 AD",
        show_date="16 Mar 2025"
    )
