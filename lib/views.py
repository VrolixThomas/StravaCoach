"""Plotly chart builders. Each function takes a filtered activities DataFrame and returns a Figure."""
from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _weekly(df: pd.DataFrame) -> pd.DataFrame:
    s = df.assign(week=df["start_time_utc"].dt.tz_convert("UTC").dt.to_period("W").dt.start_time)
    return s.groupby(["week", "year"], as_index=False).agg(distance_km=("distance_m", lambda x: x.sum() / 1000))


def _monthly(df: pd.DataFrame) -> pd.DataFrame:
    s = df.assign(
        month=df["start_time_utc"].dt.month,
        year=df["start_time_utc"].dt.year,
    )
    return s.groupby(["year", "month"], as_index=False).agg(distance_km=("distance_m", lambda x: x.sum() / 1000))


def fig_weekly_distance_stacked(df: pd.DataFrame) -> go.Figure:
    w = _weekly(df)
    fig = px.bar(w, x="week", y="distance_km", color="year",
                 labels={"distance_km": "km", "week": "Week"},
                 title="Weekly distance (stacked by year)")
    fig.update_layout(barmode="stack", height=400)
    return fig


def fig_rolling_4wk(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    daily = (df.assign(d=df["start_time_utc"].dt.date)
               .groupby("d")
               .agg(km=("distance_m", lambda x: x.sum() / 1000),
                    hours=("moving_time_s", lambda x: x.sum() / 3600))
               .sort_index())
    full = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"), fill_value=0)
    full["km_4wk"] = full["km"].rolling(28).sum()
    full["hours_4wk"] = full["hours"].rolling(28).sum()
    fig = go.Figure()
    fig.add_scatter(x=full.index, y=full["km_4wk"], name="4-wk km", yaxis="y1")
    fig.add_scatter(x=full.index, y=full["hours_4wk"], name="4-wk hours", yaxis="y2")
    fig.update_layout(
        title="Rolling 4-week volume",
        yaxis=dict(title="km"),
        yaxis2=dict(title="hours", overlaying="y", side="right"),
        height=400,
    )
    return fig


def fig_yoy_monthly(df: pd.DataFrame) -> go.Figure:
    m = _monthly(df)
    fig = px.line(m, x="month", y="distance_km", color="year", markers=True,
                  title="Year-over-year monthly distance",
                  labels={"distance_km": "km", "month": "Month"})
    fig.update_layout(height=400, xaxis=dict(tickmode="array", tickvals=list(range(1, 13))))
    return fig


def kpi_volume(df: pd.DataFrame) -> dict:
    total_km = df["distance_m"].sum() / 1000
    total_hours = df["moving_time_s"].sum() / 3600
    runs = len(df)
    last_4wk = df[df["start_time_utc"] >= (df["start_time_utc"].max() - pd.Timedelta(days=28))]
    last_4wk_km = last_4wk["distance_m"].sum() / 1000
    one_y_ago_window_end = df["start_time_utc"].max() - pd.Timedelta(days=365)
    one_y_ago_window_start = one_y_ago_window_end - pd.Timedelta(days=28)
    prev = df[(df["start_time_utc"] >= one_y_ago_window_start) & (df["start_time_utc"] <= one_y_ago_window_end)]
    prev_km = prev["distance_m"].sum() / 1000
    return {"total_km": total_km, "total_hours": total_hours, "runs": runs,
            "last_4wk_km": last_4wk_km, "prev_year_4wk_km": prev_km}


def _pace_label(s: float) -> str:
    if pd.isna(s):
        return ""
    m, sec = divmod(int(s), 60)
    return f"{m}:{sec:02d}"


def fig_pace_scatter(df: pd.DataFrame) -> go.Figure:
    d = df.dropna(subset=["avg_pace_s_per_km"])
    fig = px.scatter(d, x="start_time_utc", y="avg_pace_s_per_km",
                     size="distance_m", color="avg_hr",
                     hover_data={"name": True, "activity_id": True, "distance_m": ":.0f"},
                     labels={"avg_pace_s_per_km": "Pace (s/km)", "start_time_utc": "Date"},
                     title="Pace per run (size=distance, color=avg HR)")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=450)
    return fig


