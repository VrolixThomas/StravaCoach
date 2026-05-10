from pathlib import Path
import pytest
import pandas as pd

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_fit_path() -> Path:
    return FIXTURES / "sample.fit.gz"


@pytest.fixture
def sample_gpx_path() -> Path:
    return FIXTURES / "sample.gpx"


@pytest.fixture
def sample_fit_uncompressed_path() -> Path:
    return FIXTURES / "sample_uncompressed.fit"


@pytest.fixture
def synthetic_stream() -> pd.DataFrame:
    """30-minute synthetic running stream at constant 5:00/km, HR 150."""
    n = 30 * 60 + 1  # 1 sample/sec for 30 min, inclusive endpoint → reaches 6000m
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01 10:00:00", periods=n, freq="1s", tz="UTC"),
        "distance": [i * (1000 / 300) for i in range(n)],  # 5:00/km = 3.333 m/s
        "speed": [1000 / 300] * n,
        "heart_rate": [150] * n,
        "cadence": [85] * n,
        "altitude": [50] * n,
        "position_lat": [50.85] * n,
        "position_long": [4.35] * n,
    })
