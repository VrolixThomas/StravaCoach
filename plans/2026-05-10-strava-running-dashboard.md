# Strava Running Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Streamlit dashboard over a Strava bulk export (1008 running activities), showing volume, pace/HR efficiency, PRs, and consistency over years.

**Architecture:** One-shot ETL (`prepare.py`) parses `activities.csv` (Dutch locale) and 1008 `.fit.gz` files into two parquet artifacts (`activities.parquet` summary + `streams/` partitioned dataset). A Streamlit app reads those parquets and renders 4 tabbed views with sidebar filters.

**Tech Stack:** Python 3.11+, Streamlit, pandas, pyarrow, plotly, fitparse, pytest.

**Spec:** `/Users/Werk/Documents/strava-dashboard/specs/2026-05-10-strava-running-dashboard-design.md`

**Project root:** `/Users/Werk/Documents/strava-dashboard/` — outside any other repo. **No git commits in this plan** (per user instruction). Code is self-contained; user may `git init` later.

---

## File map

| File | Responsibility |
|---|---|
| `requirements.txt` | Pinned deps |
| `README.md` | How to run |
| `lib/__init__.py` | Marker |
| `lib/parsing.py` | Dutch-date parser, activities.csv loader, FIT decode, semicircle conversion |
| `lib/metrics.py` | Indoor flag, splits, HR zones, HR drift, best efforts, derived columns |
| `prepare.py` | ETL orchestrator: loads csv → decodes FITs → writes parquets, incremental |
| `lib/views.py` | Plotly chart builders (one function per chart) |
| `app.py` | Streamlit entry: sidebar filters + 4 tabs |
| `tests/__init__.py` | Marker |
| `tests/conftest.py` | Shared fixtures (synthetic streams, sample FIT path) |
| `tests/fixtures/sample.fit.gz` | One real FIT copied from the export for parser tests |
| `tests/test_parsing.py` | Unit tests for parsing.py |
| `tests/test_metrics.py` | Unit tests for metrics.py |

`data/` and `strava/` (symlink) are runtime artifacts — created by `prepare.py` or task 1, never tracked.

---

### Task 1: Bootstrap project skeleton

**Files:**
- Create: `/Users/Werk/Documents/strava-dashboard/requirements.txt`
- Create: `/Users/Werk/Documents/strava-dashboard/README.md`
- Create: `/Users/Werk/Documents/strava-dashboard/lib/__init__.py`
- Create: `/Users/Werk/Documents/strava-dashboard/tests/__init__.py`
- Create: `/Users/Werk/Documents/strava-dashboard/tests/conftest.py`
- Create symlink: `/Users/Werk/Documents/strava-dashboard/strava` → `/Users/Werk/Documents/provider-service-worktrees/testing/strava`
- Copy: `/Users/Werk/Documents/strava-dashboard/tests/fixtures/sample.fit.gz` from one small export FIT

- [ ] **Step 1: Create dirs and venv**

```bash
cd /Users/Werk/Documents/strava-dashboard
mkdir -p lib tests/fixtures data
python3.11 -m venv .venv
source .venv/bin/activate
```

Expected: `.venv/` exists, prompt shows `(.venv)`.

- [ ] **Step 2: Write `requirements.txt`**

```
streamlit==1.39.0
pandas==2.2.3
pyarrow==17.0.0
plotly==5.24.1
fitparse==1.2.0
tqdm==4.66.5
pytest==8.3.3
```

Run: `pip install -r requirements.txt`
Expected: clean install, no errors.

- [ ] **Step 3: Symlink raw export and copy a sample FIT**

```bash
ln -s /Users/Werk/Documents/provider-service-worktrees/testing/strava /Users/Werk/Documents/strava-dashboard/strava
# Pick the smallest .fit.gz to keep fixture light:
SMALLEST=$(ls -S /Users/Werk/Documents/strava-dashboard/strava/activities/*.fit.gz | tail -1)
cp "$SMALLEST" /Users/Werk/Documents/strava-dashboard/tests/fixtures/sample.fit.gz
echo "Sample: $SMALLEST"
```

Expected: symlink resolves, fixture copied. Note the activity id in the filename — used in tests later.

- [ ] **Step 4: Write `lib/__init__.py` and `tests/__init__.py`** (empty files)

```bash
touch /Users/Werk/Documents/strava-dashboard/lib/__init__.py /Users/Werk/Documents/strava-dashboard/tests/__init__.py
```

- [ ] **Step 5: Write `tests/conftest.py`** with shared fixtures