def fig_pace_rolling_by_bucket(df: pd.DataFrame) -> go.Figure:
    d = df.dropna(subset=["avg_pace_s_per_km"]).sort_values("start_time_utc")
    if d.empty:
        return go.Figure()
    fig = go.Figure()
    for bucket_label in d["bucket"].dropna().unique():
        sub = d[d["bucket"] == bucket_label].copy()
        if len(sub) < 5:
            continue
        sub["roll_pace"] = sub["avg_pace_s_per_km"].rolling(min(30, len(sub)), min_periods=5).mean()
        fig.add_scatter(x=sub["start_time_utc"], y=sub["roll_pace"], name=str(bucket_label), mode="lines")
    fig.update_yaxes(autorange="reversed", title="Pace (s/km, rolling 30-run avg)")
    fig.update_layout(title="Rolling pace by distance bucket", height=400)
    return fig


def fig_aerobic_efficiency(df: pd.DataFrame, target_hr: float, tol: float = 3.0) -> go.Figure:
    d = df.dropna(subset=["avg_hr", "avg_pace_s_per_km"])
    d = d[(d["avg_hr"] >= target_hr - tol) & (d["avg_hr"] <= target_hr + tol)]
    if d.empty:
        return go.Figure().update_layout(title=f"Aerobic efficiency (no runs at HR {target_hr:.0f}±{tol:.0f})")
    monthly = (d.assign(month=d["start_time_utc"].dt.to_period("M").dt.start_time)
                .groupby("month")
                .agg(pace=("avg_pace_s_per_km", "mean"), n=("activity_id", "count"))
                .reset_index())
    monthly = monthly[monthly["n"] >= 3]
    fig = px.line(monthly, x="month", y="pace", markers=True,
                  title=f"Aerobic efficiency: pace at HR {target_hr:.0f} ± {tol:.0f}",
                  labels={"pace": "Pace (s/km)", "month": "Month"})
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=400)
    return fig


def fig_hr_zones_monthly(df: pd.DataFrame) -> go.Figure:
    if "hr_zones_seconds" not in df.columns:
        return go.Figure()
    rows = []
    for _, r in df.iterrows():
        z = r["hr_zones_seconds"] or {}
        if not z:
            continue
        rows.append({"month": r["start_time_utc"].to_period("M").start_time, **z})
    if not rows:
        return go.Figure()
    long_df = pd.DataFrame(rows).groupby("month", as_index=False).sum()
    z_cols = ["z1", "z2", "z3", "z4", "z5"]
    totals = long_df[z_cols].sum(axis=1).replace(0, 1)
    for c in z_cols:
        long_df[c] = long_df[c] / totals * 100
    fig = px.area(long_df.melt(id_vars="month", value_vars=z_cols, var_name="zone", value_name="pct"),
                  x="month", y="pct", color="zone",
                  title="HR zone distribution (monthly, % of moving time)",
                  labels={"pct": "% time"})
    fig.update_layout(height=400)
    return fig


def fig_hr_drift(df: pd.DataFrame) -> go.Figure:
    d = df.dropna(subset=["hr_drift_pct"])
    if d.empty:
        return go.Figure()
    monthly = (d.assign(month=d["start_time_utc"].dt.to_period("M").dt.start_time)
                .groupby("month", as_index=False)
                .agg(drift=("hr_drift_pct", "mean")))
    fig = px.line(monthly, x="month", y="drift", markers=True,
                  title="HR drift per run (monthly avg)",
                  labels={"drift": "Drift (fraction)"})
    fig.update_layout(height=350)
    return fig


PR_LABELS = ["1k", "5k", "10k", "21.1k", "42.2k"]


def pr_table(df: pd.DataFrame) -> pd.DataFrame:
    """Best time per (distance, year)."""
    if "best_efforts" not in df.columns:
        return pd.DataFrame()
    rows = []
    for _, r in df.iterrows():
        be = r["best_efforts"] or {}
        for label in PR_LABELS:
            v = be.get(label)
            if v is not None:
                rows.append({"year": int(r["start_time_utc"].year), "label": label, "seconds": float(v)})
    if not rows:
        return pd.DataFrame()
    long_df = pd.DataFrame(rows)
    best = long_df.groupby(["year", "label"], as_index=False)["seconds"].min()
    pivot = best.pivot(index="year", columns="label", values="seconds").reindex(columns=PR_LABELS)
    return pivot.sort_index()


