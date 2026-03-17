"""
Premium Box Office Report Generator
Pixel-accurate match to reference image.
Output: 1280px wide
"""

from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os

# ── CANVAS WIDTH ─────────────────────────────────────────────────────────────
W   = 1280      # ← widened from 1080
PAD = 56        # ← slightly more padding to match proportionally

# ── WATERMARK ────────────────────────────────────────────────────────────────
WATERMARK_ENABLED = True
WATERMARK_TEXT    = "CINEPULSEBO"
WATERMARK_OPACITY = 90
WATERMARK_ANGLE   = 35

# ── EXACT COLOURS FROM REFERENCE ─────────────────────────────────────────────
BG       = (11,  10,  15)
SURFACE  = (20,  20,  30)
SURFACE2 = (30,  30,  44)
BORDER   = (46,  46,  64)
ACCENT   = (245, 166,  35)
TEXT     = (232, 232, 240)
MUTED    = (108, 108, 148)
BMS_C    = (232,  23,  77)
DST_C    = (152,  68, 222)
GREEN    = (30,  200,  80)
ORANGE   = (255, 120,   0)
YELLOW   = (240, 200,   0)
RED_OCC  = (220,  40,  60)

# ── FONTS — cross-platform, ₹ support required ───────────────────────────────
import sys, platform

def _find_font(bold=False):
    candidates_bold = [
        r"C:\Windows\Fonts\NotoSans-Bold.ttf",
        r"C:\Windows\Fonts\NotoSans_Condensed-Bold.ttf",
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
        "/Library/Fonts/NotoSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    ]
    candidates_reg = [
        r"C:\Windows\Fonts\NotoSans-Regular.ttf",
        r"C:\Windows\Fonts\NotoSans_Condensed-Regular.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
        "/Library/Fonts/NotoSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf",
    ]
    candidates = candidates_bold if bold else candidates_reg
    for path in candidates:
        if os.path.exists(path):
            return path
    try:
        import matplotlib.font_manager as fm
        fp = fm.findfont(fm.FontProperties(family="DejaVu Sans", weight="bold" if bold else "regular"))
        if fp and os.path.exists(fp):
            return fp
    except Exception:
        pass
    raise FileNotFoundError(
        "Could not find a suitable font with ₹ support.\n"
        "Please install Noto Sans: https://fonts.google.com/noto/specimen/Noto+Sans\n"
        "and place NotoSans-Regular.ttf / NotoSans-Bold.ttf in C:\\Windows\\Fonts\\"
    )

_BOLD_PATH = _find_font(bold=True)
_REG_PATH  = _find_font(bold=False)
print(f"Using fonts:\n  Regular: {_REG_PATH}\n  Bold:    {_BOLD_PATH}")

def _f(size, bold=False):
    path = _BOLD_PATH if bold else _REG_PATH
    return ImageFont.truetype(path, size)

# Font sizes — unchanged from original
F_EYEBROW  = _f(25)
F_HERO     = _f(85, bold=True)
F_PILL_LBL = _f(25)
F_KPI_LBL  = _f(25)
F_KPI_VAL  = _f(70, bold=True)
F_SEC_TITLE= _f(34, bold=True)
F_SEC_SUB  = _f(25)
F_CARD_LBL = _f(25)
F_CARD_VAL = _f(65, bold=True)
F_STAT_LBL = _f(25)
F_STAT_VAL = _f(30, bold=True)
F_TBL_HDR  = _f(25, bold=True)
F_TBL_RANK = _f(32)
F_TBL_NAME = _f(35, bold=True)
F_TBL_NUM  = _f(32, bold=True)
F_TBL_BODY = _f(32)
F_TBL_GROSS= _f(32, bold=True)
F_OCC_PCT  = _f(32)
F_FOOTER   = _f(25)

# ── HELPERS ───────────────────────────────────────────────────────────────────
def tw(draw, text, font, stroke=0):
    bb = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return bb[2] - bb[0]

def th_font(draw, font, stroke=0):
    bb = draw.textbbox((0, 0), "Ag", font=font, stroke_width=stroke)
    return bb[3] - bb[1]

def draw_text_c(draw, cx, y, text, font, color, stroke=0):
    x = int(cx - tw(draw, text, font, stroke) / 2)
    if stroke > 0:
        draw.text((x, y), text, font=font, fill=color, stroke_width=stroke, stroke_fill=color)
    else:
        draw.text((x, y), text, font=font, fill=color)

def tbold(draw, xy, text, font, fill, stroke=1):
    draw.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=fill)