```python
from pathlib import Path
import pytest
import pandas as pd

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_fit_path() -> Path:
    return FIXTURES / "sample.fit.gz"


@pytest.fixture
def synthetic_stream() -> pd.DataFrame:
    """30-minute synthetic running stream at constant 5:00/km, HR 150."""
    n = 30 * 60  # 1 sample/sec for 30 min
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
```

- [ ] **Step 6: Write `README.md`**

```markdown
# Strava Running Dashboard

Local-only dashboard over a Strava bulk export.

## Setup

    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

The `strava/` symlink should already point at the unzipped export dir.

## Run

    python prepare.py            # one-shot ETL → data/
    streamlit run app.py         # opens browser

## Tests

    pytest
```

- [ ] **Step 7: Verify skeleton**

Run: `pytest -q`
Expected: `0 tests collected` (no failure — pytest happy with empty test files).

---

### Task 2: Dutch date parser

**Files:**
- Create: `/Users/Werk/Documents/strava-dashboard/lib/parsing.py`
- Create: `/Users/Werk/Documents/strava-dashboard/tests/test_parsing.py`

- [ ] **Step 1: Write the failing test**

`tests/test_parsing.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parsing.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_dutch_datetime'`.

- [ ] **Step 3: Implement parser**

`lib/parsing.py`:

```python
from datetime import datetime, timezone
import re

_MONTHS = {
    "jan": 1, "feb": 2, "mrt": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}

_DATE_RE = re.compile(r"^\s*(\d{1,2})\s+([a-z]{3})\s+(\d{4}),\s+(\d{2}):(\d{2}):(\d{2})\s*$")


def parse_dutch_datetime(s: str) -> datetime:
    m = _DATE_RE.match(s.lower())
    if not m:
        raise ValueError(f"bad date format: {s!r}")
    day, mon_abbr, year, hh, mm, ss = m.groups()
    if mon_abbr not in _MONTHS:
        raise ValueError(f"unknown month: {mon_abbr!r}")
    return datetime(int(year), _MONTHS[mon_abbr], int(day), int(hh), int(mm), int(ss), tzinfo=timezone.utc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parsing.py -v`
Expected: PASS — 3 tests green.

---

### Task 3: activities.csv loader

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/parsing.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/tests/test_parsing.py`
- Create: `/Users/Werk/Documents/strava-dashboard/tests/fixtures/mini_activities.csv`

- [ ] **Step 1: Create a tiny csv fixture** with 3 rows (1 run, 1 ride, 1 run with empty optional fields).

`tests/fixtures/mini_activities.csv`:

```csv
Activiteits-ID,Datum van activiteit,Naam activiteit,Activiteitstype,Beschrijving van activiteit,Beweegtijd,Verstreken tijd,Afstand,Totale stijging,Gemiddelde hartslag,Max. hartslag,Gemiddelde cadans,Max. cadans,Calorieën,Bestandsnaam,Ervaren inspanning,Trainingsbelasting
1001,"9 mei 2026, 19:00:00",Avondloop,Hardloopsessie,,1800,1900,7500.0,80.0,148,172,82,95,520,activities/1001.fit.gz,6,55
2002,"8 mei 2026, 10:00:00",Ochtendrit,Fietsrit,,3600,3650,30000.0,300.0,135,165,,,800,activities/2002.fit.gz,,
3003,"7 mei 2026, 22:30:00",Nachtloop,Hardloopsessie,,1200,1220,5000.0,30.0,,,,,330,activities/3003.fit.gz,,
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_parsing.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_parsing.py -v`
Expected: 3 new tests FAIL with `ImportError: cannot import name 'load_activities_csv'`.

- [ ] **Step 4: Implement loader**

Append to `lib/parsing.py`:

```python
from pathlib import Path
import csv
import math
import pandas as pd

_RUN_TYPE = "Hardloopsessie"

# Source-Dutch → target-English column map. Keep only what we use.
_COL_MAP = {
    "Activiteits-ID": "activity_id",
    "Datum van activiteit": "_start_time_raw",
    "Naam activiteit": "name",
    "Beweegtijd": "moving_time_s",
    "Verstreken tijd": "elapsed_time_s",
    "Afstand": "distance_m",
    "Totale stijging": "elev_gain_m",
    "Gemiddelde hartslag": "avg_hr",
    "Max. hartslag": "max_hr",
    "Gemiddelde cadans": "avg_cadence",
    "Max. cadans": "max_cadence",
    "Calorieën": "calories",
    "Bestandsnaam": "fit_path",
    "Ervaren inspanning": "perceived_effort",
    "Trainingsbelasting": "training_load",
}

