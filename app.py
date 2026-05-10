"""Streamlit dashboard over data/activities.parquet and data/streams/."""
from __future__ import annotations
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
ACTIVITIES_PARQUET = ROOT / "data" / "activities.parquet"

DISTANCE_BUCKETS = [
    ("<5k",   0,      5000),
    ("5–10k", 5000,   10000),
    ("10–21k", 10000, 21000),
    ("21k+",  21000,  10**9),
]


@st.cache_data(show_spinner=False)
def load_activities(mtime_key: float) -> pd.DataFrame:
    df = pd.read_parquet(ACTIVITIES_PARQUET)
    df["start_time_utc"] = pd.to_datetime(df["start_time_utc"], utc=True)
    df["date"] = df["start_time_utc"].dt.date
    df["year"] = df["start_time_utc"].dt.year
    df["bucket"] = pd.cut(
        df["distance_m"],
        bins=[b[1] for b in DISTANCE_BUCKETS] + [DISTANCE_BUCKETS[-1][2]],
        labels=[b[0] for b in DISTANCE_BUCKETS],
        include_lowest=True,
    )
    return df


def _missing_data_screen() -> None:
    st.error("No data found. Run `python prepare.py` first.")
    st.code("python prepare.py", language="bash")
    st.stop()


def _sidebar(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")
    min_d, max_d = df["date"].min(), df["date"].max()
    date_range = st.sidebar.slider(
        "Date range", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM",
    )
    years = sorted(df["year"].unique())
    sel_years = st.sidebar.multiselect("Years", years, default=years)
    sel_buckets = st.sidebar.multiselect(
        "Distance buckets", [b[0] for b in DISTANCE_BUCKETS], default=[b[0] for b in DISTANCE_BUCKETS],
    )
    show_lq = st.sidebar.toggle("Include low-quality runs", value=False)
    show_indoor = st.sidebar.toggle("Include indoor runs", value=True)

    mask = (
        (df["date"] >= date_range[0]) & (df["date"] <= date_range[1])
        & (df["year"].isin(sel_years))
        & (df["bucket"].astype(str).isin(sel_buckets))
    )
    if not show_lq:
        mask &= ~df["low_quality"].fillna(False)
    if not show_indoor:
        mask &= ~df["indoor"].fillna(False)
    return df[mask].copy()


def main() -> None:
    st.set_page_config(page_title="Running Dashboard", layout="wide")
    st.title("🏃 Running Dashboard")
    if not ACTIVITIES_PARQUET.exists():
        _missing_data_screen()
    df = load_activities(ACTIVITIES_PARQUET.stat().st_mtime)
    filtered = _sidebar(df)
    st.caption(f"{len(filtered)} runs match current filters (of {len(df)} total).")

    tab1, tab2, tab3, tab4 = st.tabs(["Volume", "Pace & HR", "Personal Records", "Calendar"])
    with tab1:
        from lib.views import (
            fig_weekly_distance_stacked, fig_rolling_4wk, fig_yoy_monthly, kpi_volume,
        )
        kpis = kpi_volume(filtered)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total km", f"{kpis['total_km']:.0f}")
        c2.metric("Total runs", kpis["runs"])
        c3.metric("Total hours", f"{kpis['total_hours']:.0f}")
        delta_km = kpis["last_4wk_km"] - kpis["prev_year_4wk_km"]
        c4.metric("Last 4-wk km", f"{kpis['last_4wk_km']:.1f}",
                  delta=f"{delta_km:+.1f} vs 1 yr ago")
        st.plotly_chart(fig_weekly_distance_stacked(filtered), use_container_width=True)
        st.plotly_chart(fig_rolling_4wk(filtered), use_container_width=True)
        st.plotly_chart(fig_yoy_monthly(filtered), use_container_width=True)
    with tab2:
        from lib.views import (
            fig_pace_scatter, fig_pace_rolling_by_bucket,
            fig_aerobic_efficiency, fig_hr_zones_monthly, fig_hr_drift,
        )
        max_hr = float(filtered["max_hr"].max() if filtered["max_hr"].notna().any() else 190)
        default_target = round(max_hr * 0.75)
        target_hr = st.slider("Aerobic-efficiency target HR (bpm)", min_value=100, max_value=180,
                              value=int(default_target), step=1)
        st.plotly_chart(fig_pace_scatter(filtered), use_container_width=True)
        st.plotly_chart(fig_pace_rolling_by_bucket(filtered), use_container_width=True)
        st.plotly_chart(fig_aerobic_efficiency(filtered, target_hr=target_hr), use_container_width=True)
        st.plotly_chart(fig_hr_zones_monthly(filtered), use_container_width=True)
        st.plotly_chart(fig_hr_drift(filtered), use_container_width=True)
    with tab3:
        from lib.views import pr_table, fig_pr_progression, fig_long_runs_per_year, _pace_label
        prs = pr_table(filtered)
        if prs.empty:
            st.info("No PR data — none of the runs reached the PR distances, or `best_efforts` is missing.")
        else:
            display = prs.copy()
            for c in display.columns:
                display[c] = display[c].map(_pace_label)
            st.subheader("Best times per year")
            st.dataframe(display, use_container_width=True)
            st.plotly_chart(fig_pr_progression(prs), use_container_width=True)
        st.plotly_chart(fig_long_runs_per_year(filtered), use_container_width=True)
    with tab4:
        from lib.views import fig_year_heatmap, streak_stats, fig_dow_histogram, fig_hour_histogram
        stats = streak_stats(filtered)
        c1, c2 = st.columns(2)
        c1.metric("Longest streak (days)", stats["longest"])
        c2.metric("Current streak (days)", stats["current"])
        for y in sorted(filtered["year"].dropna().unique(), reverse=True):
            st.plotly_chart(fig_year_heatmap(filtered, int(y)), use_container_width=True)
        st.plotly_chart(fig_dow_histogram(filtered), use_container_width=True)
        st.plotly_chart(fig_hour_histogram(filtered), use_container_width=True)


if __name__ == "__main__":
    main()
