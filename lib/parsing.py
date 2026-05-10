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
        # Last occurrence wins — the export has duplicate header names where the
        # later column holds the canonical numeric form (e.g. distance in metres,
        # not the display "7,53" km). First occurrences are display strings.
        idx = {}
        for i, h in enumerate(header):
            if h in _COL_MAP:
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


import gzip
import math as _math
from io import BytesIO
import fitparse
import gpxpy

_SEMI_TO_DEG = 180.0 / 2**31

_RECORD_FIELDS = (
    "timestamp", "position_lat", "position_long", "distance",
    "speed", "heart_rate", "cadence", "altitude", "power",
)


def decode_fit_stream(path: Path) -> pd.DataFrame:
    """Decode a .fit or .fit.gz file's `record` messages into a DataFrame."""
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":  # gzip magic
        raw = gzip.decompress(raw)
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
    df = df.dropna(axis=1, how="all")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


_GPXTPX_HR_LOCALNAMES = {"hr", "heartrate", "heart_rate"}
_EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if any(v is None or _math.isnan(v) for v in (lat1, lon1, lat2, lon2)):
        return 0.0
    rlat1, rlat2 = _math.radians(lat1), _math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = _math.radians(lon2 - lon1)
    a = _math.sin(dlat / 2) ** 2 + _math.cos(rlat1) * _math.cos(rlat2) * _math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * _math.asin(_math.sqrt(a))


def _extract_gpx_hr(point) -> float | None:
    """Pull HR from a gpxpy point's extensions, regardless of namespace."""
    for ext in getattr(point, "extensions", []) or []:
        # Some GPX exports nest hr under TrackPointExtension; gpxpy gives us the elements as ETree nodes.
        for node in ext.iter() if hasattr(ext, "iter") else [ext]:
            tag = node.tag
            local = tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()
            if local in _GPXTPX_HR_LOCALNAMES and node.text:
                try:
                    return float(node.text.strip())
                except ValueError:
                    return None
    return None


def decode_gpx_stream(path: Path) -> pd.DataFrame:
    """Decode a .gpx file into the same column shape as decode_fit_stream."""
    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)
    rows: list[dict] = []
    cumulative_m = 0.0
    prev_lat = prev_lon = None
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                if prev_lat is not None and pt.latitude is not None and pt.longitude is not None:
                    cumulative_m += _haversine_m(prev_lat, prev_lon, pt.latitude, pt.longitude)
                prev_lat, prev_lon = pt.latitude, pt.longitude
                row = {
                    "timestamp": pt.time,
                    "position_lat": pt.latitude,
                    "position_long": pt.longitude,
                    "altitude": pt.elevation,
                    "distance": cumulative_m,
                    "heart_rate": _extract_gpx_hr(pt),
                }
                rows.append(row)
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.dropna(axis=1, how="all")
    return df


def decode_stream(path: Path) -> pd.DataFrame:
    """Dispatch to the right decoder based on file extension."""
    name = str(path).lower()
    if name.endswith(".fit.gz") or name.endswith(".fit"):
        return decode_fit_stream(path)
    if name.endswith(".gpx"):
        return decode_gpx_stream(path)
    raise ValueError(f"unsupported stream format: {path.name}")
