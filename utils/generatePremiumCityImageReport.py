"""
City-level Image Report Generator - Premium Dark UI
Generates a mobile-optimized PNG for a single city:
  - Hero (movie + city + date + theatre/show counts)
  - KPI strip (Gross, Tickets, Capacity, Occupancy, Theatres, Shows)
  - Platform breakdown (BMS vs District)
  - Theatre rankings (top 20)
  - Footer
"""

from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import os


# ── CONFIG ───────────────────────────────────────────────────────────────────
W       = 1080
PADDING = 48
TOP_THEATRES = 20

# ── WATERMARK ────────────────────────────────────────────────────────────────
WATERMARK_ENABLED = True          # Set False to disable watermark entirely
WATERMARK_TEXT    = "CINEPULSEBO"  # Text to repeat across the image
WATERMARK_OPACITY = 80            # 0–255 (lower = more transparent). 18 is very subtle
WATERMARK_ANGLE   = 35            # Diagonal angle in degrees

# Colours
BG       = (10,  10,  15)
SURFACE  = (19,  19,  28)
SURFACE2 = (28,  28,  42)
BORDER   = (42,  42,  61)
ACCENT   = (245, 166,  35)
ACCENT2  = (232,  23,  77)
TEXT     = (232, 232, 240)
MUTED    = (112, 112, 160)
BMS_C    = (232,  23,  77)
DST_C    = (155,  75, 225)

GREEN    = (0,   200,  83)
ORANGE   = (255, 109,   0)
YELLOW   = (255, 214,   0)
RED      = (255,  23,  68)


# ── FONTS ────────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
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
    for path in (candidates_bold if bold else candidates_reg):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

F_TINY   = load_font(18)
F_SMALL  = load_font(20)
F_BODY   = load_font(22)
F_BODY_B = load_font(22, bold=True)
F_MED    = load_font(32, bold=True)
F_LG     = load_font(44, bold=True)
F_LABEL  = load_font(17)


# ── UTILITIES ─────────────────────────────────────────────────────────────────
def format_currency(value):
    if value >= 10_000_000: return f"₹{value/10_000_000:.2f} Cr"
    if value >= 100_000:    return f"₹{value/100_000:.2f} L"
    if value >= 1_000:      return f"₹{value/1_000:.1f} K"
    return f"₹{value:.0f}"

def occ_color(occ):
    if occ >= 60:   return GREEN
    elif occ >= 50: return ORANGE
    elif occ >= 30: return YELLOW
    return RED

def tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]

def draw_rrect(draw, x1, y1, x2, y2, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill, outline=outline, width=width)


# ── URL METADATA PARSER (mirrors HTML reporter) ───────────────────────────────
def parse_metadata(url):
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        movie_name = "Movie Collection"
        city_name  = "City"
        show_date  = datetime.now().strftime("%d %b %Y")

        if "movies" in path_parts:
            for p in path_parts:
                if "-movie-tickets-in-" in p:
                    parts = p.split("-movie-tickets-in-")
                    if len(parts) > 1:
                        movie_name = parts[0].replace("-", " ").title()
                        right_side = parts[1]
                        city_name  = (" ".join(right_side.split("-")[:-1]) if "-" in right_side
                                      else right_side).title()
                    break
            q = parse_qs(parsed.query)
            if 'fromdate' in q:
                show_date = datetime.strptime(q['fromdate'][0], "%Y-%m-%d").strftime("%d %b %Y")

        elif "buytickets" in path_parts:
            idx = path_parts.index("buytickets")
            if idx >= 2:
                movie_name = path_parts[idx - 1].replace("-", " ").title()
                city_name  = path_parts[idx - 2].replace("-", " ").title()
            try:
                show_date = datetime.strptime(path_parts[-1], "%Y%m%d").strftime("%d %b %Y")
            except: pass

        return movie_name, show_date, city_name
    except:
        return "Movie Collection", datetime.now().strftime("%d %b %Y"), "City"


