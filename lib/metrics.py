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
                s["heart_rate"].iloc[bucket_start_i:i].mean()
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


_ZONE_BOUNDS = (0.81, 0.89, 0.95, 1.00)  # upper bounds for z1..z4; z5 is open above


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
    ts = s["timestamp"].astype("int64").to_numpy() / 1e9
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
            frac = (d - (dist[j-1] - dist[i])) / (dist[j] - dist[j-1]) if dist[j] != dist[j-1] else 0.0
            t_end = ts[j-1] + frac * (ts[j] - ts[j-1])
            elapsed = t_end - ts[i]
            if elapsed > 0 and elapsed < best:
                best = elapsed
        out[label] = float(best) if best < math.inf else None
    return out