_NUMERIC_COLS = {
    "moving_time_s", "elapsed_time_s", "distance_m", "elev_gain_m",
    "avg_hr", "max_hr", "avg_cadence", "max_cadence", "calories",
    "perceived_effort", "training_load",
}


def _to_float(v: str) -> float:
    if v is None or v == "":
        return math.nan
    return float(v)


def load_activities_csv(path: Path) -> pd.DataFrame:
    """Load Strava activities.csv, filter to runs, rename to snake_case."""
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # First occurrence wins — the export has duplicate header names for some metrics.
        idx = {}
        for i, h in enumerate(header):
            if h in _COL_MAP and h not in idx:
                idx[h] = i
        type_col = header.index("Activiteitstype")

        for row in reader:
            if row[type_col] != _RUN_TYPE:
                continue
            out = {target: row[idx[src]] if src in idx else "" for src, target in _COL_MAP.items()}
            rows.append(out)

    df = pd.DataFrame(rows)
    df["activity_id"] = df["activity_id"].astype("int64")
    df["start_time_utc"] = df["_start_time_raw"].map(parse_dutch_datetime)
    df = df.drop(columns=["_start_time_raw"])
    for c in _NUMERIC_COLS:
        if c in df.columns:
            df[c] = df[c].map(_to_float)
    return df
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_parsing.py -v`
Expected: 6 tests PASS total.

---

### Task 4: FIT stream decoder

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/parsing.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/tests/test_parsing.py`

- [ ] **Step 1: Write failing tests** using the real fixture FIT

Append to `tests/test_parsing.py`:

```python
from lib.parsing import decode_fit_stream


def test_decode_fit_stream_returns_dataframe(sample_fit_path):
    df = decode_fit_stream(sample_fit_path)
    assert len(df) > 0
    assert "timestamp" in df.columns
    # At least one of these movement columns should exist
    assert any(c in df.columns for c in ["distance", "speed", "heart_rate"])


def test_decode_fit_stream_lat_lon_in_degrees(sample_fit_path):
    df = decode_fit_stream(sample_fit_path)
    if "position_lat" in df.columns and df["position_lat"].notna().any():
        # Belgium-ish bounds; sanity check semicircle → degrees conversion
        lat = df["position_lat"].dropna()
        assert lat.between(-90, 90).all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parsing.py -v -k decode`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement decoder**

Append to `lib/parsing.py`:

```python
import gzip
from io import BytesIO
import fitparse

_SEMI_TO_DEG = 180.0 / 2**31

_RECORD_FIELDS = (
    "timestamp", "position_lat", "position_long", "distance",
    "speed", "heart_rate", "cadence", "altitude", "power",
)


def decode_fit_stream(path: Path) -> pd.DataFrame:
    """Decode a .fit.gz file's `record` messages into a DataFrame."""
    with gzip.open(path, "rb") as f:
        raw = f.read()
    fit = fitparse.FitFile(BytesIO(raw))
    rows = []
    for msg in fit.get_messages("record"):
        d = {f.name: f.value for f in msg.fields if f.name in _RECORD_FIELDS}
        rows.append(d)
    df = pd.DataFrame(rows)
    if "position_lat" in df.columns:
        df["position_lat"] = df["position_lat"] * _SEMI_TO_DEG
    if "position_long" in df.columns:
        df["position_long"] = df["position_long"] * _SEMI_TO_DEG
    # Drop columns that are entirely null
    df = df.dropna(axis=1, how="all")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parsing.py -v -k decode`
Expected: PASS.

---

### Task 5: Indoor detection + per-activity derived columns (cheap ones)

**Files:**
- Create: `/Users/Werk/Documents/strava-dashboard/lib/metrics.py`
- Create: `/Users/Werk/Documents/strava-dashboard/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

`tests/test_metrics.py`:

```python
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
    # 30:00 over 6 km → 5:00/km = 300 s/km
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement helpers**

`lib/metrics.py`:

```python
import math
import pandas as pd


def is_indoor(stream: pd.DataFrame) -> bool:
    if "position_lat" not in stream.columns:
        return True
    return not stream["position_lat"].notna().any()


def avg_pace_s_per_km(distance_m: float, moving_time_s: float) -> float:
    if not distance_m or distance_m <= 0:
        return math.nan
    return moving_time_s / (distance_m / 1000.0)


def low_quality(distance_m: float, moving_time_s: float) -> bool:
    return distance_m < 500 or moving_time_s < 120
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v`
Expected: 8 PASS.

