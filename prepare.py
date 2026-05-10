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

from lib.parsing import load_activities_csv, decode_stream
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

_SUPPORTED_EXTS = (".fit.gz", ".fit", ".gpx")


def _zone_lthr(activities_df: pd.DataFrame, override: float | None) -> float:
    if override is not None:
        return override
    max_hrs = activities_df["max_hr"].dropna()
    if max_hrs.empty:
        return 180.0
    return float(max_hrs.max() * 0.95)


def _process_activity(row: pd.Series, lthr: float) -> tuple[dict, pd.DataFrame | None, str | None]:
    fit_path = STRAVA / row["fit_path"]
    if not fit_path.exists():
        return row.to_dict(), None, f"missing file: {fit_path.name}"
    if not str(fit_path).lower().endswith(_SUPPORTED_EXTS):
        return row.to_dict(), None, f"unsupported format: {fit_path.name}"
    try:
        stream = decode_stream(fit_path)
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
