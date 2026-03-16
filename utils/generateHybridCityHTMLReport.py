"""
Multi-City HTML Report Generator - Premium Design
Updated to support multiple cities with city rankings + cross-city theatre rankings.
"""

import json
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from collections import defaultdict


def parse_metadata(url):
    try:
        parsed     = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        movie_name = "Movie Collection"
        show_date  = datetime.now().strftime("%d %b %Y")

        if "movies" in path_parts:
            for p in path_parts:
                if "-movie-tickets-in-" in p:
                    movie_name = p.split("-movie-tickets-in-")[0].replace("-", " ").title()
                    break
            q = parse_qs(parsed.query)
            if 'fromdate' in q:
                show_date = datetime.strptime(q['fromdate'][0], "%Y-%m-%d").strftime("%d %b %Y")
        elif "buytickets" in path_parts:
            idx = path_parts.index("buytickets")
            if idx >= 1:
                movie_name = path_parts[idx - 1].replace("-", " ").title()
            try:
                show_date = datetime.strptime(path_parts[-1], "%Y%m%d").strftime("%d %b %Y")
            except: pass

        return movie_name, show_date
    except:
        return "Movie Collection", datetime.now().strftime("%d %b %Y")


def format_currency(value):
    if value >= 10_000_000: return f"₹{value/10_000_000:.2f} Cr"
    if value >= 100_000:    return f"₹{value/100_000:.2f} L"
    if value >= 1_000:      return f"₹{value/1_000:.1f} K"
    return f"₹{value:.0f}"

def get_occupancy_color(occ):
    if occ >= 60:   return "#00c853"
    elif occ >= 50: return "#ff6d00"
    elif occ >= 30: return "#ffd600"
    return "#ff1744"


