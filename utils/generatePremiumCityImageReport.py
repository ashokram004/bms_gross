"""
Multi-City Image Report Generator - Premium Dark UI
Exact same rendering engine as the states reporter (proven working).
"""
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from collections import defaultdict
import os

# ── CONFIG ────────────────────────────────────────────────────────────────────
W            = 1080
PADDING      = 48
TOP_THEATRES = 10

# ── WATERMARK ─────────────────────────────────────────────────────────────────
WATERMARK_ENABLED = True
WATERMARK_TEXT    = "CINEPULSEBO"
WATERMARK_OPACITY = 80
WATERMARK_ANGLE   = 35

# ── COLOURS ───────────────────────────────────────────────────────────────────
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

# ── FONTS ─────────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    cb = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
          "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]
    cr = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
          "/usr/share/fonts/truetype/freefont/FreeSans.ttf"]
    for p in (cb if bold else cr):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

F_SMALL  = load_font(20)
F_BODY   = load_font(22)
F_BODY_B = load_font(22, bold=True)
F_MED    = load_font(32, bold=True)
F_LG     = load_font(44, bold=True)
F_LABEL  = load_font(17)

# ── UTILITIES ─────────────────────────────────────────────────────────────────
def format_currency(v):
    if v >= 10_000_000: return f"Rs.{v/10_000_000:.2f} Cr"
    if v >= 100_000:    return f"Rs.{v/100_000:.2f} L"
    if v >= 1_000:      return f"Rs.{v/1_000:.1f} K"
    return f"Rs.{v:.0f}"

def occ_color(o):
    return GREEN if o >= 60 else ORANGE if o >= 50 else YELLOW if o >= 30 else RED

def text_w(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]

def draw_rounded_rect(draw, x1, y1, x2, y2, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill, outline=outline, width=width)

def draw_section_header(draw, y, title, subtitle=""):
    draw.text((PADDING, y), title.upper(), font=F_MED, fill=TEXT)
    if subtitle:
        sx = PADDING + text_w(draw, title.upper(), F_MED) + 20
        draw.text((sx, y + 8), subtitle.upper(), font=F_LABEL, fill=MUTED)
    draw.line([(PADDING, y + 52), (W - PADDING, y + 52)], fill=BORDER, width=2)
    return y + 70