def fig_pr_progression(prs: pd.DataFrame) -> go.Figure:
    if prs.empty:
        return go.Figure()
    long_df = prs.reset_index().melt(id_vars="year", var_name="label", value_name="seconds").dropna()
    fig = px.line(long_df, x="year", y="seconds", color="label", markers=True,
                  title="PR progression by year",
                  labels={"seconds": "Best time (s)"})
    fig.update_layout(height=400)
    return fig


def fig_long_runs_per_year(df: pd.DataFrame, threshold_m: float = 15000) -> go.Figure:
    d = df[df["distance_m"] >= threshold_m]
    by_year = d.groupby(d["start_time_utc"].dt.year).size().reset_index(name="count")
    by_year.columns = ["year", "count"]
    fig = px.bar(by_year, x="year", y="count", title=f"Long runs per year (≥ {threshold_m/1000:.0f} km)",
                 labels={"count": "# runs"})
    fig.update_layout(height=350)
    return fig


def fig_year_heatmap(df: pd.DataFrame, year: int) -> go.Figure:
    daily = (df[df["year"] == year]
             .groupby(df[df["year"] == year]["start_time_utc"].dt.date)
             ["distance_m"].sum() / 1000)
    if daily.empty:
        return go.Figure()
    full_year = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    daily = daily.reindex(full_year.date, fill_value=0)
    daily.index = pd.to_datetime(daily.index)
    df_h = pd.DataFrame({"date": daily.index, "km": daily.values})
    df_h["dow"] = df_h["date"].dt.weekday
    df_h["week"] = df_h["date"].dt.isocalendar().week
    # ISO week numbers wrap at year boundaries (e.g. Dec 31 may be ISO week 1
    # of the next year, Jan 1 may be ISO week 52 of the previous year), which
    # produces duplicate (dow, week) keys within a calendar year. Use
    # pivot_table+sum to merge these boundary cells rather than failing.
    pivot = df_h.pivot_table(index="dow", columns="week", values="km",
                             aggfunc="sum", fill_value=0)
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns, y=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        colorscale="Greens", showscale=True, hovertemplate="week %{x}, %{y}: %{z:.1f} km<extra></extra>",
    ))
    fig.update_layout(title=f"{year}", height=200, margin=dict(t=30, b=10))
    return fig


def streak_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"longest": 0, "current": 0}
    days = sorted(set(df["start_time_utc"].dt.date))
    longest = 0
    cur = 1
    for i in range(1, len(days)):
        if (days[i] - days[i-1]).days == 1:
            cur += 1
        else:
            longest = max(longest, cur)
            cur = 1
    longest = max(longest, cur)
    today = pd.Timestamp.utcnow().date()
    current = 0
    if days and (today - days[-1]).days <= 1:
        current = 1
        for i in range(len(days) - 1, 0, -1):
            if (days[i] - days[i-1]).days == 1:
                current += 1
            else:
                break
    return {"longest": longest, "current": current}


def fig_dow_histogram(df: pd.DataFrame) -> go.Figure:
    by = df.groupby(df["start_time_utc"].dt.dayofweek)["distance_m"].sum() / 1000
    by = by.reindex(range(7), fill_value=0)
    fig = px.bar(x=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], y=by.values,
                 labels={"x": "Day", "y": "km"}, title="Total km by day of week")
    fig.update_layout(height=350)
    return fig


def fig_hour_histogram(df: pd.DataFrame) -> go.Figure:
    by = df.groupby(df["start_time_utc"].dt.hour).size()
    by = by.reindex(range(24), fill_value=0)
    fig = px.bar(x=list(by.index), y=by.values, labels={"x": "Hour of day", "y": "Run count"},
                 title="When you actually run")
    fig.update_layout(height=350)
    return fig
