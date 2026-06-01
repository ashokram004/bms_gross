import os
import json
from datetime import datetime

def generate_hybrid_states_html_report(
        all_results,
        output_path,
        movie_name="Movie Collection",
        show_date="N/A"
):
    print("🎨 Generating Premium Reactive Glassmorphism HTML Report...")

    if not show_date or show_date == "N/A":
        show_date = datetime.now().strftime("%d %b %Y")

    # ========================================================
    # FRONTEND RAW DATA
    # ========================================================

    frontend_rows = []

    for row in all_results:
        # Time Category parsing
        dt_str = row.get('normalized_show_time', '')
        time_str = "Unknown"
        timeCat = "7. Unknown Time"
        
        if dt_str:
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                time_str = dt.strftime("%I:%M %p")
                h = dt.hour
                if 5 <= h < 9: timeCat = "1. Early Morning (5am-9am)"
                elif 9 <= h < 12: timeCat = "2. Morning (9am-12pm)"
                elif 12 <= h < 16: timeCat = "3. Afternoon (12pm-4pm)"
                elif 16 <= h < 20: timeCat = "4. Evening (4pm-8pm)"
                elif 20 <= h < 24: timeCat = "5. Night (8pm-12am)"
                else: timeCat = "6. Midnight (12am-5am)"
            except Exception:
                pass

        total_tix = row.get('total_tickets', 0)
        booked_tix = row.get('booked_tickets', 0)
        
        status = "Available"
        if total_tix == 0:
            status = "N/A"
        elif booked_tix >= total_tix:
            status = "Sold Out"

        frontend_rows.append({
            'source': row.get('source', '').upper(),
            'state': row.get('state', 'Unknown'),
            'city': row.get('city', 'Unknown'),
            'theater': row.get('venue', 'Unknown'),
            'time': time_str,
            'timeCat': timeCat,
            'status': status,
            'total': total_tix,
            'booked': booked_tix,
            'gross': row.get('booked_gross', 0),
            'is_extra': row.get('is_fallback', False)
        })

    frontend_json = json.dumps(frontend_rows)

    # ========================================================
    # HTML SKELETON & VUE TEMPLATE
    # ========================================================

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{movie_name} - Advance Sales Report</title>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>

<style>
:root {{
    --bg-color: #020617;
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
    --primary: #f58320;
    --glass-bg: rgba(255, 255, 255, 0.03);
    --glass-border: rgba(255, 255, 255, 0.06);
    --glass-highlight: rgba(255, 255, 255, 0.12);
}}

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font-family: 'Inter', sans-serif;
}}

body {{
    background-color: var(--bg-color);
    background-image:
        radial-gradient(circle at 10% 20%, rgba(37, 99, 235, 0.12), transparent 30%),
        radial-gradient(circle at 90% 40%, rgba(245, 131, 32, 0.08), transparent 30%),
        radial-gradient(circle at 50% 90%, rgba(139, 92, 246, 0.12), transparent 40%);
    background-attachment: fixed;
    color: var(--text-main);
    padding: 20px;
}}

.container {{
    max-width: 1400px;
    margin: 0 auto;
}}

.header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 25px;
    padding-bottom: 15px;
    border-bottom: 1px solid var(--glass-border);
}}

.header h1 {{
    font-size: 26px;
    font-weight: 600;
    color: var(--text-main);
    letter-spacing: -0.5px;
}}

.header-meta {{
    text-align: right;
    color: var(--text-muted);
    font-size: 13px;
    line-height: 1.6;
}}

.header-meta strong {{ color: var(--text-main); font-weight: 500; }}

.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-bottom: 20px;
}}

.kpi-card {{
    background: var(--glass-bg);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    padding: 20px;
    border-radius: 16px;
    border: 1px solid var(--glass-border);
    border-top: 1px solid var(--glass-highlight);
    border-left: 1px solid var(--glass-highlight);
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
    position: relative;
    overflow: hidden;
}}

.kpi-title {{
    font-size: 12px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
    margin-bottom: 8px;
}}

.kpi-value {{
    font-size: 26px;
    font-weight: 600;
    color: var(--text-main);
}}

.kpi-sub {{
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 6px;
}}

.dashboard-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
    align-items: stretch;
}}

@media (max-width: 1000px) {{
    .dashboard-row {{ grid-template-columns: 1fr; }}
}}