def rr(draw, x1, y1, x2, y2, r=8, fill=None, outline=None, width=1):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill, outline=outline, width=width)

def fmt(v):
    if v >= 10_000_000: return f"\u20b9{v/10_000_000:.2f} Cr"
    if v >= 100_000:    return f"\u20b9{v/100_000:.2f} L"
    if v >= 1_000:      return f"\u20b9{v/1_000:.1f} K"
    return f"\u20b9{v:.0f}"

def occ_col(o):
    if o >= 60: return GREEN
    if o >= 50: return ORANGE
    if o >= 30: return YELLOW
    return RED_OCC

# ── AGGREGATE ─────────────────────────────────────────────────────────────────
def aggregate(all_results):
    state_stats, city_stats = {}, {}
    for r in all_results:
        state = r.get("state", "Unknown")
        city  = r.get("city",  "Unknown")
        venue = r["venue"]
        g = r["booked_gross"]; t = r["booked_tickets"]; s = r["total_tickets"]
        if state not in state_stats:
            state_stats[state] = {"name": state, "gross":0,"tickets":0,"seats":0,"shows":0,"venues":set()}
        ss = state_stats[state]
        ss["gross"]+=g; ss["tickets"]+=t; ss["seats"]+=s; ss["shows"]+=1; ss["venues"].add(venue)
        ck = (state, city)
        if ck not in city_stats:
            city_stats[ck] = {"city":city,"state":state,"gross":0,"tickets":0,"seats":0,"shows":0,"venues":set()}
        cs = city_stats[ck]
        cs["gross"]+=g; cs["tickets"]+=t; cs["seats"]+=s; cs["shows"]+=1; cs["venues"].add(venue)

    def build(d):
        out = []
        for v in d.values():
            occ = round((v["tickets"]/v["seats"])*100, 1) if v["seats"] else 0
            row = {k:(len(vv) if isinstance(vv, set) else vv) for k, vv in v.items()}
            row["occupancy"] = occ
            out.append(row)
        out.sort(key=lambda x: x["gross"], reverse=True)
        return out
    return build(state_stats), build(city_stats)