---

### Task 6: 1-km splits

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/metrics.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from lib.metrics import compute_splits


def test_compute_splits_constant_pace(synthetic_stream):
    # 30 min @ 5:00/km, distance reaches 6 km exactly
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metrics.py -v -k splits`
Expected: FAIL.

- [ ] **Step 3: Implement `compute_splits`**

Append to `lib/metrics.py`:

```python
def compute_splits(stream: pd.DataFrame, km: float = 1.0) -> list[dict]:
    """Per-km splits: list of {km, pace_s_per_km, avg_hr}."""
    if "distance" not in stream.columns or "timestamp" not in stream.columns or len(stream) == 0:
        return []
    s = stream.dropna(subset=["distance", "timestamp"]).sort_values("timestamp").reset_index(drop=True)
    if len(s) < 2:
        return []
    splits: list[dict] = []
    bucket_m = km * 1000.0
    bucket_idx = 1
    bucket_start_i = 0
    for i in range(len(s)):
        if s.loc[i, "distance"] >= bucket_idx * bucket_m:
            t0 = s.loc[bucket_start_i, "timestamp"]
            t1 = s.loc[i, "timestamp"]
            elapsed_s = (t1 - t0).total_seconds()
            avg_hr = (
                s.loc[bucket_start_i:i, "heart_rate"].mean()
                if "heart_rate" in s.columns else math.nan
            )
            splits.append({
                "km": bucket_idx,
                "pace_s_per_km": elapsed_s / km,
                "avg_hr": float(avg_hr) if not pd.isna(avg_hr) else math.nan,
            })
            bucket_start_i = i
            bucket_idx += 1
    return splits
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v -k splits`
Expected: PASS.

---

### Task 7: HR zones

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/metrics.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from lib.metrics import hr_zones_seconds


def test_hr_zones_constant_z3():
    # LTHR 170, HR 150 → 150/170 = 0.882 → z2 (0.81–0.89)
    s = pd.DataFrame({"heart_rate": [150] * 600})  # 600 samples ≈ 600 s if 1Hz
    z = hr_zones_seconds(s, lthr=170, sample_hz=1)
    assert z["z2"] == 600
    assert z["z1"] == 0
    assert z["z3"] == 0


def test_hr_zones_split_three_zones():
    # 100 samples z1, 200 z3, 300 z5
    hrs = [120] * 100 + [160] * 200 + [180] * 300  # at LTHR 170: 120/170=.706, 160/170=.941, 180/170=1.06
    s = pd.DataFrame({"heart_rate": hrs})
    z = hr_zones_seconds(s, lthr=170, sample_hz=1)
    assert z["z1"] == 100
    assert z["z3"] == 200
    assert z["z5"] == 300


def test_hr_zones_handles_missing_hr_column():
    s = pd.DataFrame({"timestamp": []})
    assert hr_zones_seconds(s, lthr=170) == {"z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metrics.py -v -k zones`
Expected: FAIL.

- [ ] **Step 3: Implement `hr_zones_seconds`**

Append to `lib/metrics.py`:

```python
_ZONE_BOUNDS = (0.81, 0.89, 0.94, 1.00)  # upper bounds for z1..z4; z5 is open above


def hr_zones_seconds(stream: pd.DataFrame, lthr: float, sample_hz: float = 1.0) -> dict[str, int]:
    z = {f"z{i}": 0 for i in range(1, 6)}
    if "heart_rate" not in stream.columns or len(stream) == 0:
        return z
    hr = stream["heart_rate"].dropna() / lthr
    counts = [0, 0, 0, 0, 0]
    for r in hr:
        if r < _ZONE_BOUNDS[0]:
            counts[0] += 1
        elif r < _ZONE_BOUNDS[1]:
            counts[1] += 1
        elif r < _ZONE_BOUNDS[2]:
            counts[2] += 1
        elif r < _ZONE_BOUNDS[3]:
            counts[3] += 1
        else:
            counts[4] += 1
    return {f"z{i+1}": int(c / sample_hz) for i, c in enumerate(counts)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v -k zones`
Expected: PASS.

---

### Task 8: HR drift

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/metrics.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from lib.metrics import hr_drift_pct


def test_hr_drift_no_drift():
    s = pd.DataFrame({"heart_rate": [150] * 1000})
    assert hr_drift_pct(s) == pytest.approx(0.0, abs=0.001)


