"""
Professional HTML Report Generator (State-wise) - Premium Design
Generates beautiful interactive reports matching premium box office standards
"""

import json
import os
from datetime import datetime


def format_currency(value):
    """Format large numbers (Cr = Crores, L = Lakhs, K = Thousands)"""
    if value >= 10000000:
        return f"₹{value/10000000:.2f} Cr"
    elif value >= 100000:
        return f"₹{value/100000:.2f} L"
    elif value >= 1000:
        return f"₹{value/1000:.1f} K"
    else:
        return f"₹{value:.0f}"


def get_occupancy_color(occ):
    """Get color code based on occupancy percentage"""
    if occ >= 60:
        return "#00c853" # Green
    elif occ >= 50:
        return "#ff6d00" # Orange
    elif occ >= 30:
        return "#ffd600" # Yellow
    else:
        return "#ff1744" # Red


def generate_hybrid_states_html_report(all_results, output_path, movie_name="Movie Collection", show_date=None):
    """Generate professional HTML report for state-wise data"""
    
    print("🎨 Generating Premium Multi-State HTML Report...")
    
    if show_date is None:
        show_date = datetime.now().strftime("%d %b %Y")
    
    # --- 1. AGGREGATE BY STATE ---
    state_venue_map = {}
    state_stats = {}
    
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
                "gross": 0, "tickets": 0, "shows": 0, "seats": 0,
                "source_count": {"district": 0, "bms": 0}
            }
        
        state_venue_map[state][venue]["gross"] += r["booked_gross"]
        state_venue_map[state][venue]["tickets"] += r["booked_tickets"]
        state_venue_map[state][venue]["shows"] += 1
        state_venue_map[state][venue]["seats"] += r["total_tickets"]
        
        if source in state_venue_map[state][venue]["source_count"]:
            state_venue_map[state][venue]["source_count"][source] += 1
    
    # State summary list
    state_list = []
    for state, stats in state_stats.items():
        occ = round((stats["tickets"] / stats["seats"]) * 100, 1) if stats["seats"] else 0
        state_list.append({
            "name": state,
            "gross": stats["gross"],
            "tickets": stats["tickets"],
            "shows": stats["shows"],
            "venues": len(stats["venues"]),
            "occupancy": occ,
            "district_shows": stats["source_count"]["district"],
            "bms_shows": stats["source_count"]["bms"]
        })
    
    state_list.sort(key=lambda x: x["gross"], reverse=True)

    # --- 1b. AGGREGATE BY CITY ---
    city_stats = {}
    for r in all_results:
        city = r.get("city", "Unknown")
        state = r.get("state", "Unknown")
        venue = r["venue"]
        city_key = (state, city)

        if city_key not in city_stats:
            city_stats[city_key] = {
                "city": city, "state": state,
                "gross": 0, "tickets": 0, "seats": 0, "shows": 0,
                "venues": set()
            }

        city_stats[city_key]["gross"] += r["booked_gross"]
        city_stats[city_key]["tickets"] += r["booked_tickets"]
        city_stats[city_key]["seats"] += r["total_tickets"]
        city_stats[city_key]["shows"] += 1
        city_stats[city_key]["venues"].add(venue)

    city_list = []
    for ck, cs in city_stats.items():
        occ = round((cs["tickets"] / cs["seats"]) * 100, 1) if cs["seats"] else 0
        city_list.append({
            "name": cs["city"],
            "state": cs["state"],
            "gross": cs["gross"],
            "tickets": cs["tickets"],
            "shows": cs["shows"],
            "venues": len(cs["venues"]),
            "occupancy": occ
        })

    city_list.sort(key=lambda x: x["gross"], reverse=True)
    total_cities = len(city_list)
    
    # --- 2. BUILD STATE ROWS ---
    state_rows = ""
    for idx, s in enumerate(state_list, 1):
        occ_color = get_occupancy_color(s["occupancy"])
        state_rows += f"""
        <tr>
            <td class="rank">${idx}</td>
            <td><strong>{s['name']}</strong></td>
            <td class="num">{s['venues']}</td>
            <td class="num">{s['shows']}</td>
            <td class="num">{s['tickets']:,}</td>
            <td class="num">
                <div class="occ-bar-wrap">
                    <div class="occ-bar" style="width:{s['occupancy']}%;background:{occ_color}"></div>
                    <span style="color:{occ_color}">{s['occupancy']}%</span>
                </div>
            </td>
            <td class="num gross-cell">{format_currency(s['gross'])}</td>
        </tr>"""
    
    # --- 2b. BUILD CITY ROWS ---
    city_rows = ""
    for idx, c in enumerate(city_list, 1):
        occ_color = get_occupancy_color(c["occupancy"])
        hidden_class = ' class="hidden-row"' if idx > 50 else ''
        city_rows += f"""
        <tr{hidden_class}>
            <td class="rank">{idx}</td>
            <td><strong>{c['state']}</strong></td>
            <td><strong>{c['name']}</strong></td>
            <td class="num">{c['venues']}</td>
            <td class="num">{c['shows']}</td>
            <td class="num">{c['tickets']:,}</td>
            <td class="num">
                <div class="occ-bar-wrap">
                    <div class="occ-bar" style="width:{c['occupancy']}%;background:{occ_color}"></div>
                    <span style="color:{occ_color}">{c['occupancy']}%</span>
                </div>
            </td>
            <td class="num gross-cell">{format_currency(c['gross'])}</td>
        </tr>"""

    # --- 3. BUILD VENUE ROWS (All States) ---
    venue_rows = ""
    venue_count = 1
    total_venues = 0
    for state_name in [s["name"] for s in state_list]:
        venues = state_venue_map[state_name]
        venue_list = []
        
        for v, d in venues.items():
            occ = round((d["tickets"] / d["seats"]) * 100, 1) if d["seats"] else 0
            venue_list.append({
                "name": v, "state": state_name, "gross": d["gross"],
                "tickets": d["tickets"], "shows": d["shows"], "seats": d["seats"],
                "occupancy": occ, "district_shows": d["source_count"]["district"],
                "bms_shows": d["source_count"]["bms"]
            })
        
        venue_list.sort(key=lambda x: x["gross"], reverse=True)
        total_venues += len(venue_list)
        
        for idx, v in enumerate(venue_list):  # Show all venues
            occ_color = get_occupancy_color(v["occupancy"])
            # Mark rows beyond 50 as hidden initially
            hidden_class = ' class="hidden-row"' if venue_count > 50 else ''
            venue_rows += f"""
            <tr{hidden_class}>
                <td class="rank">{venue_count}</td>
                <td><strong>{v['state']}</strong></td>
                <td><div class="theatre-name">{v['name']}</div></td>
                <td class="num">{v['shows']}</td>
                <td class="num">{v['tickets']:,}/{v['seats']:,}</td>
                <td class="num">
                    <div class="occ-bar-wrap">
                        <div class="occ-bar" style="width:{v['occupancy']}%;background:{occ_color}"></div>
                        <span style="color:{occ_color}">{v['occupancy']}%</span>
                    </div>
                </td>
                <td class="num gross-cell">{format_currency(v['gross'])}</td>
            </tr>"""
            venue_count += 1
    
    # --- 4. TOTAL STATS ---
    total_gross = sum(s["gross"] for s in state_list)
    total_tickets = sum(s["tickets"] for s in state_list)
    total_occupancy = round((sum(r["booked_tickets"] for r in all_results) / sum(r["total_tickets"] for r in all_results) * 100), 1) if all_results else 0
    num_theatres = sum(s["venues"] for s in state_list)
    num_shows = len(all_results)
    
    # --- 5. Platform breakdown ---
    source_gross_dist = sum(r["booked_gross"] for r in all_results if r.get("source") == "district")
    source_gross_bms = sum(r["booked_gross"] for r in all_results if r.get("source") == "bms")
    source_tickets_dist = sum(r["booked_tickets"] for r in all_results if r.get("source") == "district")
    source_tickets_bms = sum(r["booked_tickets"] for r in all_results if r.get("source") == "bms")
    source_shows_dist = sum(1 for r in all_results if r.get("source") == "district")
    source_shows_bms = sum(1 for r in all_results if r.get("source") == "bms")
    
    platform_html = f"""
    <div class="platform-card bms-card">
        <div class="platform-name">BookMyShow</div>
        <div class="platform-gross">{format_currency(source_gross_bms)}</div>
        <div class="platform-stats">
            <div>
                <div class="pstat-label">Shows</div>
                <div class="pstat-value">{source_shows_bms}</div>
            </div>
            <div>
                <div class="pstat-label">Tickets</div>
                <div class="pstat-value">{source_tickets_bms:,}</div>
            </div>
            <div>
                <div class="pstat-label">% Share</div>
                <div class="pstat-value">{round((source_gross_bms/total_gross)*100, 1) if total_gross else 0}%</div>
            </div>
        </div>
    </div>
    <div class="platform-card dst-card">
        <div class="platform-name">District App</div>
        <div class="platform-gross">{format_currency(source_gross_dist)}</div>
        <div class="platform-stats">
            <div>
                <div class="pstat-label">Shows</div>
                <div class="pstat-value">{source_shows_dist}</div>
            </div>
            <div>
                <div class="pstat-label">Tickets</div>
                <div class="pstat-value">{source_tickets_dist:,}</div>
            </div>
            <div>
                <div class="pstat-label">% Share</div>
                <div class="pstat-value">{round((source_gross_dist/total_gross)*100, 1) if total_gross else 0}%</div>
            </div>
        </div>
    </div>"""
    
    total_occ_color = get_occupancy_color(total_occupancy)
    # --- 6. BUILD HTML ---
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{movie_name} — Multi-State Box Office Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0a0a0f;
            --surface: #13131c;
            --surface2: #1c1c2a;
            --border: #2a2a3d;
            --accent: #f5a623;
            --accent2: #e8174d;
            --text: #e8e8f0;
            --muted: #7070a0;
            --bms: #e8174d;
            --district: #9B4BE1;
        }}

        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: 'DM Sans', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }}

        /* ── Hero ── */
        .hero {{
            background: linear-gradient(135deg, #0d0d1a 0%, #1a0a20 50%, #0a1020 100%);
            border-bottom: 1px solid var(--border);
            padding: 48px 40px 36px;
            position: relative;
            overflow: hidden;
        }}
        .hero::before {{
            content: '';
            position: absolute;
            top: -60px; right: -60px;
            width: 320px; height: 320px;
            background: radial-gradient(circle, rgba(245,166,35,0.12) 0%, transparent 70%);
            pointer-events: none;
        }}
        .hero::after {{
            content: '';
            position: absolute;
            bottom: -80px; left: 20%;
            width: 400px; height: 200px;
            background: radial-gradient(circle, rgba(232,23,77,0.08) 0%, transparent 70%);
            pointer-events: none;
        }}
        .hero-eyebrow {{
            font-size: 11px;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: var(--accent);
            margin-bottom: 10px;
            font-weight: 600;
        }}
        .hero-title {{
            font-family: 'Bebas Neue', sans-serif;
            font-size: clamp(42px, 7vw, 80px);
            letter-spacing: 2px;
            line-height: 0.95;
            background: linear-gradient(135deg, #fff 30%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 12px;
        }}
        .hero-meta {{
            display: flex;
            gap: 24px;
            flex-wrap: wrap;
            margin-top: 16px;
            color: var(--muted);
            font-size: 13px;
        }}
        .hero-meta span {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .hero-meta strong {{ color: var(--text); }}

        /* ── KPI Strip ── */
        .kpi-strip {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 1px;
            background: var(--border);
            border-bottom: 1px solid var(--border);
        }}
        .kpi-card {{
            background: var(--surface);
            padding: 28px 24px;
            text-align: center;
        }}
        .kpi-label {{
            font-size: 10px;
            letter-spacing: 2.5px;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .kpi-value {{
            font-family: 'Bebas Neue', sans-serif;
            font-size: 36px;
            letter-spacing: 1px;
            color: var(--accent);
        }}
        .kpi-card.total .kpi-value {{
            background: linear-gradient(135deg, var(--accent), var(--accent2));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 44px;
        }}

        /* ── Main Layout ── */
        .main {{ padding: 32px 40px; max-width: 1400px; margin: 0 auto; }}

        /* ── Section ── */
        .section {{ margin-bottom: 48px; }}
        .section-header {{
            display: flex;
            align-items: baseline;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }}
        .section-title {{
            font-family: 'Bebas Neue', sans-serif;
            font-size: 24px;
            letter-spacing: 1.5px;
            color: var(--text);
        }}
        .section-sub {{
            font-size: 12px;
            color: var(--muted);
            letter-spacing: 1px;
            text-transform: uppercase;
        }}

        /* ── Platform Cards ── */
        .platform-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
        }}
        .platform-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s;
        }}
        .platform-card:hover {{ transform: translateY(-2px); }}
        .platform-card.bms-card {{ border-top: 3px solid var(--bms); }}
        .platform-card.dst-card {{ border-top: 3px solid var(--district); }}
        .platform-card::before {{
            content: '';
            position: absolute;
            top: 0; right: 0;
            width: 120px; height: 120px;
            border-radius: 50%;
            opacity: 0.06;
        }}
        .bms-card::before {{ background: var(--bms); }}
        .dst-card::before {{ background: var(--district); }}
        .platform-name {{
            font-size: 11px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 4px;
        }}
        .platform-gross {{
            font-family: 'Bebas Neue', sans-serif;
            font-size: 36px;
            letter-spacing: 1px;
            margin-bottom: 16px;
        }}
        .bms-card .platform-gross {{ color: var(--bms); }}
        .dst-card .platform-gross {{ color: var(--district); }}
        .platform-stats {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 12px;
        }}
        .pstat-label {{ font-size: 10px; color: var(--muted); text-transform: uppercase; }}
        .pstat-value {{ font-size: 18px; font-weight: 700; color: var(--text); }}

        /* ── Tables ── */
        .table-wrap {{
            overflow-x: auto;
            border: 1px solid var(--border);
            border-radius: 12px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
        }}
        thead th {{
            background: var(--surface2);
            color: var(--muted);
            font-size: 10px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            font-weight: 600;
            padding: 12px 16px;
            text-align: left;
            white-space: nowrap;
            border-bottom: 1px solid var(--border);
        }}
        /* Align numeric columns right */
        table:nth-of-type(1) thead th:nth-child(3),
        table:nth-of-type(1) thead th:nth-child(4),
        table:nth-of-type(1) thead th:nth-child(5),
        table:nth-of-type(1) thead th:nth-child(6),
        table:nth-of-type(1) thead th:nth-child(7) {{
            text-align: right;
        }}
        table:nth-of-type(2) thead th:nth-child(4),
        table:nth-of-type(2) thead th:nth-child(5),
        table:nth-of-type(2) thead th:nth-child(6),
        table:nth-of-type(2) thead th:nth-child(7),
        table:nth-of-type(2) thead th:nth-child(8) {{
            text-align: right;
        }}
        table:nth-of-type(3) thead th:nth-child(4),
        table:nth-of-type(3) thead th:nth-child(5),
        table:nth-of-type(3) thead th:nth-child(6),
        table:nth-of-type(3) thead th:nth-child(7) {{
            text-align: right;
        }}
        tbody tr {{
            border-bottom: 1px solid var(--border);
            transition: background 0.15s;
        }}
        tbody tr:hover {{ background: var(--surface2); }}
        td {{
            padding: 12px 16px;
            vertical-align: middle;
        }}
        td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        td.gross-cell {{ font-weight: 700; color: var(--accent); }}
        td.rank {{ color: var(--muted); font-size: 12px; width: 40px; }}

        .theatre-name {{ font-weight: 600; color: var(--text); }}

        /* ── Occupancy Bar ── */
        .occ-bar-wrap {{
            display: flex;
            align-items: center;
            gap: 8px;
            justify-content: flex-end;
        }}
        .occ-bar {{
            height: 6px;
            border-radius: 3px;
            max-width: 70px;
            width: 70px;
            flex-shrink: 0;
            order: -1;
        }}
        .occ-bar-wrap span {{ font-weight: 700; font-size: 13px; width: 42px; text-align: right; }}

        /* ── Footer ── */
        .footer {{
            text-align: center;
            padding: 32px 40px;
            color: var(--muted);
            font-size: 12px;
            border-top: 1px solid var(--border);
        }}
        .footer strong {{ color: var(--accent); }}

        /* ── Toggle ── */
        .hidden-row {{ display: none; }}
        .show-all-btn {{
            display: inline-block;
            margin-top: 16px;
            padding: 8px 16px;
            background: var(--surface2);
            color: var(--accent);
            border: 1px solid var(--accent);
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.5px;
            transition: all 0.2s;
        }}
        .show-all-btn:hover {{
            background: var(--accent);
            color: var(--bg);
        }}
        .toggle-container {{
            text-align: center;
            padding: 20px;
        }}

        /* ── Responsive ── */
        @media (max-width: 768px) {{
            .hero {{ padding: 32px 20px; }}
            .main {{ padding: 20px; }}
            table {{ font-size: 12px; }}
            td {{ padding: 8px; }}
        }}

        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border); }}
    </style>
