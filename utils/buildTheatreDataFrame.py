import pandas as pd

def build_theatre_dataframe(results):
    df = pd.DataFrame(results)

    theatre_df = (
        df.groupby("venue")
        .agg(
            shows=("showTime", "count"),
            total_seats=("total_tickets", "sum"),
            booked_seats=("booked_tickets", "sum"),
            gross=("booked_gross", "sum")
        )
        .reset_index()
    )

    theatre_df["occupancy"] = (
        theatre_df["booked_seats"] / theatre_df["total_seats"] * 100
    ).round(1)

    return theatre_df.sort_values("gross", ascending=False)