def test_hr_drift_positive():
    # 1st half avg 140, 2nd half avg 154 → drift = (154-140)/140 = 0.10
    s = pd.DataFrame({"heart_rate": [140] * 500 + [154] * 500})
    assert hr_drift_pct(s) == pytest.approx(0.10, abs=0.001)


def test_hr_drift_no_hr_returns_nan():
    import math
    s = pd.DataFrame({"timestamp": []})
    assert math.isnan(hr_drift_pct(s))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metrics.py -v -k drift`
Expected: FAIL.

- [ ] **Step 3: Implement `hr_drift_pct`**

Append to `lib/metrics.py`:

```python
def hr_drift_pct(stream: pd.DataFrame) -> float:
    if "heart_rate" not in stream.columns:
        return math.nan
    hr = stream["heart_rate"].dropna().reset_index(drop=True)
    if len(hr) < 4:
        return math.nan
    mid = len(hr) // 2
    first = hr.iloc[:mid].mean()
    second = hr.iloc[mid:].mean()
    if first == 0:
        return math.nan
    return float((second - first) / first)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v -k drift`
Expected: PASS.

---

### Task 9: Best efforts (rolling-window PRs)

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/metrics.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from lib.metrics import best_efforts


def test_best_efforts_constant_pace(synthetic_stream):
    # 6 km @ 5:00/km
    be = best_efforts(synthetic_stream)
    assert be["1k"] == pytest.approx(300.0, abs=2.0)
    assert be["5k"] == pytest.approx(1500.0, abs=2.0)
    assert be["10k"] is None  # didn't reach 10k


def test_best_efforts_empty():
    assert best_efforts(pd.DataFrame({"timestamp": [], "distance": []})) == {
        "1k": None, "5k": None, "10k": None, "21.1k": None, "42.2k": None
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metrics.py -v -k best_efforts`
Expected: FAIL.

- [ ] **Step 3: Implement `best_efforts`**

Append to `lib/metrics.py`:

```python
import numpy as np

_PR_DISTANCES_M = {"1k": 1000, "5k": 5000, "10k": 10000, "21.1k": 21097.5, "42.2k": 42195.0}


def best_efforts(stream: pd.DataFrame) -> dict[str, float | None]:
    """Fastest rolling-window time for each PR distance the run reaches."""
    out: dict[str, float | None] = {k: None for k in _PR_DISTANCES_M}
    if "distance" not in stream.columns or "timestamp" not in stream.columns or len(stream) < 2:
        return out
    s = stream.dropna(subset=["distance", "timestamp"]).sort_values("timestamp").reset_index(drop=True)
    if len(s) < 2:
        return out
    dist = s["distance"].to_numpy()
    ts = s["timestamp"].astype("int64").to_numpy() / 1e9  # epoch seconds
    total_d = dist[-1] - dist[0]
    for label, d in _PR_DISTANCES_M.items():
        if total_d < d:
            continue
        best = math.inf
        j = 0
        for i in range(len(dist)):
            while j < len(dist) and dist[j] - dist[i] < d:
                j += 1
            if j >= len(dist):
                break
            # Linear interpolation between j-1 and j to land exactly on `d`.
            frac = (d - (dist[j-1] - dist[i])) / (dist[j] - dist[j-1]) if dist[j] != dist[j-1] else 0.0
            t_end = ts[j-1] + frac * (ts[j] - ts[j-1])
            elapsed = t_end - ts[i]
            if elapsed > 0 and elapsed < best:
                best = elapsed
        out[label] = float(best) if best < math.inf else None
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v -k best_efforts`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: all tests PASS (Tasks 2–9 covered).

---

### Task 10: ETL orchestrator (`prepare.py`)

**Files:**
- Create: `/Users/Werk/Documents/strava-dashboard/prepare.py`

This task is integration-level — verified by running it against the real export rather than unit tests.

- [ ] **Step 1: Write `prepare.py`**

