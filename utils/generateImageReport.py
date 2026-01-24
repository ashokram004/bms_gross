import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from datetime import datetime
from .computeCityKPIs import compute_city_kpis
from .buildTheatreDataFrame import build_theatre_dataframe
from .parseBMSURL import parse_bms_url

def generate_city_image_report(results, url, output_path):
    meta = parse_bms_url(url)
    theatre_df = build_theatre_dataframe(results)
    kpis = compute_city_kpis(theatre_df)

    top_theatres = theatre_df.head(20)

    fig = plt.figure(figsize=(18, 11), dpi=150)
    gs = GridSpec(3, 1, height_ratios=[0.9, 1.1, 3], hspace=0.25)

    # ================= HEADER =================
    ax0 = fig.add_subplot(gs[0])
    ax0.axis("off")

    ax0.text(
        0.01, 0.65,
        f"🎬 {meta['movie']}",
        fontsize=22, fontweight="bold"
    )
    ax0.text(
        0.01, 0.35,
        f"📍 {meta['city']}   |   📅 {meta['date']}",
        fontsize=14
    )

    # ================= KPI ROW =================
    ax1 = fig.add_subplot(gs[1])
    ax1.axis("off")

    kpi_text = (
        f"Theatres: {kpis['theatres']}     "
        f"Shows: {kpis['shows']}     "
        f"Tickets: {kpis['tickets']}     "
        f"Occupancy: {kpis['occupancy']}%     "
        f"Gross: ₹{kpis['gross']:,}"
    )

    ax1.text(
        0.01, 0.5,
        kpi_text,
        fontsize=15,
        fontweight="bold"
    )

    # ================= THEATRE TABLE =================
    ax2 = fig.add_subplot(gs[2])
    ax2.axis("off")
    ax2.set_title("Top 20 Theatres by Gross", fontsize=15, fontweight="bold", loc="left")

    table_data = top_theatres[
        ["venue", "shows", "booked_seats", "occupancy", "gross"]
    ].values

    table = ax2.table(
        cellText=table_data,
        colLabels=[
            "Theatre",
            "Shows",
            "Tickets Sold",
            "Occupancy %",
            "Gross (₹)"
        ],
        loc="center"
    )

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.4)

    # ================= FOOTER =================
    fig.text(
        0.01, 0.02,
        f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Source: BookMyShow",
        fontsize=9,
        color="gray"
    )

    plt.savefig(output_path, bbox_inches="tight")
    plt.close()

    print(f"🖼 City image report generated: {output_path}")