# ── WATERMARK ─────────────────────────────────────────────────────────────────
def apply_watermark(img):
    wfont = _f(80, bold=True)
    tmp = Image.new("RGBA", (1,1))
    td  = ImageDraw.Draw(tmp)
    bb  = td.textbbox((0,0), WATERMARK_TEXT, font=wfont)
    tw_, th_ = bb[2]-bb[0]+4, bb[3]-bb[1]+4
    tile_w, tile_h = tw_+120, th_+100
    tile = Image.new("RGBA", (tile_w, tile_h), (0,0,0,0))
    td2  = ImageDraw.Draw(tile)
    td2.text(((tile_w-tw_)//2, (tile_h-th_)//2), WATERMARK_TEXT,
             font=wfont, fill=(255,255,255, WATERMARK_OPACITY))
    rotated = tile.rotate(WATERMARK_ANGLE, expand=True)
    rw, rh  = rotated.size
    W_, H_  = img.size
    overlay = Image.new("RGBA", (W_, H_), (0,0,0,0))
    for yy in range(-rh, H_+rh, rh):
        for xx in range(-rw, W_+rw, rw):
            overlay.paste(rotated, (xx, yy), rotated)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

# ── TABLE ─────────────────────────────────────────────────────────────────────
def draw_table(draw, y, headers, rows, col_widths, alignments, col_x_start):
    TW     = W - PAD*2
    tx     = col_x_start
    HEAD_H = 62
    ROW_H  = 88

    # Header row
    draw.rectangle([tx, y, tx+TW, y+HEAD_H], fill=SURFACE2)
    cx = tx
    for hdr, cw, al in zip(headers, col_widths, alignments):
        hdr_w = tw(draw, hdr, F_TBL_HDR)
        ty_hdr = y + (HEAD_H - th_font(draw, F_TBL_HDR)) // 2
        if al == 'R':
            draw.text((cx+cw-hdr_w-8, ty_hdr), hdr, font=F_TBL_HDR, fill=MUTED)
        elif al == 'C':
            draw.text((cx+(cw-hdr_w)//2, ty_hdr), hdr, font=F_TBL_HDR, fill=MUTED)
        else:
            draw.text((cx+8, ty_hdr), hdr, font=F_TBL_HDR, fill=MUTED)
        cx += cw
    y += HEAD_H

    # Data rows
    for ri, row in enumerate(rows):
        row_bg = SURFACE if ri % 2 == 0 else BG
        draw.rectangle([tx, y, tx+TW, y+ROW_H], fill=row_bg)
        cx = tx
        mid_y = y + ROW_H // 2

        for ci, (cell, cw, al) in enumerate(zip(row, col_widths, alignments)):
            if isinstance(cell, dict) and cell.get("type") == "occ_bar":
                occ_val = cell["value"]
                o_col   = occ_col(occ_val)
                occ_str = f"{occ_val}%"
                bar_x  = cx + 8
                bar_w  = 90          # ← wider bar to use extra column space
                bar_h  = 12
                bar_y  = mid_y - bar_h // 2
                fill_w = max(2, int(bar_w * occ_val / 100))
                rr(draw, bar_x, bar_y, bar_x+bar_w, bar_y+bar_h, 6, fill=SURFACE2)
                rr(draw, bar_x, bar_y, bar_x+fill_w, bar_y+bar_h, 6, fill=o_col)
                pct_w = tw(draw, occ_str, F_OCC_PCT)
                pct_x = cx + cw - pct_w - 8
                pct_y = mid_y - th_font(draw, F_OCC_PCT)//2
                draw.text((pct_x, pct_y), occ_str, font=F_OCC_PCT, fill=o_col)
            else:
                cell_str = str(cell)
                is_rank  = ci == 0
                is_name  = ci == 1
                is_gross = ci == len(row) - 1

                if is_rank:
                    font  = F_TBL_RANK;  color = MUTED;   stroke = 0
                elif is_name:
                    font  = F_TBL_NAME;  color = TEXT;    stroke = 0
                elif is_gross:
                    font  = F_TBL_GROSS; color = ACCENT;  stroke = 0
                else:
                    font  = F_TBL_NUM;   color = TEXT;    stroke = 0

                max_w = cw - 16
                while len(cell_str) > 1 and tw(draw, cell_str, font) > max_w:
                    cell_str = cell_str[:-1]

                cw_t = tw(draw, cell_str, font)
                cy_t = mid_y - th_font(draw, font) // 2

                if al == 'R':
                    draw.text((cx+cw-cw_t-8, cy_t), cell_str, font=font, fill=color)
                elif al == 'C':
                    draw.text((cx+(cw-cw_t)//2, cy_t), cell_str, font=font, fill=color)
                else:
                    draw.text((cx+8, cy_t), cell_str, font=font, fill=color)

            cx += cw

        draw.line([(tx, y+ROW_H), (tx+TW, y+ROW_H)], fill=BORDER, width=1)
        y += ROW_H

    rr(draw, tx, y - ROW_H*len(rows) - HEAD_H, tx+TW, y, 8, outline=BORDER, width=1)
    return y + 32

# ── MAIN GENERATOR ────────────────────────────────────────────────────────────
def generate_premium_states_image_report(all_results, output_path,
                                          movie_name="Movie Collection",
                                          show_date=None):
    if show_date is None:
        show_date = datetime.now().strftime("%d %b %Y")

    TOP_ROWS = 10
    state_list, city_list = aggregate(all_results)

    total_gross   = sum(r["booked_gross"]   for r in all_results)
    total_tickets = sum(r["booked_tickets"] for r in all_results)
    total_seats   = sum(r["total_tickets"]  for r in all_results)
    total_occ     = round((total_tickets/total_seats)*100, 1) if total_seats else 0
    num_states    = len(state_list)
    num_venues    = len(set(r["venue"] for r in all_results))
    num_shows     = len(all_results)

    src_gross_bms    = sum(r["booked_gross"]   for r in all_results if r.get("source")=="bms")
    src_gross_dist   = sum(r["booked_gross"]   for r in all_results if r.get("source")=="district")
    src_tickets_bms  = sum(r["booked_tickets"] for r in all_results if r.get("source")=="bms")
    src_tickets_dist = sum(r["booked_tickets"] for r in all_results if r.get("source")=="district")
    src_shows_bms    = sum(1 for r in all_results if r.get("source")=="bms")
    src_shows_dist   = sum(1 for r in all_results if r.get("source")=="district")

    # ── TABLE COLUMN DEFINITIONS — recalculated for wider canvas ─────────────
    TW     = W - PAD * 2   # 1280 - 112 = 1168px
    # Fixed cols: rank(60) vens(80) shows(90) tickets(120) occ(220) gross(175)
    fixed  = 68 + 100 + 112 + 140 + 235 + 190
    name_w = TW - fixed    # remaining space goes to name column
    col_widths  = [68, name_w, 100, 112, 140, 235, 190]
    col_headers = ["#", "STATE", "VENS", "SHOWS", "TICKETS", "OCCUPANCY", "GROSS"]
    col_aligns  = ["C", "L",    "R",    "R",      "R",       "L",          "R"]

    def render(canvas_h):
        img  = Image.new("RGB", (W, canvas_h), BG)
        draw = ImageDraw.Draw(img)
        y    = 0

        # ── HERO ─────────────────────────────────────────────────────────────
        hero_h_approx = 280
        for gy in range(hero_h_approx):
            t = gy / hero_h_approx
            draw.line([(0, gy), (W, gy)], fill=(int(11+t*5), int(10+t*2), int(15+t*18)))

        draw.text((PAD, 18), "STATE-WISE BOX OFFICE REPORT", font=F_EYEBROW, fill=ACCENT)

        title_font = F_HERO
        words = movie_name.upper().split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if tw(draw, test, title_font, stroke=1) <= W - PAD*2:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)

        line_h = th_font(draw, title_font, stroke=1) + 6
        ty = 44
        for line in lines:
            draw.text((PAD+2, ty+2), line, font=title_font, fill=(20, 18, 28), stroke_width=1, stroke_fill=(20,18,28))
            tbold(draw, (PAD, ty), line, title_font, TEXT, stroke=1)
            ty += line_h
        title_end = ty + 20

        PILL_H = 40
        PILL_R = 7
        pill_items = [show_date, f"{num_states} States", f"{num_venues} Theatres", f"{num_shows} Shows"]
        mx = PAD
        for label in pill_items:
            pw = tw(draw, label, F_PILL_LBL) + 28
            rr(draw, mx, title_end, mx+pw, title_end+PILL_H, PILL_R, fill=SURFACE2)
            lbl_y = title_end + (PILL_H - th_font(draw, F_PILL_LBL)) // 2
            draw.text((mx+14, lbl_y), label, font=F_PILL_LBL, fill=MUTED)
            mx += pw + 10

        hero_h = title_end + PILL_H + 30
        y = hero_h

        # ── KPI STRIP ────────────────────────────────────────────────────────
        KPI_ROW_H = 170
        kpis = [
            ("TOTAL GROSS",   fmt(total_gross),      ACCENT),
            ("TICKETS SOLD",  f"{total_tickets:,}",  ACCENT),
            ("STATES",        str(num_states),        ACCENT),
            ("THEATRES",      str(num_venues),         ACCENT),
            ("AVG OCCUPANCY", f"{total_occ}%",        occ_col(total_occ)),
            ("TOTAL SHOWS",   str(num_shows),          ACCENT),
        ]
        COLS   = 3
        cell_w = W // COLS

        for i, (label, val, col) in enumerate(kpis):
            ci = i % COLS; ri = i // COLS
            kx = ci * cell_w; ky = y + ri * KPI_ROW_H
            draw.rectangle([kx, ky, kx+cell_w, ky+KPI_ROW_H], fill=SURFACE, outline=BORDER)
            lw = tw(draw, label, F_KPI_LBL)
            draw.text((kx + cell_w//2 - lw//2, ky+26), label, font=F_KPI_LBL, fill=MUTED)
            vw = tw(draw, val, F_KPI_VAL, stroke=1)
            tbold(draw, (kx + cell_w//2 - vw//2, ky+60), val, F_KPI_VAL, col, stroke=1)

        y += KPI_ROW_H * 2
        draw.line([(0, y), (W, y)], fill=BORDER, width=1)
        y += 40

        # ── PLATFORM BREAKDOWN ───────────────────────────────────────────────
        sec_y = y
        tbold(draw, (PAD, sec_y), "PLATFORM BREAKDOWN", F_SEC_TITLE, TEXT, stroke=1)
        sub_x   = PAD + tw(draw, "PLATFORM BREAKDOWN", F_SEC_TITLE, stroke=1) + 18
        sub_off = (th_font(draw, F_SEC_TITLE) - th_font(draw, F_SEC_SUB)) // 2
        draw.text((sub_x, sec_y+sub_off+2), "BMS VS DISTRICT", font=F_SEC_SUB, fill=MUTED)
        y = sec_y + th_font(draw, F_SEC_TITLE, stroke=1) + 16
        draw.line([(PAD, y), (W-PAD, y)], fill=BORDER, width=1)
        y += 22

        CARD_H   = 260
        CARD_GAP = 22
        card_w   = (W - PAD*2 - CARD_GAP) // 2

        for pi, (name, gross_v, tickets_v, shows_v, bar_col) in enumerate([
            ("BOOKMYSHOW",   src_gross_bms,  src_tickets_bms,  src_shows_bms,  BMS_C),
            ("DISTRICT APP", src_gross_dist, src_tickets_dist, src_shows_dist, DST_C),
        ]):
            cx = PAD + pi*(card_w+CARD_GAP); cy = y
            rr(draw, cx, cy, cx+card_w, cy+CARD_H, 10, fill=SURFACE, outline=BORDER, width=1)
            rr(draw, cx+1, cy+1, cx+card_w-1, cy+5, 10, fill=bar_col)
            draw.rectangle([cx+1, cy+3, cx+card_w-1, cy+5], fill=bar_col)
            draw.text((cx+24, cy+18), name, font=F_CARD_LBL, fill=MUTED)
            tbold(draw, (cx+24, cy+46), fmt(gross_v), F_CARD_VAL, bar_col, stroke=1)
            stats = [("Shows", str(shows_v)), ("Tickets", f"{tickets_v:,}"),
                     ("% Share", f"{round((gross_v/total_gross)*100,1) if total_gross else 0}%")]
            stat_w = (card_w - 48) // 3
            for si, (sl, sv) in enumerate(stats):
                sx = cx + 24 + si*stat_w
                draw.text((sx, cy+172), sl, font=F_STAT_LBL, fill=MUTED)
                tbold(draw, (sx, cy+200), sv, F_STAT_VAL, TEXT, stroke=1)

        y += CARD_H + 42

        # ── STATE RANKINGS TABLE ─────────────────────────────────────────────
        sec_y = y
        tbold(draw, (PAD, sec_y), "STATE RANKINGS", F_SEC_TITLE, TEXT, stroke=1)
        sub_x   = PAD + tw(draw, "STATE RANKINGS", F_SEC_TITLE, stroke=1) + 18
        sub_off = (th_font(draw, F_SEC_TITLE) - th_font(draw, F_SEC_SUB)) // 2
        draw.text((sub_x, sec_y+sub_off+2), "BY GROSS COLLECTION", font=F_SEC_SUB, fill=MUTED)
        y = sec_y + th_font(draw, F_SEC_TITLE, stroke=1) + 16
        draw.line([(PAD, y), (W-PAD, y)], fill=BORDER, width=1)
        y += 18

        state_rows = []
        for i, s in enumerate(state_list[:TOP_ROWS], 1):
            state_rows.append([str(i), s["name"], str(s["venues"]), str(s["shows"]),
                                f"{s['tickets']:,}", {"type":"occ_bar","value":s["occupancy"]}, fmt(s["gross"])])
        y = draw_table(draw, y, col_headers, state_rows, col_widths, col_aligns, PAD)

        # ── CITY RANKINGS TABLE ──────────────────────────────────────────────
        sec_y = y
        tbold(draw, (PAD, sec_y), "CITY RANKINGS", F_SEC_TITLE, TEXT, stroke=1)
        sub_x   = PAD + tw(draw, "CITY RANKINGS", F_SEC_TITLE, stroke=1) + 18
        sub_off = (th_font(draw, F_SEC_TITLE) - th_font(draw, F_SEC_SUB)) // 2
        draw.text((sub_x, sec_y+sub_off+2), "TOP 10 \u00b7 BY GROSS", font=F_SEC_SUB, fill=MUTED)
        y = sec_y + th_font(draw, F_SEC_TITLE, stroke=1) + 16
        draw.line([(PAD, y), (W-PAD, y)], fill=BORDER, width=1)
        y += 18

        city_col_headers = ["#", "CITY", "VENS", "SHOWS", "TICKETS", "OCCUPANCY", "GROSS"]
        city_rows = []
        for i, c in enumerate(city_list[:TOP_ROWS], 1):
            city_rows.append([str(i), c["city"], str(c["venues"]), str(c["shows"]),
                               f"{c['tickets']:,}", {"type":"occ_bar","value":c["occupancy"]}, fmt(c["gross"])])
        y = draw_table(draw, y, city_col_headers, city_rows, col_widths, col_aligns, PAD)

        # ── FOOTER ───────────────────────────────────────────────────────────
        y += 10
        FOOT_H = 95
        draw.rectangle([0, y, W, y+FOOT_H], fill=SURFACE)
        f1 = "Generated by CinePulseBO \u00b7  Data: BookMyShow & District"
        f2 = datetime.now().strftime("%d %b %Y, %I:%M %p")
        draw_text_c(draw, W//2, y+18, f1, F_FOOTER, MUTED)
        draw_text_c(draw, W//2, y+50, f2, F_FOOTER, MUTED)
        y += FOOT_H

        return img, y

    _, est_h = render(9000)
    img, _   = render(est_h + 10)
    img = img.crop((0, 0, W, est_h + 10))
    if WATERMARK_ENABLED:
        img = apply_watermark(img)
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    print(f"✅ Saved: {output_path}  ({W}×{est_h+10}px)")
    return output_path


# ── DEMO ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import random
    states_cities = {
        "Telangana":      ["Hyderabad", "Warangal", "Karimnagar"],
        "Andhra Pradesh": ["Vijayawada", "Visakhapatnam", "Tirupati", "Guntur"],
        "Tamil Nadu":     ["Chennai", "Coimbatore", "Madurai"],
        "Karnataka":      ["Bengaluru", "Mysuru", "Mangaluru"],
        "Kerala":         ["Kochi", "Thiruvananthapuram", "Kozhikode"],
    }
    venues_by_city = {
        "Hyderabad":     ["AMB Cinemas", "PVR IMAX Inorbit", "Cinepolis Kukatpally", "Asian Mukta A2"],
        "Vijayawada":    ["PVR CinemaS", "SVC Cinemas", "Imax Cinemas"],
        "Chennai":       ["PVR SPI Palazzo", "INOX Chennai", "AGS Cinemas"],
        "Bengaluru":     ["PVR Orion", "INOX Garuda", "Cinepolis HSR"],
        "Kochi":         ["PVR LuLu", "INOX Oberon", "PVR Gold"],
        "Warangal":      ["Sri Mayuri Theatre", "Vinayaka Cinemas"],
        "Coimbatore":    ["INOX Brookefields", "Cinepolis Fun Mall"],
        "Mysuru":        ["PVR Forum", "Cinepolis Mysuru Mall"],
        "Thiruvananthapuram": ["PVR Kims", "INOX TVM"],
        "Tirupati":      ["Sri Devi Theatre", "Nagaland Complex"],
        "Guntur":        ["Sri Ram Cinemas", "PVR Guntur"],
        "Karimnagar":    ["Vaishnavi Theatre", "MGM Complex"],
        "Visakhapatnam": ["PVR CMR", "INOX Vizag", "Cinepolis Rushikonda"],
        "Madurai":       ["Inox Madurai", "AGS Cinemas Madurai"],
        "Mangaluru":     ["PVR Forum", "INOX Mangaluru"],
        "Kozhikode":     ["PVR Kozhikode", "INOX Kozhikode"],
    }
    random.seed(42)
    sample_data = []
    for state, cities in states_cities.items():
        for city in cities:
            venues = venues_by_city.get(city, [f"{city} Cinema 1", f"{city} Cinema 2"])
            for venue in venues:
                for _ in range(random.randint(2, 6)):
                    total  = random.choice([150, 200, 250, 300, 400])
                    booked = random.randint(int(total*0.25), total)
                    price  = random.choice([180, 200, 250, 300, 350, 400])
                    source = random.choice(["bms", "district"])
                    sample_data.append({
                        "state": state, "city": city, "venue": venue,
                        "booked_tickets": booked, "total_tickets": total,
                        "booked_gross": booked*price, "source": source,
                    })
    generate_premium_states_image_report(
        sample_data,
        output_path="box_office_report.png",
        movie_name="KALKI 2898 AD",
        show_date="16 Mar 2025"
    )