import pandas as pd
import pytest
from lib.metrics import is_indoor, avg_pace_s_per_km, low_quality


def test_is_indoor_true_when_no_lat(synthetic_stream):
    s = synthetic_stream.copy()
    s["position_lat"] = pd.NA
    assert is_indoor(s) is True


def test_is_indoor_false_with_gps(synthetic_stream):
    assert is_indoor(synthetic_stream) is False


def test_is_indoor_true_when_lat_column_missing(synthetic_stream):
    s = synthetic_stream.drop(columns=["position_lat", "position_long"])
    assert is_indoor(s) is True


def test_avg_pace_basic():
    assert avg_pace_s_per_km(distance_m=6000, moving_time_s=1800) == pytest.approx(300.0)


def test_avg_pace_zero_distance_is_nan():
    import math
    assert math.isnan(avg_pace_s_per_km(distance_m=0, moving_time_s=600))


def test_low_quality_short_distance():
    assert low_quality(distance_m=400, moving_time_s=600) is True


def test_low_quality_short_time():
    assert low_quality(distance_m=2000, moving_time_s=60) is True


def test_low_quality_normal_run():
    assert low_quality(distance_m=5000, moving_time_s=1500) is False


from lib.metrics import compute_splits


def test_compute_splits_constant_pace(synthetic_stream):
    splits = compute_splits(synthetic_stream)
    assert len(splits) == 6
    for s in splits:
        assert s["pace_s_per_km"] == pytest.approx(300.0, abs=2.0)
        assert s["avg_hr"] == pytest.approx(150.0, abs=0.1)


def test_compute_splits_empty_stream_returns_empty():
    df = pd.DataFrame({"timestamp": [], "distance": [], "heart_rate": []})
    assert compute_splits(df) == []


def test_compute_splits_no_distance_column_returns_empty():
    df = pd.DataFrame({"timestamp": [pd.Timestamp("2024-01-01", tz="UTC")]})
    assert compute_splits(df) == []


from lib.metrics import hr_zones_seconds


def test_hr_zones_constant_z3():
    s = pd.DataFrame({"heart_rate": [150] * 600})
    z = hr_zones_seconds(s, lthr=170, sample_hz=1)
    assert z["z2"] == 600
    assert z["z1"] == 0
    assert z["z3"] == 0


def test_hr_zones_split_three_zones():
    hrs = [120] * 100 + [160] * 200 + [180] * 300
    s = pd.DataFrame({"heart_rate": hrs})
    z = hr_zones_seconds(s, lthr=170, sample_hz=1)
    assert z["z1"] == 100
    assert z["z3"] == 200
    assert z["z5"] == 300


def test_hr_zones_handles_missing_hr_column():
    s = pd.DataFrame({"timestamp": []})
    assert hr_zones_seconds(s, lthr=170) == {"z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0}


from lib.metrics import hr_drift_pct


def test_hr_drift_no_drift():
    s = pd.DataFrame({"heart_rate": [150] * 1000})
    assert hr_drift_pct(s) == pytest.approx(0.0, abs=0.001)


def test_hr_drift_positive():
    s = pd.DataFrame({"heart_rate": [140] * 500 + [154] * 500})
    assert hr_drift_pct(s) == pytest.approx(0.10, abs=0.001)


def test_hr_drift_no_hr_returns_nan():
    import math
    s = pd.DataFrame({"timestamp": []})
    assert math.isnan(hr_drift_pct(s))


from lib.metrics import best_efforts


def test_best_efforts_constant_pace(synthetic_stream):
    be = best_efforts(synthetic_stream)
    assert be["1k"] == pytest.approx(300.0, abs=2.0)
    assert be["5k"] == pytest.approx(1500.0, abs=2.0)
    assert be["10k"] is None


def test_best_efforts_empty():
    assert best_efforts(pd.DataFrame({"timestamp": [], "distance": []})) == {
        "1k": None, "5k": None, "10k": None, "21.1k": None, "42.2k": None
    }