.summary-section {{
    background: var(--glass-bg);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-radius: 16px;
    padding: 20px;
    border: 1px solid var(--glass-border);
    border-top: 1px solid var(--glass-highlight);
    border-left: 1px solid var(--glass-highlight);
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
    overflow-x: auto;
    display: flex;
    flex-direction: column;
}}

.summary-section h2 {{
    font-size: 16px;
    margin-bottom: 15px;
    font-weight: 500;
    color: var(--text-main);
    border-bottom: 1px solid var(--glass-border);
    padding-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}

th, td {{
    padding: 12px 10px;
    text-align: right;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}}

th {{
    background-color: rgba(255, 255, 255, 0.02);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    color: var(--text-muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 11px;
    cursor: pointer;
    user-select: none;
    position: sticky;
    top: 0;
    z-index: 10;
}}

th:first-child, td:first-child {{ text-align: left; }}

tr:hover td {{ background-color: rgba(255,255,255,0.04); }}

.gross-val {{ font-weight: 600; color: #f8fafc; }}
.state-col {{ font-weight: 500; color: var(--text-muted); }}
.theater-col {{ font-weight: 400; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }}
.format-col {{ color: #fbbf24; font-weight: 500; }}
.language-col {{ color: #a78bfa; font-weight: 500; }}

.status-badge {{
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.status-available {{ background-color: rgba(22, 163, 74, 0.15); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.2); }}
.status-sold-out {{ background-color: rgba(220, 38, 38, 0.15); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.2); }}

.btn-toggle {{
    background: rgba(255,255,255,0.05);
    border: 1px solid var(--glass-border);
    backdrop-filter: blur(10px);
    padding: 8px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-main);
    margin-top: auto;
    width: 100%;
    transition: all 0.2s;
}}
.btn-toggle:hover {{ background: rgba(255,255,255,0.1); border-color: var(--glass-highlight); }}

.footer {{
    text-align: center;
    margin-top: 30px;
    padding-top: 20px;
    border-top: 1px solid var(--glass-border);
    color: var(--text-muted);
    font-size: 12px;
}}

/* FILTER PANEL */
.filter-panel {{
    background: var(--glass-bg);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-radius: 16px;
    padding: 20px;
    border: 1px solid var(--glass-border);
    border-top: 1px solid var(--glass-highlight);
    border-left: 1px solid var(--glass-highlight);
    margin-bottom: 20px;
}}

.filter-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
}}

.filter-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    margin-bottom: 8px;
    font-weight: 600;
}}

.filter-select {{
    width: 100%;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--glass-border);
    color: var(--text-main);
    padding: 12px;
    border-radius: 10px;
    outline: none;
    font-size: 13px;
}}
.filter-select option {{ background: #0f172a; color: white; }}

.toggle-filter-btn {{
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    border: none;
    color: white;
    padding: 12px 18px;
    border-radius: 10px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    transition: all 0.2s;
}}
.toggle-filter-btn:hover {{ transform: translateY(-1px); opacity: 0.95; }}

</style>
</head>

<body>
<div id="app">
<div class="container">

    <div class="header">
        <h1>{movie_name} - Advance Sales Report</h1>
        <div class="header-meta">
            Show Date: <strong>{show_date}</strong><br>
            Report Generated: <strong>{datetime.now().strftime("%d %b %Y, %I:%M %p")}</strong> IST
        </div>
    </div>

    <div style="display:flex; justify-content:flex-end; margin-bottom:20px;">
        <button @click="showFilters = !showFilters" class="toggle-filter-btn">
            {{{{ showFilters ? 'Hide Filters' : 'Show Filters' }}}}
        </button>
    </div>

    <div v-show="showFilters" class="filter-panel">
        <div class="filter-grid">
            
            <div>
                <div class="filter-label">State</div>
                <select v-model="filters.state" class="filter-select">
                    <option value="ALL">All States</option>
                    <option v-for="st in uniqueStates" :key="st" :value="st">{{{{ st }}}}</option>
                </select>
            </div>

            <div>
                <div class="filter-label">City</div>
                <select v-model="filters.city" class="filter-select">
                    <option value="ALL">All Cities</option>
                    <option v-for="ct in filteredCitiesList" :key="ct" :value="ct">{{{{ ct }}}}</option>
                </select>
            </div>

            <div>
                <div class="filter-label">Theatre</div>
                <select v-model="filters.theater" class="filter-select">
                    <option value="ALL">All Theatres</option>
                    <option v-for="th in filteredTheatersList" :key="th" :value="th">{{{{ th }}}}</option>
                </select>
            </div>

            <div>
                <div class="filter-label">Platform (Source)</div>
                <select v-model="filters.source" class="filter-select">
                    <option value="ALL">All Platforms</option>
                    <option v-for="sc in uniqueSources" :key="sc" :value="sc">{{{{ sc }}}}</option>
                </select>
            </div>

            <div>
                <div class="filter-label">Time Of Day</div>
                <select v-model="filters.timeCat" class="filter-select">
                    <option value="ALL">All Times</option>
                    <option v-for="tm in uniqueTimeCats" :key="tm" :value="tm">{{{{ tm }}}}</option>
                </select>
            </div>

        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">Total Gross</div>
            <div class="kpi-value">{{{{ formatCurrency(kpis.gross) }}}}</div>
        </div>

        <div class="kpi-card">
            <div class="kpi-title">Tickets Sold</div>
            <div class="kpi-value">{{{{ formatInt(kpis.booked) }}}}</div>
            <div class="kpi-sub">{{{{ formatInt(kpis.total) }}}} cap</div>
        </div>

        <div class="kpi-card">
            <div class="kpi-title">Total Venues</div>
            <div class="kpi-value">{{{{ formatInt(kpis.venues) }}}}</div>
        </div>

        <div class="kpi-card">
            <div class="kpi-title">Total Shows</div>
            <div class="kpi-value">{{{{ formatInt(kpis.shows) }}}}</div>
        </div>

        <div class="kpi-card">
            <div class="kpi-title">Overall Occupancy</div>
            <div class="kpi-value" :style="{{ color: getOccupancyColor(kpis.occupancy) }}">
                {{{{ kpis.occupancy.toFixed(1) }}}}%
            </div>
        </div>

        <div class="kpi-card">
            <div class="kpi-title">Avg Ticket Price</div>
            <div class="kpi-value">{{{{ formatCurrency(kpis.atp) }}}}</div>
        </div>
    </div>

    <div class="dashboard-row">
        
        <div class="summary-section">
            <h2>Platform Distribution</h2>
            <table>
                <thead>
                    <tr>
                        <th>Platform</th>
                        <th>Shows</th>
                        <th>Tickets</th>
                        <th>Gross</th>
                        <th>Occ %</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="row in sourceSummary" :key="row.name">
                        <td class="format-col">{{{{ row.name }}}}</td>
                        <td>{{{{ formatInt(row.shows) }}}}</td>
                        <td>{{{{ formatInt(row.booked) }}}}</td>
                        <td class="gross-val">{{{{ formatCurrency(row.gross) }}}}</td>
                        <td :style="{{ color: getOccupancyColor(row.occupancy) }}">{{{{ row.occupancy.toFixed(1) }}}}%</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="summary-section">
            <h2>Time Of Day Analysis</h2>
            <table>
                <thead>
                    <tr>
                        <th>Time Category</th>
                        <th>Shows</th>
                        <th>Tickets</th>
                        <th>Gross</th>
                        <th>Occ %</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="row in timeSummary" :key="row.name">
                        <td class="state-col">{{{{ row.name }}}}</td>
                        <td>{{{{ formatInt(row.shows) }}}}</td>
                        <td>{{{{ formatInt(row.booked) }}}}</td>
                        <td class="gross-val">{{{{ formatCurrency(row.gross) }}}}</td>
                        <td :style="{{ color: getOccupancyColor(row.occupancy) }}">{{{{ row.occupancy.toFixed(1) }}}}%</td>
                    </tr>
                </tbody>
            </table>
        </div>

    </div>

    <div class="dashboard-row">
        
        <div class="summary-section">
            <h2>State Distribution</h2>
            <table>
                <thead>
                    <tr>
                        <th>State</th>
                        <th>Shows</th>
                        <th>Tickets</th>
                        <th>Gross</th>
                        <th>Occ %</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="row in stateSummary" :key="row.name">
                        <td class="state-col">{{{{ row.name }}}}</td>
                        <td>{{{{ formatInt(row.shows) }}}}</td>
                        <td>{{{{ formatInt(row.booked) }}}}</td>
                        <td class="gross-val">{{{{ formatCurrency(row.gross) }}}}</td>
                        <td :style="{{ color: getOccupancyColor(row.occupancy) }}">{{{{ row.occupancy.toFixed(1) }}}}%</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="summary-section">
            <h2>City Distribution</h2>
            <table>
                <thead>
                    <tr>
                        <th>City</th>
                        <th>Shows</th>
                        <th>Tickets</th>
                        <th>Gross</th>
                        <th>Occ %</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="row in displayedCitySummary" :key="row.name">
                        <td class="language-col">{{{{ row.name }}}}</td>
                        <td>{{{{ formatInt(row.shows) }}}}</td>
                        <td>{{{{ formatInt(row.booked) }}}}</td>
                        <td class="gross-val">{{{{ formatCurrency(row.gross) }}}}</td>
                        <td :style="{{ color: getOccupancyColor(row.occupancy) }}">{{{{ row.occupancy.toFixed(1) }}}}%</td>
                    </tr>
                    <tr v-if="citySummary.length > 20">
                        <td colspan="5" style="text-align:center; padding:18px; border-bottom:none;">
                            <button @click="showAllCities = !showAllCities" class="btn-toggle" style="width:auto; padding:10px 18px;">
                                {{{{ showAllCities ? 'Hide Full City List' : 'Show Full City List' }}}}
                            </button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

    </div>

    <div class="summary-section" style="margin-bottom:20px;">
        <h2>Top Theatres</h2>
        <table>
            <thead>
                <tr>
                    <th>State</th>
                    <th>City</th>
                    <th>Theatre</th>
                    <th>Shows</th>
                    <th>Tickets</th>
                    <th>Gross</th>
                    <th>Occ %</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="row in displayedTheatreSummary" :key="row.name">
                    <td class="state-col">{{{{ row.state }}}}</td>
                    <td class="language-col">{{{{ row.city }}}}</td>
                    <td class="theater-col">{{{{ row.name }}}}</td>
                    <td>{{{{ formatInt(row.shows) }}}}</td>
                    <td>{{{{ formatInt(row.booked) }}}}</td>
                    <td class="gross-val">{{{{ formatCurrency(row.gross) }}}}</td>
                    <td :style="{{ color: getOccupancyColor(row.occupancy) }}">{{{{ row.occupancy.toFixed(1) }}}}%</td>
                </tr>
                <tr v-if="theatreSummary.length > 40">
                    <td colspan="7" style="text-align:center; padding:18px; border-bottom:none;">
                        <button @click="showAllTheatres = !showAllTheatres" class="btn-toggle" style="width:auto; padding:10px 18px;">
                            {{{{ showAllTheatres ? 'Hide Full Theatre List' : 'Show Full Theatre List' }}}}
                        </button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="summary-section" style="margin-bottom:0;">
        <h2>All Showtimes <span style="font-size:12px; font-weight:400; color:var(--text-muted);">(Reactive Filtering Enabled)</span></h2>
        <div style="overflow-x:auto; max-height:700px; overflow-y:auto;">
            <table id="showsTable">
                <thead>
                    <tr>
                        <th>Platform</th>
                        <th>City</th>
                        <th>Theatre Name</th>
                        <th>Time</th>
                        <th>Time Category</th>
                        <th>Status</th>
                        <th>Tickets</th>
                        <th>Gross</th>
                        <th>Occ %</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="(row, idx) in filteredShows" :key="idx">
                        <td class="format-col">{{{{ row.source }}}}</td>
                        <td class="language-col">{{{{ row.city }}}}</td>
                        <td class="theater-col">{{{{ row.theater }}}}</td>
                        <td>{{{{ row.time }}}}</td>
                        <td style="font-size:11px; color:#94a3b8;">{{{{ row.timeCat }}}}</td>
                        <td>
                            <span class="status-badge" :class="[row.status === 'Sold Out' ? 'status-sold-out' : 'status-available']">
                                {{{{ row.status }}}}
                            </span>
                        </td>
                        <td>{{{{ formatInt(row.booked) }}}} / {{{{ formatInt(row.total) }}}}</td>
                        <td class="gross-val">{{{{ formatCurrency(row.gross) }}}}</td>
                        <td :style="{{ color: getOccupancyColor((row.booked / row.total) * 100 || 0) }}">
                            {{{{ ((row.booked / row.total) * 100 || 0).toFixed(1) }}}}%
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <div class="footer">
        Data Aggregation • WkndCinema BookMyShow & District Scraper • Generated {datetime.now().strftime("%d %b %Y, %I:%M %p")}
    </div>

</div>

<script>
window.__MASTER_DATA__ = {frontend_json};

const {{ createApp }} = Vue;

createApp({{
    data() {{
        return {{
            rawData: window.__MASTER_DATA__,
            showFilters: true,
            showAllTheatres: false,
            showAllCities: false,
            filters: {{
                state: 'ALL',
                city: 'ALL',
                theater: 'ALL',
                source: 'ALL',
                timeCat: 'ALL'
            }}
        }}
    }},
    computed: {{
        uniqueStates() {{ return [...new Set(this.rawData.map(d => d.state))].sort(); }},
        uniqueSources() {{ return [...new Set(this.rawData.map(d => d.source))].sort(); }},
        uniqueTimeCats() {{ return [...new Set(this.rawData.map(d => d.timeCat))].sort(); }},

        filteredCitiesList() {{
            let data = this.rawData;
            if (this.filters.state !== 'ALL') data = data.filter(d => d.state === this.filters.state);
            return [...new Set(data.map(d => d.city))].sort();
        }},

        filteredTheatersList() {{
            let data = this.rawData;
            if (this.filters.state !== 'ALL') data = data.filter(d => d.state === this.filters.state);
            if (this.filters.city !== 'ALL') data = data.filter(d => d.city === this.filters.city);
            return [...new Set(data.map(d => d.theater))].sort();
        }},

        filteredData() {{
            return this.rawData.filter(row => {{
                if (this.filters.state !== 'ALL' && row.state !== this.filters.state) return false;
                if (this.filters.city !== 'ALL' && row.city !== this.filters.city) return false;
                if (this.filters.theater !== 'ALL' && row.theater !== this.filters.theater) return false;
                if (this.filters.source !== 'ALL' && row.source !== this.filters.source) return false;
                if (this.filters.timeCat !== 'ALL' && row.timeCat !== this.filters.timeCat) return false;
                return true;
            }});
        }},

        kpis() {{
            const total = this.filteredData.reduce((s, r) => s + r.total, 0);
            const booked = this.filteredData.reduce((s, r) => s + r.booked, 0);
            const gross = this.filteredData.reduce((s, r) => s + r.gross, 0);
            return {{
                total, booked, gross,
                shows: this.filteredData.length,
                venues: new Set(this.filteredData.map(r => r.theater)).size,
                occupancy: total > 0 ? (booked / total) * 100 : 0,
                atp: booked > 0 ? gross / booked : 0
            }}
        }},

        stateSummary() {{ return this.groupByField('state'); }},
        citySummary() {{ return this.groupByField('city'); }},
        displayedCitySummary() {{ return this.showAllCities ? this.citySummary : this.citySummary.slice(0, 20); }},
        
        theatreSummary() {{ return this.groupByField('theater'); }},
        displayedTheatreSummary() {{ return this.showAllTheatres ? this.theatreSummary : this.theatreSummary.slice(0, 40); }},
        
        sourceSummary() {{ return this.groupByField('source'); }},
        timeSummary() {{ return this.groupByField('timeCat'); }},

        filteredShows() {{
            return [...this.filteredData].sort((a, b) => b.gross - a.gross);
        }}
    }},
    methods: {{
        formatCurrency(v) {{
            const absVal = Math.round(Math.abs(Number(v)));
            if (absVal >= 10000000) return "₹" + (v/10000000).toFixed(2) + " Cr";
            if (absVal >= 100000) return "₹" + (v/100000).toFixed(2) + " L";
            if (absVal >= 1000) return "₹" + (v/1000).toFixed(1) + " K";
            return "₹" + absVal.toLocaleString('en-IN');
        }},
        formatInt(v) {{ return Math.round(Number(v)).toLocaleString('en-IN'); }},
        getOccupancyColor(occ) {{
            if (occ >= 60) return '#4ade80';
            if (occ >= 50) return '#fb923c';
            if (occ >= 30) return '#facc15';
            return '#f87171';
        }},
        groupByField(field) {{
            const map = {{}};
            this.filteredData.forEach(r => {{
                const key = r[field];
                if (!map[key]) {{
                    map[key] = {{ name: key, state: r.state, city: r.city, shows: 0, total: 0, booked: 0, gross: 0 }}
                }}
                map[key].shows += 1;
                map[key].total += r.total;
                map[key].booked += r.booked;
                map[key].gross += r.gross;
            }});
            return Object.values(map)
                .map(r => ({{ ...r, occupancy: r.total > 0 ? (r.booked / r.total) * 100 : 0 }}))
                .sort((a, b) => b.gross - a.gross);
        }}
    }}
}}).mount('#app');
</script>

</body>
</html>
"""

    # ========================================================
    # SAVE HTML
    # ========================================================

    try:
        if os.path.dirname(output_path):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"📊 Reactive Glassmorphism HTML report saved to {output_path}")
        return output_path
    except Exception as e:
        print(f"Error saving HTML: {e}")
        return None