# ── SECTION HEADER ────────────────────────────────────────────────────────────
def draw_section_header(draw, y, title, subtitle=""):
    draw.text((PADDING, y), title.upper(), font=F_MED, fill=TEXT)
    if subtitle:
        sub_x = PADDING + tw(draw, title.upper(), F_MED) + 20
        draw.text((sub_x, y + 8), subtitle.upper(), font=F_LABEL, fill=MUTED)
    draw.line([(PADDING, y + 52), (W - PADDING, y + 52)], fill=BORDER, width=2)
    return y + 70


# ── WATERMARK HELPER ─────────────────────────────────────────────────────────
def _apply_watermark(img):
    """Stamp a diagonal tiled watermark across the image using RGBA compositing."""
    from PIL import ImageFont
    wm_font = load_font(72, bold=True)

    # Build a small tile on a transparent canvas
    # Measure the text so the tile fits snugly
    tmp_img  = Image.new("RGBA", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp_img)
    bb   = tmp_draw.textbbox((0, 0), WATERMARK_TEXT, font=wm_font)
    tw_  = bb[2] - bb[0]
    th_  = bb[3] - bb[1]

    # Tile size: leave breathing room so tiles don't crowd each other
    tile_w = tw_ + 120
    tile_h = th_ + 100

    tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    td   = ImageDraw.Draw(tile)
    # Draw text centered in tile with the configured opacity
    tx = (tile_w - tw_) // 2
    ty = (tile_h - th_) // 2
    td.text((tx, ty), WATERMARK_TEXT, font=wm_font,
            fill=(255, 255, 255, WATERMARK_OPACITY))

    # Rotate the tile
    rotated = tile.rotate(WATERMARK_ANGLE, expand=True)
    rw, rh  = rotated.size

    # Build a full-size overlay by tiling the rotated stamp
    W_, H_ = img.size
    overlay = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    for y_ in range(-rh, H_ + rh, rh):
        for x_ in range(-rw, W_ + rw, rw):
            overlay.paste(rotated, (x_, y_), rotated)

    # Composite onto the original image
    base = img.convert("RGBA")
    out  = Image.alpha_composite(base, overlay)
    return out.convert("RGB")