def generate_hybrid_city_html_report(all_results, ref_url, output_path,
                                      movie_name=None, show_date=None):
    print("🎨 Generating Premium Multi-City HTML Report...")

    parsed_movie, parsed_date = parse_metadata(ref_url)
    if not movie_name: movie_name = parsed_movie
    if not show_date:  show_date  = parsed_date

    # ── Aggregate by city ────────────────────────────────────────────────────
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
         "occ": round((d["tickets"]/d["seats"])*100, 1) if d["seats"] else 0}
        for c, d in city_map.items()
    ], key=lambda x: x["gross"], reverse=True)

    # ── Aggregate by venue (across all cities) ────────────────────────────────
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
         "occ": round((d["tickets"]/d["seats"])*100, 1) if d["seats"] else 0}
        for v, d in venue_map.items()
    ], key=lambda x: x["gross"], reverse=True)

    # ── Totals ────────────────────────────────────────────────────────────────
    total_gross   = sum(r["booked_gross"]   for r in all_results)
    total_tickets = sum(r["booked_tickets"] for r in all_results)
    total_seats   = sum(r["total_tickets"]  for r in all_results)
    total_occ     = round((total_tickets/total_seats)*100, 1) if total_seats else 0
    num_shows     = len(all_results)
    num_cities    = len(city_list)
    num_theatres  = len(venue_list)

    src_gross_bms    = sum(r["booked_gross"]   for r in all_results if r.get("source")=="bms")
    src_gross_dist   = sum(r["booked_gross"]   for r in all_results if r.get("source")=="district")
    src_tickets_bms  = sum(r["booked_tickets"] for r in all_results if r.get("source")=="bms")
    src_tickets_dist = sum(r["booked_tickets"] for r in all_results if r.get("source")=="district")
    src_shows_bms    = sum(1 for r in all_results if r.get("source")=="bms")
    src_shows_dist   = sum(1 for r in all_results if r.get("source")=="district")

    total_occ_color = get_occupancy_color(total_occ)

    # ── City ranking rows ─────────────────────────────────────────────────────
    city_rows_html = ""
    for idx, c in enumerate(city_list, 1):
        oc = get_occupancy_color(c["occ"])
        city_rows_html += f"""
        <tr>
            <td class="rank">{idx}</td>
            <td><strong>{c['name']}</strong></td>
            <td class="num">{c['venues']}</td>
            <td class="num">{c['shows']}</td>
            <td class="num">{c['tickets']:,}</td>
            <td class="num">
                <div class="occ-bar-wrap">
                    <div class="occ-bar" style="width:{c['occ']}%;background:{oc}"></div>
                    <span style="color:{oc}">{c['occ']}%</span>
                </div>
            </td>
            <td class="num gross-cell">{format_currency(c['gross'])}</td>
        </tr>"""

    # ── Theatre ranking rows ──────────────────────────────────────────────────
    theatre_rows_html = ""
    for idx, v in enumerate(venue_list, 1):
        oc = get_occupancy_color(v["occ"])
        hidden = ' class="hidden-row"' if idx > 20 else ''
        theatre_rows_html += f"""
        <tr{hidden}>
            <td class="rank">{idx}</td>
            <td><strong>{v['city']}</strong></td>
            <td><div class="theatre-name">{v['name']}</div></td>
            <td class="num">{v['shows']}</td>
            <td class="num">{v['tickets']:,}/{v['seats']:,}</td>
            <td class="num">
                <div class="occ-bar-wrap">
                    <div class="occ-bar" style="width:{v['occ']}%;background:{oc}"></div>
                    <span style="color:{oc}">{v['occ']}%</span>
                </div>
            </td>
            <td class="num gross-cell">{format_currency(v['gross'])}</td>
        </tr>"""

    # ── Platform cards ────────────────────────────────────────────────────────
    platform_html = f"""
    <div class="platform-card bms-card">
        <div class="platform-name">BookMyShow</div>
        <div class="platform-gross">{format_currency(src_gross_bms)}</div>
        <div class="platform-stats">
            <div><div class="pstat-label">Shows</div><div class="pstat-value">{src_shows_bms}</div></div>
            <div><div class="pstat-label">Tickets</div><div class="pstat-value">{src_tickets_bms:,}</div></div>
            <div><div class="pstat-label">% Share</div><div class="pstat-value">{round((src_gross_bms/total_gross)*100,1) if total_gross else 0}%</div></div>
        </div>
    </div>
    <div class="platform-card dst-card">
        <div class="platform-name">District App</div>
        <div class="platform-gross">{format_currency(src_gross_dist)}</div>
        <div class="platform-stats">
            <div><div class="pstat-label">Shows</div><div class="pstat-value">{src_shows_dist}</div></div>
            <div><div class="pstat-label">Tickets</div><div class="pstat-value">{src_tickets_dist:,}</div></div>
            <div><div class="pstat-label">% Share</div><div class="pstat-value">{round((src_gross_dist/total_gross)*100,1) if total_gross else 0}%</div></div>
        </div>
    </div>"""

    show_toggle = f'<div class="toggle-container"><button class="show-all-btn" onclick="toggleRows(\'theatreTable\')">🎪 Show All {num_theatres} Theatres</button></div>' if num_theatres > 20 else ''

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{movie_name} — Multi-City Box Office Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg:#0a0a0f; --surface:#13131c; --surface2:#1c1c2a; --border:#2a2a3d;
            --accent:#f5a623; --accent2:#e8174d; --text:#e8e8f0; --muted:#7070a0;
            --bms:#e8174d; --district:#9B4BE1;
        }}
        *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
        body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}}

        .hero{{background:linear-gradient(135deg,#0d0d1a 0%,#1a0a20 50%,#0a1020 100%);border-bottom:1px solid var(--border);padding:48px 40px 36px;position:relative;overflow:hidden}}
        .hero::before{{content:'';position:absolute;top:-60px;right:-60px;width:320px;height:320px;background:radial-gradient(circle,rgba(245,166,35,0.12) 0%,transparent 70%);pointer-events:none}}
        .hero::after{{content:'';position:absolute;bottom:-80px;left:20%;width:400px;height:200px;background:radial-gradient(circle,rgba(232,23,77,0.08) 0%,transparent 70%);pointer-events:none}}
        .hero-eyebrow{{font-size:11px;letter-spacing:3px;text-transform:uppercase;color:var(--accent);margin-bottom:10px;font-weight:600}}
        .hero-title{{font-family:'Bebas Neue',sans-serif;font-size:clamp(42px,7vw,80px);letter-spacing:2px;line-height:0.95;background:linear-gradient(135deg,#fff 30%,var(--accent) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:12px}}
        .hero-meta{{display:flex;gap:16px;flex-wrap:wrap;margin-top:16px;color:var(--muted);font-size:13px}}
        .hero-meta span{{display:flex;align-items:center;gap:6px}}
        .hero-meta strong{{color:var(--text)}}

        .kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;background:var(--border);border-bottom:1px solid var(--border)}}
        .kpi-card{{background:var(--surface);padding:28px 24px;text-align:center}}
        .kpi-label{{font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:var(--muted);margin-bottom:8px;font-weight:600}}
        .kpi-value{{font-family:'Bebas Neue',sans-serif;font-size:36px;letter-spacing:1px;color:var(--accent)}}
        .kpi-card.total .kpi-value{{background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-size:44px}}

        .main{{padding:32px 40px;max-width:1400px;margin:0 auto}}
        .section{{margin-bottom:48px}}
        .section-header{{display:flex;align-items:baseline;gap:12px;margin-bottom:20px;padding-bottom:12px;border-bottom:1px solid var(--border)}}
        .section-title{{font-family:'Bebas Neue',sans-serif;font-size:24px;letter-spacing:1.5px;color:var(--text)}}
        .section-sub{{font-size:12px;color:var(--muted);letter-spacing:1px;text-transform:uppercase}}

        .platform-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
        .platform-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;position:relative;overflow:hidden;transition:transform 0.2s}}
        .platform-card:hover{{transform:translateY(-2px)}}
        .platform-card.bms-card{{border-top:3px solid var(--bms)}}
        .platform-card.dst-card{{border-top:3px solid var(--district)}}
        .platform-card::before{{content:'';position:absolute;top:0;right:0;width:120px;height:120px;border-radius:50%;opacity:0.06}}
        .bms-card::before{{background:var(--bms)}} .dst-card::before{{background:var(--district)}}
        .platform-name{{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:4px}}
        .platform-gross{{font-family:'Bebas Neue',sans-serif;font-size:36px;letter-spacing:1px;margin-bottom:16px}}
        .bms-card .platform-gross{{color:var(--bms)}} .dst-card .platform-gross{{color:var(--district)}}
        .platform-stats{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
        .pstat-label{{font-size:10px;color:var(--muted);text-transform:uppercase}}
        .pstat-value{{font-size:18px;font-weight:700;color:var(--text)}}

        .table-wrap{{overflow-x:auto;border:1px solid var(--border);border-radius:12px}}
        table{{width:100%;border-collapse:collapse;font-size:13.5px}}
        thead th{{background:var(--surface2);color:var(--muted);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;font-weight:600;padding:12px 16px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--border)}}
        #cityTable thead th:nth-child(3),#cityTable thead th:nth-child(4),
        #cityTable thead th:nth-child(5),#cityTable thead th:nth-child(6),
        #cityTable thead th:nth-child(7){{text-align:right}}
        #theatreTable thead th:nth-child(4),#theatreTable thead th:nth-child(5),
        #theatreTable thead th:nth-child(6),#theatreTable thead th:nth-child(7){{text-align:right}}
        tbody tr{{border-bottom:1px solid var(--border);transition:background 0.15s}}
        tbody tr:hover{{background:var(--surface2)}}
        td{{padding:12px 16px;vertical-align:middle}}
        td.num{{text-align:right;font-variant-numeric:tabular-nums}}
        td.gross-cell{{font-weight:700;color:var(--accent)}}
        td.rank{{color:var(--muted);font-size:12px;width:40px}}
        .theatre-name{{font-weight:600;color:var(--text)}}

        .occ-bar-wrap{{display:flex;align-items:center;gap:8px;justify-content:flex-end}}
        .occ-bar{{height:6px;border-radius:3px;max-width:70px;width:70px;flex-shrink:0;order:-1}}
        .occ-bar-wrap span{{font-weight:700;font-size:13px;width:42px;text-align:right}}

        .hidden-row{{display:none}}
        .show-all-btn{{display:inline-block;margin-top:16px;padding:8px 16px;background:var(--surface2);color:var(--accent);border:1px solid var(--accent);border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;letter-spacing:0.5px;transition:all 0.2s}}
        .show-all-btn:hover{{background:var(--accent);color:var(--bg)}}
        .toggle-container{{text-align:center;padding:20px}}

        .footer{{text-align:center;padding:32px 40px;color:var(--muted);font-size:12px;border-top:1px solid var(--border)}}
        .footer strong{{color:var(--accent)}}

        @media(max-width:768px){{.hero{{padding:32px 20px}}.main{{padding:20px}}table{{font-size:12px}}td{{padding:8px}}}}
        ::-webkit-scrollbar{{width:6px;height:6px}}
        ::-webkit-scrollbar-track{{background:var(--bg)}}
        ::-webkit-scrollbar-thumb{{background:var(--border)}}
    </style>
</head>
<body>

<header class="hero">
    <div class="hero-eyebrow">📽 Multi-City Box Office Report</div>
    <div class="hero-title">{movie_name}</div>
    <div class="hero-meta">
        <span>📅 <strong>{show_date}</strong></span>
        <span>🕐 Generated: <strong>{datetime.now().strftime("%d %b %Y, %I:%M %p")}</strong></span>
        <span>🗺️ <strong>{num_cities} Cities</strong></span>
        <span>🎪 <strong>{num_theatres} Theatres</strong></span>
        <span>🎬 <strong>{num_shows} Shows</strong></span>
    </div>
</header>

<div class="kpi-strip">
    <div class="kpi-card total">
        <div class="kpi-label">Total Gross Collection</div>
        <div class="kpi-value">{format_currency(total_gross)}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Tickets Sold</div>
        <div class="kpi-value">{total_tickets:,}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Cities</div>
        <div class="kpi-value">{num_cities}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Theatres</div>
        <div class="kpi-value">{num_theatres}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Avg Occupancy</div>
        <div class="kpi-value" style="color:{total_occ_color}">{total_occ}%</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Total Shows</div>
        <div class="kpi-value">{num_shows}</div>
    </div>
</div>

<main class="main">

    <section class="section">
        <div class="section-header">
            <div class="section-title">Platform Breakdown</div>
            <div class="section-sub">BMS vs District</div>
        </div>
        <div class="platform-grid">{platform_html}</div>
    </section>

    <section class="section">
        <div class="section-header">
            <div class="section-title">City Rankings</div>
            <div class="section-sub">By Gross Collection</div>
        </div>
        <div class="table-wrap">
            <table id="cityTable">
                <thead>
                    <tr>
                        <th>#</th><th>City</th><th>Theatres</th><th>Shows</th>
                        <th>Tickets Sold</th><th>Occupancy</th><th>Gross</th>
                    </tr>
                </thead>
                <tbody>{city_rows_html}</tbody>
            </table>
        </div>
    </section>

    <section class="section">
        <div class="section-header">
            <div class="section-title">Theatre Rankings</div>
            <div class="section-sub">All Cities · By Gross Collection</div>
        </div>
        <div class="table-wrap">
            <table id="theatreTable">
                <thead>
                    <tr>
                        <th>#</th><th>City</th><th>Theatre</th><th>Shows</th>
                        <th>Seats (Sold/Total)</th><th>Occupancy</th><th>Gross</th>
                    </tr>
                </thead>
                <tbody>{theatre_rows_html}</tbody>
            </table>
        </div>
        {show_toggle}
    </section>

</main>

<footer class="footer">
    Generated by <strong>CinePulseBO</strong> &nbsp;·&nbsp;
    Data from BookMyShow &amp; District &nbsp;·&nbsp;
    {datetime.now().strftime("%d %b %Y, %I:%M %p")} &nbsp;·&nbsp;
    For informational purposes only
</footer>

<script>
function toggleRows(tableId) {{
    const table = document.getElementById(tableId);
    const rows  = Array.from(table.querySelectorAll('tbody tr'));
    const btn   = event.target;
    const hasHidden = table.querySelectorAll('tbody tr.hidden-row').length > 0;
    if (hasHidden) {{
        table.querySelectorAll('tbody tr.hidden-row').forEach(r => r.classList.remove('hidden-row'));
        btn.textContent = '🔽 Hide Details';
    }} else {{
        rows.forEach((r, i) => {{ if (i >= 20) r.classList.add('hidden-row'); }});
        btn.textContent = '🎪 Show All ' + rows.length + ' Theatres';
    }}
}}
</script>
</body>
</html>"""

    reports_dir = os.path.dirname(output_path)
    if reports_dir:
        os.makedirs(reports_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"✅ Multi-City HTML Report generated: {output_path}")