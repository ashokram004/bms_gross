def compute_city_kpis(theatre_df):
    return {
        "theatres": theatre_df["venue"].nunique(),
        "shows": theatre_df["shows"].sum(),
        "tickets": theatre_df["booked_seats"].sum(),
        "occupancy": round(
            theatre_df["booked_seats"].sum() /
            theatre_df["total_seats"].sum() * 100, 1
        ),
        "gross": int(theatre_df["gross"].sum())
    }