# ── MAIN GENERATOR ────────────────────────────────────────────────────────────
def generate_premium_city_image_report(all_results, output_path,
                                movie_name="Movie Collection",
                                city_name="City",
                                show_date=None,
                                ref_url=None):
    """
    all_results : list of show dicts (same format as HTML reporter)
    output_path : where to save the PNG
    movie_name  : movie title (overridden by ref_url if provided)
    city_name   : city name   (overridden by ref_url if provided)
    show_date   : "DD Mon YYYY" string
    ref_url     : BMS/District URL — if given, movie_name/city_name/show_date are parsed from it
    """
    if ref_url:
        movie_name, show_date, city_name = parse_metadata(ref_url)
    if show_date is None:
        show_date = datetime.now().strftime("%d %b %Y")

    # ── Aggregate by venue ───────────────────────────────────────────────────
    venue_map = {}
    for r in all_results:
        v = r["venue"]
        if v not in venue_map:
            venue_map[v] = {"gross": 0, "tickets": 0, "shows": 0, "seats": 0}
        venue_map[v]["gross"]   += r["booked_gross"]
        venue_map[v]["tickets"] += r["booked_tickets"]
        venue_map[v]["shows"]   += 1
        venue_map[v]["seats"]   += r["total_tickets"]

    venue_list = []
    for name, d in venue_map.items():
        occ = round((d["tickets"] / d["seats"]) * 100, 1) if d["seats"] else 0
        venue_list.append({"name": name, "occ": occ, **d})
    venue_list.sort(key=lambda x: x["gross"], reverse=True)

    # ── Totals ───────────────────────────────────────────────────────────────
    total_gross   = sum(r["booked_gross"]   for r in all_results)
    total_tickets = sum(r["booked_tickets"] for r in all_results)
    total_seats   = sum(r["total_tickets"]  for r in all_results)
    total_occ     = round((total_tickets / total_seats) * 100, 1) if total_seats else 0
    num_shows     = len(all_results)
    num_venues    = len(venue_list)

    # ── Platform breakdown ───────────────────────────────────────────────────
    src_gross_bms    = sum(r["booked_gross"]   for r in all_results if r.get("source") == "bms")
    src_gross_dist   = sum(r["booked_gross"]   for r in all_results if r.get("source") == "district")
    src_tickets_bms  = sum(r["booked_tickets"] for r in all_results if r.get("source") == "bms")
    src_tickets_dist = sum(r["booked_tickets"] for r in all_results if r.get("source") == "district")
    src_shows_bms    = sum(1 for r in all_results if r.get("source") == "bms")
    src_shows_dist   = sum(1 for r in all_results if r.get("source") == "district")

    # ── Render function ───────────────────────────────────────────────────────
    def render(canvas_h):
        img  = Image.new("RGB", (W, canvas_h), BG)
        draw = ImageDraw.Draw(img)
        y    = 0

        # ── HERO ─────────────────────────────────────────────────────────────
        hero_h_max = 280
        for gy in range(hero_h_max):
            t = gy / hero_h_max
            draw.line([(0, gy), (W, gy)],
                      fill=(int(10 + t*8), int(10 + t*2), int(15 + t*18)))

        # eyebrow
        draw.text((PADDING, y + 20), "CITY BOX OFFICE REPORT", font=F_LABEL, fill=ACCENT)

        # movie title — word-wrap at 76px, never shrinks
        title_y    = y + 44
        title_text = movie_name.upper()
        title_font = load_font(76, bold=True)
        max_tw     = W - PADDING * 2
        words, lines, cur = title_text.split(), [], ""
        for word in words:
            test = (cur + " " + word).strip()
            if tw(draw, test, title_font) <= max_tw:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = word
        if cur: lines.append(cur)

        line_bb = draw.textbbox((0, 0), "Ag", font=title_font)
        line_h  = line_bb[3] - line_bb[1]
        line_gap = 8
        ty = title_y
        for line in lines:
            draw.text((PADDING + 2, ty + 2), line, font=title_font, fill=(20, 20, 30))
            draw.text((PADDING,     ty),     line, font=title_font, fill=TEXT)
            ty += line_h + line_gap
        title_px_h = ty - title_y - line_gap

        # city + date + meta pills
        pill_h = 36
        meta_y = title_y + title_px_h + 22
        meta_items = [
            city_name,
            show_date,
            f"{num_venues} Theatres",
            f"{num_shows} Shows",
        ]
        mx = PADDING
        for label in meta_items:
            pill_w = tw(draw, label, F_SMALL) + 24
            draw_rrect(draw, mx, meta_y, mx + pill_w, meta_y + pill_h, 8, fill=SURFACE2)
            # city pill gets accent color to stand out
            label_col = ACCENT if label == city_name else MUTED
            draw.text((mx + 12, meta_y + 8), label, font=F_SMALL, fill=label_col)
            mx += pill_w + 10

        hero_h = meta_y + pill_h + 36
        y += hero_h

        # ── KPI STRIP ────────────────────────────────────────────────────────
        kpis = [
            ("TOTAL GROSS",    format_currency(total_gross),  ACCENT),
            ("TICKETS SOLD",   f"{total_tickets:,}",          ACCENT),
            ("CAPACITY",       f"{total_seats:,}",            ACCENT),
            ("AVG OCCUPANCY",  f"{total_occ}%",               occ_color(total_occ)),
            ("THEATRES",       str(num_venues),               ACCENT),
            ("TOTAL SHOWS",    str(num_shows),                ACCENT),
        ]
        kpi_cols = 3
        kpi_w    = W // kpi_cols
        kpi_h    = 140
        draw.rectangle([0, y, W, y + kpi_h * 2], fill=SURFACE)
        for i, (label, val, col) in enumerate(kpis):
            col_i = i % kpi_cols
            row_i = i // kpi_cols
            kx = col_i * kpi_w
            ky = y + row_i * kpi_h
            draw.rectangle([kx, ky, kx + kpi_w, ky + kpi_h], outline=BORDER, width=1)
            lw = tw(draw, label, F_LABEL)
            draw.text((kx + kpi_w // 2 - lw // 2, ky + 18), label, font=F_LABEL, fill=MUTED)
            vw = tw(draw, val, F_LG)
            draw.text((kx + kpi_w // 2 - vw // 2, ky + 52), val,   font=F_LG,    fill=col)
        y += kpi_h * 2 + 40

        # ── PLATFORM BREAKDOWN ────────────────────────────────────────────────
        y = draw_section_header(draw, y, "Platform Breakdown", "BMS vs District")
        card_w = (W - PADDING * 2 - 20) // 2
        card_h = 230
        for pi, (name, gross_v, tickets_v, shows_v, col) in enumerate([
            ("BookMyShow",  src_gross_bms,  src_tickets_bms,  src_shows_bms,  BMS_C),
            ("District App",src_gross_dist, src_tickets_dist, src_shows_dist, DST_C),
        ]):
            cx = PADDING + pi * (card_w + 20)
            cy = y
            draw_rrect(draw, cx, cy, cx + card_w, cy + card_h, 14, fill=SURFACE, outline=BORDER, width=1)
            draw_rrect(draw, cx, cy, cx + card_w, cy + 6, 4, fill=col)
            draw.text((cx + 20, cy + 20), name.upper(), font=F_LABEL, fill=MUTED)
            draw.text((cx + 20, cy + 46), format_currency(gross_v), font=F_LG, fill=col)
            stats = [("Shows", str(shows_v)), ("Tickets", f"{tickets_v:,}"),
                     ("% Share", f"{round((gross_v/total_gross)*100,1) if total_gross else 0}%")]
            sw = (card_w - 40) // 3
            for si, (sl, sv) in enumerate(stats):
                sx = cx + 20 + si * sw
                draw.text((sx, cy + 150), sl, font=F_LABEL, fill=MUTED)
                draw.text((sx, cy + 174), sv, font=F_BODY_B, fill=TEXT)
        y += card_h + 48

        # ── THEATRE TABLE ─────────────────────────────────────────────────────
        show_n = min(len(venue_list), TOP_THEATRES)
        y = draw_section_header(draw, y, "Theatre Rankings",
                                f"Top {show_n} · By Gross Collection")
        tbl_w = W - PADDING * 2
        # cols: #(46) THEATRE(name, wide) SHOWS(80) SEATS(130) OCC(162) GROSS(140)
        name_col = tbl_w - 46 - 80 - 130 - 162 - 140
        th_cws     = [46, name_col, 80, 130, 162, 140]
        th_headers = ["#", "THEATRE", "SHOWS", "SEATS B/T", "OCCUPANCY", "GROSS"]
        th_aligns  = ["L", "L",       "R",     "R",          "L",         "R"]

        row_h  = 54
        head_h = 42
        tx     = PADDING

        # header
        draw.rectangle([tx, y, tx + tbl_w, y + head_h], fill=SURFACE2)
        cx = tx
        for hdr, cw, align in zip(th_headers, th_cws, th_aligns):
            hdr_t = hdr
            while len(hdr_t) > 1 and tw(draw, hdr_t, F_LABEL) > cw - 4:
                hdr_t = hdr_t[:-1]
            if align == 'R':
                hw = tw(draw, hdr_t, F_LABEL)
                draw.text((cx + cw - hw - 6, y + 12), hdr_t, font=F_LABEL, fill=MUTED)
            else:
                draw.text((cx + 8, y + 12), hdr_t, font=F_LABEL, fill=MUTED)
            cx += cw
        y += head_h

        for ri, v in enumerate(venue_list[:TOP_THEATRES]):
            row_bg = SURFACE if ri % 2 == 0 else BG
            draw.rectangle([tx, y, tx + tbl_w, y + row_h], fill=row_bg)
            cx = tx
            cells = [
                (str(ri + 1),                      "L", False, False),
                (v["name"],                        "L", True,  False),
                (str(v["shows"]),                  "R", False, False),
                (f"{v['tickets']}/{v['seats']}",   "R", False, False),
                ({"type": "occ_bar", "value": v["occ"]}, "L", False, False),
                (format_currency(v["gross"]),      "R", False, True),
            ]
            for (cell, align, bold, is_gross), cw in zip(cells, th_cws):
                if isinstance(cell, dict) and cell.get("type") == "occ_bar":
                    occ_val  = cell["value"]
                    o_col    = occ_color(occ_val)
                    occ_str  = f"{occ_val}%"
                    pct_w    = tw(draw, occ_str, F_SMALL)
                    bar_x    = cx + 6
                    bar_end  = cx + 82
                    bar_fill = int(76 * occ_val / 100)
                    bar_y    = y + row_h // 2 - 5
                    draw_rrect(draw, bar_x, bar_y, bar_end, bar_y + 10, 5, fill=SURFACE2)
                    if bar_fill > 0:
                        draw_rrect(draw, bar_x, bar_y, bar_x + bar_fill, bar_y + 10, 5, fill=o_col)
                    text_x = cx + cw - 4 - pct_w
                    draw.text((text_x, bar_y - 2), occ_str, font=F_SMALL, fill=o_col)
                else:
                    font     = F_BODY_B if bold else F_BODY
                    col_fill = ACCENT if is_gross else TEXT
                    # truncate to fit
                    cell_str = str(cell)
                    max_cw   = cw - 16
                    while len(cell_str) > 1 and tw(draw, cell_str, font) > max_cw:
                        cell_str = cell_str[:-1]
                    if align == 'R':
                        cw2 = tw(draw, cell_str, font)
                        draw.text((cx + cw - cw2 - 8, y + row_h // 2 - 11), cell_str, font=font, fill=col_fill)
                    else:
                        draw.text((cx + 8, y + row_h // 2 - 11), cell_str, font=font, fill=col_fill)
                cx += cw
            draw.line([(tx, y + row_h), (tx + tbl_w, y + row_h)], fill=BORDER, width=1)
            y += row_h

        draw_rrect(draw, tx, y - row_h * show_n - head_h,
                   tx + tbl_w, y, 10, outline=BORDER, width=1)
        y += 32

        # ── FOOTER ───────────────────────────────────────────────────────────
        y += 20
        foot_h = 100
        draw.rectangle([0, y, W, y + foot_h], fill=SURFACE)
        foot1 = "Generated by CinePulseBO ·  Data: BookMyShow & District"
        foot2 = datetime.now().strftime("%d %b %Y, %I:%M %p")
        draw.text((W // 2 - tw(draw, foot1, F_SMALL) // 2, y + 18), foot1, font=F_SMALL, fill=MUTED)
        draw.text((W // 2 - tw(draw, foot2, F_SMALL) // 2, y + 54), foot2, font=F_SMALL, fill=MUTED)
        y += foot_h

        return img, y

    _, est_h = render(8000)
    img, _   = render(est_h + 20)
    img      = img.crop((0, 0, W, est_h + 20))

    # ── WATERMARK ────────────────────────────────────────────────────────────
    if WATERMARK_ENABLED:
        img = _apply_watermark(img)

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    print(f"✅ City image report saved: {output_path}  ({W}×{est_h + 20}px)")
    return output_path


# ── DEMO ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import random

    venues = [
        "PVR IMAX Inorbit", "AMB Cinemas IMAX", "Cinepolis Kukatpally",
        "Asian Mukta A2", "Prasads Multiplex", "Sudarshan 35mm",
        "PVR Nexus", "INOX GVK One", "Cinepolis Forum Sujana",
        "Sandhya 70mm", "PVR Kukatpally", "Cineplanet Kompally",
        "Movietime Chintal", "Miraj Cinemas KPHB", "SPI Palazzo",
        "Carnival Cinemas", "PVR Attapur", "INOX Banjara Hills",
        "Cinepolis Manjeera", "Regal Talkies",
        "Grand Cinemas Uppal", "Star Theatre",
    ]
    random.seed(7)
    sample = []
    for venue in venues:
        for _ in range(random.randint(3, 8)):
            total  = random.choice([150, 200, 250, 300, 400, 500])
            booked = random.randint(int(total * 0.2), total)
            sample.append({
                "venue":          venue,
                "booked_tickets": booked,
                "total_tickets":  total,
                "booked_gross":   booked * random.choice([150, 180, 200, 250, 300, 350, 400]),
                "source":         random.choice(["bms", "district"]),
            })

    generate_premium_city_image_report(
        sample,
        output_path="city_report_hyderabad.png",
        movie_name="DEVARA PART 2",
        city_name="Hyderabad",
        show_date="16 Mar 2026",
    )
