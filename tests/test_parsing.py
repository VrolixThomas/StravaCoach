from datetime import datetime, timezone
import pytest
from lib.parsing import parse_dutch_datetime


def test_parse_dutch_datetime_basic():
    assert parse_dutch_datetime("9 mei 2026, 00:03:01") == datetime(2026, 5, 9, 0, 3, 1, tzinfo=timezone.utc)


def test_parse_dutch_datetime_all_months():
    months = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
    for i, m in enumerate(months, start=1):
        got = parse_dutch_datetime(f"15 {m} 2024, 12:00:00")
        assert got.month == i, f"failed for {m}"


def test_parse_dutch_datetime_unknown_month_raises():
    with pytest.raises(ValueError, match="unknown month"):
        parse_dutch_datetime("1 zzz 2024, 00:00:00")


from pathlib import Path
from lib.parsing import load_activities_csv

FIX = Path(__file__).parent / "fixtures" / "mini_activities.csv"


def test_load_activities_csv_filters_to_runs():
    df = load_activities_csv(FIX)
    assert len(df) == 2
    assert set(df["activity_id"]) == {1001, 3003}


def test_load_activities_csv_renames_and_types():
    df = load_activities_csv(FIX).set_index("activity_id")
    row = df.loc[1001]
    assert row["distance_m"] == 7500.0
    assert row["moving_time_s"] == 1800
    assert row["avg_hr"] == 148
    assert row["fit_path"] == "activities/1001.fit.gz"
    assert row["start_time_utc"].tzinfo is not None


def test_load_activities_csv_handles_missing_optional_fields():
    df = load_activities_csv(FIX).set_index("activity_id")
    row = df.loc[3003]
    import math
    assert math.isnan(row["avg_hr"])
    assert math.isnan(row["perceived_effort"])


from lib.parsing import decode_fit_stream, decode_stream, decode_gpx_stream


def test_decode_fit_stream_returns_dataframe(sample_fit_path):
    df = decode_fit_stream(sample_fit_path)
    assert len(df) > 0
    assert "timestamp" in df.columns
    assert any(c in df.columns for c in ["distance", "speed", "heart_rate"])


def test_decode_fit_stream_lat_lon_in_degrees(sample_fit_path):
    df = decode_fit_stream(sample_fit_path)
    if "position_lat" in df.columns and df["position_lat"].notna().any():
        lat = df["position_lat"].dropna()
        assert lat.between(-90, 90).all()


def test_decode_fit_stream_handles_uncompressed_fit(sample_fit_uncompressed_path):
    df = decode_fit_stream(sample_fit_uncompressed_path)
    assert len(df) > 0
    assert "timestamp" in df.columns


def test_decode_gpx_stream_returns_dataframe(sample_gpx_path):
    df = decode_gpx_stream(sample_gpx_path)
    assert len(df) > 0
    assert "timestamp" in df.columns
    assert "position_lat" in df.columns


def test_decode_gpx_stream_distance_monotonic(sample_gpx_path):
    df = decode_gpx_stream(sample_gpx_path)
    assert "distance" in df.columns
    d = df["distance"].dropna()
    if len(d) >= 2:
        diffs = d.diff().dropna()
        assert (diffs >= 0).all(), "cumulative distance must be non-decreasing"


def test_decode_gpx_stream_lat_lon_in_degrees(sample_gpx_path):
    df = decode_gpx_stream(sample_gpx_path)
    if "position_lat" in df.columns and df["position_lat"].notna().any():
        assert df["position_lat"].dropna().between(-90, 90).all()


def test_decode_stream_dispatches_to_fit(sample_fit_path):
    df = decode_stream(sample_fit_path)
    assert len(df) > 0


def test_decode_stream_dispatches_to_gpx(sample_gpx_path):
    df = decode_stream(sample_gpx_path)
    assert len(df) > 0


def test_decode_stream_unsupported_raises(tmp_path):
    p = tmp_path / "x.tcx"
    p.write_text("hello")
    import pytest
    with pytest.raises(ValueError, match="unsupported"):
        decode_stream(p)