```python
"""One-shot ETL: activities.csv + .fit.gz → data/activities.parquet + data/streams/."""
from __future__ import annotations
from pathlib import Path
import argparse
import logging
import sys
from datetime import datetime, timezone

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds
from tqdm import tqdm

from lib.parsing import load_activities_csv, decode_fit_stream
from lib.metrics import (
    is_indoor, avg_pace_s_per_km, low_quality,
    compute_splits, hr_zones_seconds, hr_drift_pct, best_efforts,
)

ROOT = Path(__file__).parent
STRAVA = ROOT / "strava"
DATA = ROOT / "data"
ACTIVITIES_PARQUET = DATA / "activities.parquet"
STREAMS_DIR = DATA / "streams"
ERROR_LOG = DATA / "parse_errors.log"
SCHEMA_VERSION = 1


def _zone_lthr(activities_df: pd.DataFrame, override: float | None) -> float:
    if override is not None:
        return override
    max_hrs = activities_df["max_hr"].dropna()
    if max_hrs.empty:
        return 180.0
    return float(max_hrs.max() * 0.95)


def _process_activity(row: pd.Series, lthr: float) -> tuple[dict, pd.DataFrame | None, str | None]:
    fit_path = STRAVA / row["fit_path"]
    if not fit_path.exists() or not str(fit_path).endswith(".fit.gz"):
        return row.to_dict(), None, f"skip non-fit.gz or missing: {fit_path.name}"
    try:
        stream = decode_fit_stream(fit_path)
    except Exception as e:
        return row.to_dict(), None, f"decode failed: {e}"
    enriched = row.to_dict()
    enriched["indoor"] = is_indoor(stream)
    enriched["avg_pace_s_per_km"] = avg_pace_s_per_km(row["distance_m"], row["moving_time_s"])
    enriched["low_quality"] = low_quality(row["distance_m"], row["moving_time_s"])
    enriched["splits"] = compute_splits(stream)
    enriched["hr_zones_seconds"] = hr_zones_seconds(stream, lthr=lthr)
    enriched["hr_drift_pct"] = hr_drift_pct(stream)
    enriched["best_efforts"] = best_efforts(stream)
    stream_out = stream.copy()
    stream_out["activity_id"] = row["activity_id"]
    stream_out["year"] = row["start_time_utc"].year
    return enriched, stream_out, None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lthr", type=float, default=None, help="Override LTHR for HR-zone calc")
    p.add_argument("--rebuild-zones", action="store_true",
                   help="Recompute hr_zones_seconds against existing parquet without re-parsing FITs")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)

    activities_csv = STRAVA / "activities.csv"
    if not activities_csv.exists():
        print(f"FATAL: {activities_csv} not found. Is the symlink set up?", file=sys.stderr)
        return 1

    df = load_activities_csv(activities_csv)
    if df.empty:
        print("FATAL: zero runs after filter — wrong activity-type filter?", file=sys.stderr)
        return 1
    logging.info("loaded %d runs from csv", len(df))

    lthr = _zone_lthr(df, args.lthr)
    logging.info("using LTHR=%.1f", lthr)

    if args.rebuild_zones:
        return _rebuild_zones(lthr)

    # Incremental: skip ids already in parquet.
    existing_ids: set[int] = set()
    if ACTIVITIES_PARQUET.exists():
        try:
            existing_ids = set(pd.read_parquet(ACTIVITIES_PARQUET, columns=["activity_id"])["activity_id"])
        except Exception:
            pass
    todo = df[~df["activity_id"].isin(existing_ids)]
    logging.info("processing %d new runs (%d already done)", len(todo), len(existing_ids))

    enriched_rows: list[dict] = []
    stream_frames: list[pd.DataFrame] = []
    failed = 0
    with open(ERROR_LOG, "a", encoding="utf-8") as elog:
        elog.write(f"\n=== prepare run {datetime.now(timezone.utc).isoformat()} ===\n")
        for _, row in tqdm(todo.iterrows(), total=len(todo), desc="parsing"):
            enriched, stream_out, err = _process_activity(row, lthr)
            if err:
                failed += 1
                elog.write(f"{row['activity_id']}: {err}\n")
                continue
            enriched_rows.append(enriched)
            if stream_out is not None and len(stream_out) > 0:
                stream_frames.append(stream_out)

    if enriched_rows:
        new_df = pd.DataFrame(enriched_rows)
        if ACTIVITIES_PARQUET.exists():
            old = pd.read_parquet(ACTIVITIES_PARQUET)
            combined = pd.concat([old, new_df], ignore_index=True)
        else:
            combined = new_df
        combined = combined.drop_duplicates(subset=["activity_id"], keep="last")
        table = pa.Table.from_pandas(combined, preserve_index=False)
        table = table.replace_schema_metadata({**(table.schema.metadata or {}), b"schema_version": str(SCHEMA_VERSION).encode()})
        pq.write_table(table, ACTIVITIES_PARQUET)

    if stream_frames:
        all_streams = pd.concat(stream_frames, ignore_index=True)
        STREAMS_DIR.mkdir(parents=True, exist_ok=True)
        ds.write_dataset(
            pa.Table.from_pandas(all_streams, preserve_index=False),
            base_dir=str(STREAMS_DIR),
            format="parquet",
            partitioning=ds.partitioning(pa.schema([("year", pa.int32())]), flavor="hive"),
            existing_data_behavior="overwrite_or_ignore",
        )

    final_df = pd.read_parquet(ACTIVITIES_PARQUET) if ACTIVITIES_PARQUET.exists() else pd.DataFrame()
    print()
    print(f"parsed={len(enriched_rows)} skipped={len(existing_ids)} failed={failed}")
    if not final_df.empty:
        total_km = final_df["distance_m"].sum() / 1000
        print(f"total runs in parquet: {len(final_df)}")
        print(f"date range: {final_df['start_time_utc'].min()} → {final_df['start_time_utc'].max()}")
        print(f"total km: {total_km:.1f}")
    return 0


def _rebuild_zones(lthr: float) -> int:
    """Recompute hr_zones_seconds from existing streams parquet without re-parsing FITs."""
    if not ACTIVITIES_PARQUET.exists() or not STREAMS_DIR.exists():
        print("FATAL: no existing parquet to rebuild against.", file=sys.stderr)
        return 1
    activities = pd.read_parquet(ACTIVITIES_PARQUET)
    streams_ds = ds.dataset(str(STREAMS_DIR), format="parquet")
    new_zones: dict[int, dict] = {}
    for aid in tqdm(activities["activity_id"], desc="rebuild zones"):
        sub = streams_ds.to_table(filter=ds.field("activity_id") == aid).to_pandas()
        new_zones[int(aid)] = hr_zones_seconds(sub, lthr=lthr)
    activities["hr_zones_seconds"] = activities["activity_id"].map(new_zones)
    pq.write_table(pa.Table.from_pandas(activities, preserve_index=False), ACTIVITIES_PARQUET)
    print(f"rebuilt zones for {len(activities)} runs at LTHR={lthr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: First-run smoke test on the real export**

Run from `/Users/Werk/Documents/strava-dashboard`:

```bash
source .venv/bin/activate
python prepare.py
```

Expected:
- Progress bar reaches 1008/1008.
- Final summary prints `parsed=N skipped=0 failed=K` where K is small (only the 1 .gpx file).
- `data/activities.parquet` exists, ~1008 rows.
- `data/streams/year=YYYY/...parquet` directories exist.
- `data/parse_errors.log` exists, contains failures (expect ≥1 for the .gpx file).

- [ ] **Step 3: Idempotency smoke test**

Run again: `python prepare.py`

Expected: `parsed=0 skipped=~1008 failed=0`. Confirms incremental skip works.

- [ ] **Step 4: Inspect activities parquet**

```bash
python -c "import pandas as pd; df = pd.read_parquet('data/activities.parquet'); print(df.shape); print(df[['activity_id','distance_m','avg_pace_s_per_km','indoor','low_quality']].head()); print(df.dtypes)"
```

Expected: ~1008 rows, no errors, sensible numbers (distance > 0, pace 200–600 s/km for runs).

---

### Task 11: Streamlit app skeleton + sidebar filters

**Files:**
- Create: `/Users/Werk/Documents/strava-dashboard/app.py`

- [ ] **Step 1: Write `app.py` skeleton**

```python
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
        st.info("Volume views — to be filled in Task 12.")
    with tab2:
        st.info("Pace/HR views — to be filled in Task 13.")
    with tab3:
        st.info("PR views — to be filled in Task 14.")
    with tab4:
        st.info("Calendar views — to be filled in Task 15.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test**

Run: `streamlit run app.py`
Expected:
- Browser opens. Title "Running Dashboard".
- Sidebar shows date slider, year multiselect, bucket multiselect, two toggles.
- Caption shows total filter count e.g. "1008 runs match current filters (of 1008 total)."
- Four empty tabs render placeholder text.
- Toggling filters changes the count.

Stop the dev server with Ctrl-C when done.

---

### Task 12: Tab 1 — Volume views

**Files:**
- Create: `/Users/Werk/Documents/strava-dashboard/lib/views.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/app.py`

- [ ] **Step 1: Write `lib/views.py` with volume builders**

```python
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
```

- [ ] **Step 2: Wire into `app.py`** — replace tab1 placeholder

In `app.py`, replace:

```python
    with tab1:
        st.info("Volume views — to be filled in Task 12.")
```

with:

```python
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
```

- [ ] **Step 3: Smoke test**

Run: `streamlit run app.py`
Expected: Volume tab shows 4 KPI cards + 3 charts. Adjust sidebar filters; charts update.

---

### Task 13: Tab 2 — Pace & HR efficiency

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/views.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/app.py`

- [ ] **Step 1: Add chart builders to `lib/views.py`**

Append to `lib/views.py`:

```python
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
    fig.update_yaxes(autorange="reversed")  # faster pace = lower number, but visually higher
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
```

- [ ] **Step 2: Wire tab 2** in `app.py`

Replace:

```python
    with tab2:
        st.info("Pace/HR views — to be filled in Task 13.")
```

with:

```python
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
```

- [ ] **Step 3: Smoke test**

Run: `streamlit run app.py`
Expected: Pace & HR tab renders 5 charts. Slider updates aerobic-efficiency chart. No exceptions in the terminal.

---

### Task 14: Tab 3 — Personal Records by year

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/views.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/app.py`

- [ ] **Step 1: Add PR builders**

Append to `lib/views.py`:

```python
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
```

- [ ] **Step 2: Wire tab 3** in `app.py`

Replace:

```python
    with tab3:
        st.info("PR views — to be filled in Task 14.")
```

with:

```python
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
```

- [ ] **Step 3: Smoke test**

Run: `streamlit run app.py`
Expected: PR tab shows a table of best times per year (mm:ss), a progression line chart, and a long-runs-per-year bar chart.

---

### Task 15: Tab 4 — Calendar & consistency

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/lib/views.py`
- Modify: `/Users/Werk/Documents/strava-dashboard/app.py`

- [ ] **Step 1: Add calendar builders**

Append to `lib/views.py`:

```python
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
    df_h["dow"] = df_h["date"].dt.weekday  # 0=Mon
    df_h["week"] = df_h["date"].dt.isocalendar().week
    pivot = df_h.pivot(index="dow", columns="week", values="km").fillna(0)
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
```

- [ ] **Step 2: Wire tab 4** in `app.py`

Replace:

```python
    with tab4:
        st.info("Calendar views — to be filled in Task 15.")
```

with:

```python
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
```

- [ ] **Step 3: Smoke test**

Run: `streamlit run app.py`
Expected: Calendar tab shows streak metrics, one heatmap row per year (newest first), a day-of-week bar, and an hour-of-day bar.

---

### Task 16: Final integration test + README polish

**Files:**
- Modify: `/Users/Werk/Documents/strava-dashboard/README.md`

- [ ] **Step 1: Run full pytest**

Run: `pytest -v`
Expected: all unit tests PASS (Tasks 2, 3, 4, 5, 6, 7, 8, 9 covered).

- [ ] **Step 2: Run prepare.py from a clean state to confirm full pipeline**

```bash
rm -rf data/
python prepare.py
```

Expected:
- Progress bar 1008/1008.
- Final summary lists `parsed≈1007 failed≈1` (the .gpx outlier).
- `data/activities.parquet`, `data/streams/year=YYYY/...` populated.

- [ ] **Step 3: Run streamlit and click each tab**

Run: `streamlit run app.py`
Manually verify:
- Sidebar filters take effect on every tab.
- Volume tab: 4 KPI cards + 3 charts render with no Python errors in the terminal.
- Pace & HR tab: 5 charts render; HR-target slider updates the aerobic-efficiency chart.
- PR tab: table + 2 charts; cells show mm:ss times.
- Calendar tab: streak metrics + 1 heatmap per year + 2 histograms.
- Toggling "Include indoor runs" changes counts.
- Selecting a single year reduces all charts to that year's data.

- [ ] **Step 4: Polish README**

Replace `/Users/Werk/Documents/strava-dashboard/README.md` with:

```markdown
# Strava Running Dashboard

Local-only Streamlit dashboard over a Strava bulk export. Tracks running progression over years.

## Setup

    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

The `strava/` symlink should point at the unzipped Strava export directory.

## Run

    python prepare.py            # one-shot ETL → data/  (~5–15 min on first run)
    streamlit run app.py         # opens browser

`prepare.py` is idempotent: it skips activities already in `data/activities.parquet`.

## Override HR zones

    LTHR=180 python prepare.py --rebuild-zones

## Tests

    pytest

## Layout

- `prepare.py`           ETL entry
- `app.py`               Streamlit entry
- `lib/parsing.py`       CSV + FIT decoders
- `lib/metrics.py`       Per-activity derived metrics
- `lib/views.py`         Plotly chart builders
- `data/`                Generated parquets (gitignored if you `git init`)
- `strava/`              Symlink to raw export
```

- [ ] **Step 5: Done**

If pytest is green and all four tabs render cleanly with the real data, the build is complete.