# ── WATERMARK ─────────────────────────────────────────────────────────────────
def _apply_watermark(img):
    wm_font = load_font(72, bold=True)
    tmp = Image.new("RGBA", (1, 1))
    td  = ImageDraw.Draw(tmp)
    bb  = td.textbbox((0, 0), WATERMARK_TEXT, font=wm_font)
    tw_ = bb[2] - bb[0]; th_ = bb[3] - bb[1]
    tile_w = tw_ + 120;  tile_h = th_ + 100
    tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    tdr  = ImageDraw.Draw(tile)
    tdr.text(((tile_w - tw_) // 2, (tile_h - th_) // 2), WATERMARK_TEXT,
             font=wm_font, fill=(255, 255, 255, WATERMARK_OPACITY))
    rotated = tile.rotate(WATERMARK_ANGLE, expand=True)
    rw, rh  = rotated.size
    W_, H_  = img.size
    overlay = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    for y_ in range(-rh, H_ + rh, rh):
        for x_ in range(-rw, W_ + rw, rw):
            overlay.paste(rotated, (x_, y_), rotated)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

# ── TABLE HELPER ──────────────────────────────────────────────────────────────
def draw_table(draw, y, headers, rows_data, col_widths, alignments):
    row_h  = 54
    head_h = 42
    tbl_w  = W - PADDING * 2
    tx     = PADDING

    # header row
    draw_rounded_rect(draw, tx, y, tx + tbl_w, y + head_h, 0, fill=SURFACE2)
    cx = tx
    for hdr, cw, align in zip(headers, col_widths, alignments):
        h = hdr
        while len(h) > 1 and text_w(draw, h, F_LABEL) > cw - 4:
            h = h[:-1]
        if align == 'R':
            draw.text((cx + cw - text_w(draw, h, F_LABEL) - 6, y + 12), h, font=F_LABEL, fill=MUTED)
        else:
            draw.text((cx + 8, y + 12), h, font=F_LABEL, fill=MUTED)
        cx += cw
    y += head_h

    for ri, row in enumerate(rows_data):
        row_bg = SURFACE if ri % 2 == 0 else BG
        draw.rectangle([tx, y, tx + tbl_w, y + row_h], fill=row_bg)
        cx = tx
        for ci, (cell, cw, align) in enumerate(zip(row, col_widths, alignments)):
            if isinstance(cell, dict) and cell.get("type") == "occ_bar":
                # Fixed-zone occ bar: [6px][76px bar][gap][pct text][4px]
                occ_val  = cell["value"]
                o_col    = occ_color(occ_val)
                occ_str  = f"{occ_val}%"
                pct_w    = text_w(draw, occ_str, F_SMALL)
                bar_x    = cx + 6
                bar_end  = cx + 82
                bar_fill = int(76 * occ_val / 100)
                bar_y    = y + row_h // 2 - 5
                draw_rounded_rect(draw, bar_x, bar_y, bar_end, bar_y + 10, 5, fill=SURFACE2)
                if bar_fill > 0:
                    draw_rounded_rect(draw, bar_x, bar_y, bar_x + bar_fill, bar_y + 10, 5, fill=o_col)
                draw.text((cx + cw - 4 - pct_w, bar_y - 2), occ_str, font=F_SMALL, fill=o_col)
            else:
                is_gross = (ci == len(row) - 1)
                font     = F_BODY_B if ci in (1, 2) else F_BODY
                col_fill = ACCENT if is_gross else TEXT
                cell_str = str(cell)
                max_cw   = cw - 16
                while len(cell_str) > 1 and text_w(draw, cell_str, font) > max_cw:
                    cell_str = cell_str[:-1]
                if align == 'R':
                    draw.text((cx + cw - text_w(draw, cell_str, font) - 8,
                               y + row_h // 2 - 11), cell_str, font=font, fill=col_fill)
                else:
                    draw.text((cx + 8, y + row_h // 2 - 11), cell_str, font=font, fill=col_fill)
            cx += cw
        draw.line([(tx, y + row_h), (tx + tbl_w, y + row_h)], fill=BORDER, width=1)
        y += row_h

    draw_rounded_rect(draw, tx, y - row_h * len(rows_data) - head_h,
                      tx + tbl_w, y, 10, outline=BORDER, width=1)
    return y + 32

# ── URL PARSER ────────────────────────────────────────────────────────────────
def parse_metadata(url):
    try:
        parsed = urlparse(url)
        pts    = [p for p in parsed.path.split('/') if p]
        mn     = "Movie Collection"
        sd     = datetime.now().strftime("%d %b %Y")
        if "movies" in pts:
            for pt in pts:
                if "-movie-tickets-in-" in pt:
                    mn = pt.split("-movie-tickets-in-")[0].replace("-", " ").title()
                    break
            q = parse_qs(parsed.query)
            if "fromdate" in q:
                sd = datetime.strptime(q["fromdate"][0], "%Y-%m-%d").strftime("%d %b %Y")
        elif "buytickets" in pts:
            idx = pts.index("buytickets")
            if idx >= 1:
                mn = pts[idx - 1].replace("-", " ").title()
            try:
                sd = datetime.strptime(pts[-1], "%Y%m%d").strftime("%d %b %Y")
            except: pass
        return mn, sd
    except:
        return "Movie Collection", datetime.now().strftime("%d %b %Y")

# ── MAIN GENERATOR ────────────────────────────────────────────────────────────
def generate_premium_city_image_report(all_results, output_path,
                                       movie_name="Movie Collection",
                                       show_date=None, ref_url=None):
    if ref_url:
        movie_name, show_date = parse_metadata(ref_url)
    if show_date is None:
        show_date = datetime.now().strftime("%d %b %Y")

    # ── Aggregate by city ─────────────────────────────────────────────────────
    city_map = defaultdict(lambda: {"gross":0,"tickets":0,"seats":0,"shows":0,"venues":set()})
    for r in all_results:
        c = r.get("city", "Unknown")
        city_map[c]["gross"]   += r["booked_gross"]
        city_map[c]["tickets"] += r["booked_tickets"]
        city_map[c]["seats"]   += r["total_tickets"]
        city_map[c]["shows"]   += 1
        city_map[c]["venues"].add(r["venue"])

    city_list = sorted([
        {"name": c, "gross": d["gross"], "tickets": d["tickets"],
         "seats": d["seats"], "shows": d["shows"], "venues": len(d["venues"]),
         "occ": round((d["tickets"] / d["seats"]) * 100, 1) if d["seats"] else 0}
        for c, d in city_map.items()
    ], key=lambda x: x["gross"], reverse=True)

    # ── Aggregate by venue ────────────────────────────────────────────────────
    venue_map = defaultdict(lambda: {"gross":0,"tickets":0,"seats":0,"shows":0,"city":""})
    for r in all_results:
        v = r["venue"]
        venue_map[v]["gross"]   += r["booked_gross"]
        venue_map[v]["tickets"] += r["booked_tickets"]
        venue_map[v]["seats"]   += r["total_tickets"]
        venue_map[v]["shows"]   += 1
        venue_map[v]["city"]     = r.get("city", "")

    venue_list = sorted([
        {"name": v, "city": d["city"], "gross": d["gross"], "tickets": d["tickets"],
         "seats": d["seats"], "shows": d["shows"],
         "occ": round((d["tickets"] / d["seats"]) * 100, 1) if d["seats"] else 0}
        for v, d in venue_map.items()
    ], key=lambda x: x["gross"], reverse=True)

    # ── Totals ────────────────────────────────────────────────────────────────
    total_gross   = sum(r["booked_gross"]   for r in all_results)
    total_tickets = sum(r["booked_tickets"] for r in all_results)
    total_seats   = sum(r["total_tickets"]  for r in all_results)
    total_occ     = round((total_tickets / total_seats) * 100, 1) if total_seats else 0
    num_shows     = len(all_results)
    num_cities    = len(city_list)
    num_venues    = len(venue_map)

    src_gross_bms    = sum(r["booked_gross"]   for r in all_results if r.get("source") == "bms")
    src_gross_dist   = sum(r["booked_gross"]   for r in all_results if r.get("source") == "district")
    src_tickets_bms  = sum(r["booked_tickets"] for r in all_results if r.get("source") == "bms")
    src_tickets_dist = sum(r["booked_tickets"] for r in all_results if r.get("source") == "district")
    src_shows_bms    = sum(1 for r in all_results if r.get("source") == "bms")
    src_shows_dist   = sum(1 for r in all_results if r.get("source") == "district")

    # ── Render ────────────────────────────────────────────────────────────────
    def render(canvas_h):
        img  = Image.new("RGB", (W, canvas_h), BG)
        draw = ImageDraw.Draw(img)
        y    = 0

        # ── HERO (exact same pattern as working states reporter) ──────────────
        hero_h_max = 260
        for gy in range(hero_h_max):
            t   = gy / hero_h_max
            r_c = int(10 + t * 8)
            g_c = int(10 + t * 2)
            b_c = int(15 + t * 18)
            draw.line([(0, gy), (W, gy)], fill=(r_c, g_c, b_c))

        draw.text((PADDING, y + 20), "CITY BOX OFFICE REPORT", font=F_LABEL, fill=ACCENT)

        title_y    = y + 44
        title_text = movie_name.upper()
        max_title_w = W - PADDING * 2

        # Auto-shrink font so title never exceeds 2 lines
        title_size = 76
        title_font = load_font(title_size, bold=True)
        while title_size > 32:
            words_tmp = title_text.split()
            lines_tmp = []; cur_tmp = ""
            for word in words_tmp:
                test = (cur_tmp + " " + word).strip()
                if text_w(draw, test, title_font) <= max_title_w:
                    cur_tmp = test
                else:
                    if cur_tmp: lines_tmp.append(cur_tmp)
                    cur_tmp = word
            if cur_tmp: lines_tmp.append(cur_tmp)
            if len(lines_tmp) <= 2:
                break
            title_size -= 4
            title_font = load_font(title_size, bold=True)

        words   = title_text.split()
        lines   = []
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

        line_bb  = draw.textbbox((0, 0), "Ag", font=title_font)
        line_h   = line_bb[3] - line_bb[1]
        line_gap = 8
        ty = title_y
        for line in lines:
            draw.text((PADDING + 2, ty + 2), line, font=title_font, fill=(20, 20, 30))
            draw.text((PADDING,     ty),     line, font=title_font, fill=TEXT)
            ty += line_h + line_gap
        title_px_h = ty - title_y - line_gap

        pill_h = 36
        meta_y = title_y + title_px_h + 22
        mx = PADDING
        for label in [show_date, f"{num_cities} Cities",
                      f"{num_venues} Theatres", f"{num_shows} Shows"]:
            pill_w = text_w(draw, label, F_SMALL) + 24
            draw_rounded_rect(draw, mx, meta_y, mx + pill_w, meta_y + pill_h, 8, fill=SURFACE2)
            draw.text((mx + 12, meta_y + 8), label, font=F_SMALL, fill=MUTED)
            mx += pill_w + 10

        # ← CRITICAL: hero_h is a delta, NOT added to meta_y
        hero_h = meta_y + pill_h + 36
        y += hero_h

        # ── KPI STRIP ─────────────────────────────────────────────────────────
        kpis = [
            ("TOTAL GROSS",   format_currency(total_gross), ACCENT),
            ("TICKETS SOLD",  f"{total_tickets:,}",         ACCENT),
            ("CAPACITY",      f"{total_seats:,}",           ACCENT),
            ("AVG OCCUPANCY", f"{total_occ}%",              occ_color(total_occ)),
            ("CITIES",        str(num_cities),              ACCENT),
            ("TOTAL SHOWS",   str(num_shows),               ACCENT),
        ]
        kpi_cols = 3
        kpi_w    = (W - 2) // kpi_cols
        kpi_h    = 140
        draw.rectangle([0, y, W, y + kpi_h * 2], fill=SURFACE)
        for i, (label, val, col) in enumerate(kpis):
            col_i = i % kpi_cols
            row_i = i // kpi_cols
            kx    = col_i * kpi_w
            ky    = y + row_i * kpi_h
            draw.rectangle([kx, ky, kx + kpi_w, ky + kpi_h], outline=BORDER, width=1)
            lw = text_w(draw, label, F_LABEL)
            draw.text((kx + kpi_w // 2 - lw // 2, ky + 18), label, font=F_LABEL, fill=MUTED)
            vw = text_w(draw, val, F_LG)
            draw.text((kx + kpi_w // 2 - vw // 2, ky + 52), val,   font=F_LG,   fill=col)
        y += kpi_h * 2 + 40

        # ── PLATFORM BREAKDOWN ────────────────────────────────────────────────
        y = draw_section_header(draw, y, "Platform Breakdown", "BMS vs District")
        card_w = (W - PADDING * 2 - 20) // 2
        card_h = 230
        for pi, (name, gross_v, tickets_v, shows_v, col) in enumerate([
            ("BookMyShow",   src_gross_bms,  src_tickets_bms,  src_shows_bms,  BMS_C),
            ("District App", src_gross_dist, src_tickets_dist, src_shows_dist, DST_C),
        ]):
            cx = PADDING + pi * (card_w + 20)
            cy = y
            draw_rounded_rect(draw, cx, cy, cx + card_w, cy + card_h, 14,
                               fill=SURFACE, outline=BORDER, width=1)
            draw_rounded_rect(draw, cx, cy, cx + card_w, cy + 6, 4, fill=col)
            draw.text((cx + 20, cy + 20), name.upper(),           font=F_LABEL, fill=MUTED)
            draw.text((cx + 20, cy + 50), format_currency(gross_v), font=F_LG,  fill=col)
            stats = [("Shows", str(shows_v)),
                     ("Tickets", f"{tickets_v:,}"),
                     ("% Share", f"{round((gross_v / total_gross) * 100, 1) if total_gross else 0}%")]
            sw = (card_w - 40) // 3
            for si, (sl, sv) in enumerate(stats):
                sx = cx + 20 + si * sw
                draw.text((sx, cy + 150), sl, font=F_LABEL, fill=MUTED)
                draw.text((sx, cy + 176), sv, font=F_BODY_B, fill=TEXT)
        y += card_h + 48

        # ── CITY RANKINGS ─────────────────────────────────────────────────────
        y = draw_section_header(draw, y, "City Rankings", "By Gross Collection")
        tbl_w = W - PADDING * 2
        # #(46) CITY(308) VENS(92) SHOWS(96) TICKETS(140) OCC(162) GROSS(140)
        c_cws     = [46, 308, 92, 96, 140, 162, 140]
        c_headers = ["#", "CITY", "VENS", "SHOWS", "TICKETS", "OCCUPANCY", "GROSS"]
        c_aligns  = ["L", "L",    "R",    "R",     "R",       "L",         "R"]

        city_rows = []
        for i, c in enumerate(city_list, 1):
            city_rows.append([
                str(i), c["name"], str(c["venues"]), str(c["shows"]),
                f"{c['tickets']:,}",
                {"type": "occ_bar", "value": c["occ"]},
                format_currency(c["gross"]),
            ])
        y = draw_table(draw, y, c_headers, city_rows, c_cws, c_aligns)

        # ── TOP THEATRES ──────────────────────────────────────────────────────
        show_n = min(len(venue_list), TOP_THEATRES)
        y = draw_section_header(draw, y, "Top Theatres",
                                f"Top {show_n} Across All Cities · By Gross")
        # #(46) CITY(180) THEATRE(name_col) SHOWS(72) OCC(162) GROSS(140)
        th_name_col = tbl_w - 46 - 180 - 72 - 162 - 140
        th_cws      = [46, 180, th_name_col, 72, 162, 140]
        th_headers  = ["#", "CITY", "THEATRE", "SHOWS", "OCCUPANCY", "GROSS"]
        th_aligns   = ["L", "L",    "L",        "R",    "L",         "R"]

        th_rows = []
        for i, v in enumerate(venue_list[:TOP_THEATRES], 1):
            th_rows.append([
                str(i), v["city"], v["name"], str(v["shows"]),
                {"type": "occ_bar", "value": v["occ"]},
                format_currency(v["gross"]),
            ])
        y = draw_table(draw, y, th_headers, th_rows, th_cws, th_aligns)

        # ── FOOTER ────────────────────────────────────────────────────────────
        y += 20
        foot_h = 100
        draw.rectangle([0, y, W, y + foot_h], fill=SURFACE)
        foot1 = "Generated by CinePulseBO  ·  Data: BookMyShow & District"
        foot2 = datetime.now().strftime("%d %b %Y, %I:%M %p")
        draw.text((W // 2 - text_w(draw, foot1, F_SMALL) // 2, y + 18), foot1,
                  font=F_SMALL, fill=MUTED)
        draw.text((W // 2 - text_w(draw, foot2, F_SMALL) // 2, y + 54), foot2,
                  font=F_SMALL, fill=MUTED)
        y += foot_h
        return img, y

    # Two-pass render: first for height estimation, second at exact size
    _, est_h = render(8000)
    img, _   = render(est_h + 20)
    img      = img.crop((0, 0, W, est_h + 20))

    if WATERMARK_ENABLED:
        img = _apply_watermark(img)

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    print(f"Multi-city image report saved: {output_path}  ({W}x{est_h + 20}px)")
    return output_path

# ── DEMO ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import random
    cv = {
        "Hyderabad":  ["PVR IMAX Inorbit","AMB Cinemas IMAX","Cinepolis Kukatpally",
                       "Asian Mukta A2","Prasads Multiplex","Sudarshan 35mm","INOX GVK One"],
        "Chennai":    ["PVR SPI Palazzo","INOX Chennai","AGS Cinemas","Sathyam Cinemas"],
        "Bengaluru":  ["PVR Orion","INOX Garuda","Cinepolis HSR","PVR Forum"],
        "Vijayawada": ["PVR Vijayawada","SVC Cinemas","Imax Cinemas"],
    }
    random.seed(7)
    sample = []
    for city, venues in cv.items():
        for v in venues:
            for _ in range(random.randint(3, 8)):
                t = random.choice([150, 200, 250, 300, 400, 500])
                b = random.randint(int(t * 0.2), t)
                sample.append({
                    "city": city, "venue": v,
                    "booked_tickets": b, "total_tickets": t,
                    "booked_gross": b * random.choice([150, 200, 250, 300, 350, 400]),
                    "source": random.choice(["bms", "district"]),
                })
    generate_premium_city_image_report(
        sample, "multi_city_report.png",
        movie_name="DEVARA PART 2", show_date="16 Mar 2026")