</head>
<body>

<!-- Hero -->
<header class="hero">
    <div class="hero-eyebrow">📽 State-wise Box Office Report</div>
    <div class="hero-title">{movie_name}</div>
    <div class="hero-meta">
        <span>🌍 <strong>Multi-State Release</strong></span>
        <span>📅 <strong>{show_date}</strong></span>
        <span>🕐 Report Generated: <strong>{datetime.now().strftime("%d %b %Y, %I:%M %p")}</strong></span>
        <span>🗺️ <strong>{len(state_list)} States</strong></span>
        <span>🎪 <strong>{num_theatres} Theatres</strong></span>
        <span>🎬 <strong>{num_shows} Shows</strong></span>
    </div>
</header>

<!-- KPI Strip -->
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
        <div class="kpi-label">States</div>
        <div class="kpi-value">{len(state_list)}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Theatres</div>
        <div class="kpi-value">{num_theatres}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Avg Occupancy</div>
        <div class="kpi-value" style="color:{total_occ_color}">{total_occupancy}%</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Total Shows</div>
        <div class="kpi-value">{num_shows}</div>
    </div>
</div>

<!-- Main Content -->
<main class="main">

    <!-- Platform Breakdown -->
    <section class="section">
        <div class="section-header">
            <div class="section-title">Platform Breakdown</div>
            <div class="section-sub">BMS vs District</div>
        </div>
        <div class="platform-grid">
            {platform_html}
        </div>
    </section>

    <!-- State Rankings -->
    <section class="section">
        <div class="section-header">
            <div class="section-title">State Rankings</div>
            <div class="section-sub">By Gross Collection</div>
        </div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>State</th>
                        <th>Theatres</th>
                        <th>Shows</th>
                        <th>Tickets Sold</th>
                        <th>Occupancy</th>
                        <th>Gross</th>
                    </tr>
                </thead>
                <tbody>
                    {state_rows}
                </tbody>
            </table>
        </div>
    </section>

    <!-- City Rankings -->
    <section class="section">
        <div class="section-header">
            <div class="section-title">City Rankings</div>
            <div class="section-sub">All States - By Gross Collection</div>
        </div>
        <div class="table-wrap">
            <table id="cityTable">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>State</th>
                        <th>City</th>
                        <th>Theatres</th>
                        <th>Shows</th>
                        <th>Tickets Sold</th>
                        <th>Occupancy</th>
                        <th>Gross</th>
                    </tr>
                </thead>
                <tbody>
                    {city_rows}
                </tbody>
            </table>
        </div>
        {f'<div class="toggle-container"><button class="show-all-btn" onclick="toggleRows(\'cityTable\')">🏙️ Show All {total_cities} Cities</button></div>' if total_cities > 50 else ''}
    </section>

    <!-- Theatre Rankings -->
    <section class="section">
        <div class="section-header">
            <div class="section-title">Theatre Rankings</div>
            <div class="section-sub">All States - By Gross Collection</div>
        </div>
        <div class="table-wrap">
            <table id="venueTable">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>State</th>
                        <th>Theatre</th>
                        <th>Shows</th>
                        <th>Seats (Booked/Total)</th>
                        <th>Occupancy</th>
                        <th>Gross</th>
                    </tr>
                </thead>
                <tbody>
                    {venue_rows}
                </tbody>
            </table>
        </div>
        {f'<div class="toggle-container"><button class="show-all-btn" onclick="toggleRows(\'venueTable\')">🎪 Show All {total_venues} Venues</button></div>' if total_venues > 50 else ''}
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
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const btn = event.target;
    
    // Check if there are currently hidden rows
    const hiddenCount = table.querySelectorAll('tbody tr.hidden-row').length;
    const hasHidden = hiddenCount > 0;
    
    if(hasHidden) {{
        // Show all rows
        table.querySelectorAll('tbody tr.hidden-row').forEach(row => {{
            row.classList.remove('hidden-row');
        }});
        btn.textContent = '🔽 Hide Details';
    }} else {{
        // Hide rows beyond first 50
        rows.forEach((row, index) => {{
            if(index >= 50) {{
                row.classList.add('hidden-row');
            }}
        }});
        btn.textContent = '🎪 Show All ' + rows.length + ' Venues';
    }}
}}
</script>

</body>
</html>"""
    
    # Ensure reports directory exists
    reports_dir = os.path.dirname(output_path)
    if reports_dir:
        os.makedirs(reports_dir, exist_ok=True)
    
    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Premium Multi-State HTML Report generated: {output_path}")
