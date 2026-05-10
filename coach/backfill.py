"""One-time backfill: load activities from data/activities.parquet → SQLite.
Useful before Strava OAuth is set up so checkin/load have history to work with."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import db

PARQUET = Path(__file__).parent.parent / "data" / "activities.parquet"


def run() -> int:
    if not PARQUET.exists():
        print(f"Missing {PARQUET}. Run `python prepare.py` first.")
        return 1
    df = pd.read_parquet(PARQUET)
    db.init()

    fetched_at = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for _, r in df.iterrows():
        start = r.get("start_time_utc")
        if pd.isna(start): continue
        start_iso = start.isoformat() if hasattr(start, "isoformat") else str(start)
        dist_m = _f(r.get("distance_m")) or 0.0
        moving_s = int(_f(r.get("moving_time_s")) or 0)
        elapsed_s = int(_f(r.get("elapsed_time_s")) or moving_s)
        avg_speed = (dist_m / moving_s) if moving_s > 0 else None
        row = {
            "id": int(r["activity_id"]),
            "start_dt": start_iso,
            "type": "Run",
            "name": str(r.get("name") or ""),
            "distance_m": dist_m,
            "moving_s": moving_s,
            "elapsed_s": elapsed_s,
            "avg_hr": _f(r.get("avg_hr")),
            "max_hr": _f(r.get("max_hr")),
            "avg_speed": avg_speed,
            "gap_speed": None,
            "total_ascent": _f(r.get("elev_gain_m")),
            "cadence": _f(r.get("avg_cadence")),
            "calories": _f(r.get("calories")),
            "perceived_exertion": _f(r.get("perceived_effort")),
            "suffer_score": _f(r.get("training_load")),
            "has_heartrate": 1 if r.get("avg_hr") and not pd.isna(r.get("avg_hr")) else 0,
            "raw_json": json.dumps({"backfilled_from": "parquet"}),
            "fetched_at": fetched_at,
        }
        if db.upsert_activity(row):
            inserted += 1
    print(f"Backfilled: {inserted} new, {len(df)-inserted} already present.")
    return 0


def _f(v):
    if v is None or (hasattr(v, "__float__") and pd.isna(v)):
        return None
    try: return float(v)
    except: return None


if __name__ == "__main__":
    raise SystemExit(run())
