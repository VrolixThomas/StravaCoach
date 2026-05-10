# Strava Running Dashboard — Design

**Date:** 2026-05-10
**Owner:** Thomas (t.vrolix@greenisland.be)
**Status:** Approved (design phase)

## 1. Goal

Build a personal, local-only interactive dashboard over a full Strava data export so the user can see how their **running** has evolved over the years across volume, pace/HR efficiency, personal records, and consistency.

Source data: Strava bulk export at `/Users/Werk/Documents/provider-service-worktrees/testing/strava/` (untracked dir in unrelated repo). 1008 running activities (`Activiteitstype == "Hardloopsessie"`), each with a `.fit.gz` (one `.gpx` outlier) under `strava/activities/`. CSV is in Dutch locale.

Out of scope (v1): live Strava API sync, route maps / GPS heatmap, multi-sport, mobile layout, athlete comparisons.

## 2. Tech stack

- **Streamlit** — UI framework. Single-script reactive model fits this scope.
- **pandas + pyarrow** — data manipulation and parquet I/O.
- **plotly** — interactive charts.
- **fitparse** — decode `.fit.gz` records.
- **tqdm** — progress bar for one-shot ETL.

Python ≥ 3.11. Local venv. No CI required.

## 3. Project layout

Lives **outside** the provider-service repo to avoid polluting it (per the project's "no plans in repo" rule).

```
/Users/Werk/Documents/strava-dashboard/
├── README.md
├── requirements.txt
├── prepare.py              # one-shot ETL: csv + .fit.gz → parquet
├── app.py                  # streamlit entry point
├── lib/
│   ├── __init__.py
│   ├── parsing.py          # fit decode, dutch-date parse, activities.csv loader
│   ├── metrics.py          # PR detection, HR efficiency, rolling aggregates, splits
│   └── views.py            # plotly chart builders, one function per chart
├── tests/
│   ├── test_parsing.py
│   └── test_metrics.py
├── data/                   # generated, gitignored
│   ├── activities.parquet
│   ├── streams/            # pyarrow dataset, partitioned by year=
│   └── parse_errors.log
├── strava/                 # symlink → ../provider-service-worktrees/testing/strava
└── specs/                  # this spec lives here
```

## 4. Data pipeline (`prepare.py`)

### 4.1 Load activities.csv

- Open `strava/activities.csv` with `csv.reader` (utf-8, Dutch headers).
- Filter `row['Activiteitstype'] == 'Hardloopsessie'` → expect ~1008 rows.
- Parse Dutch dates `"9 mei 2026, 00:03:01"` using a hard-coded month map:
  `{'jan':1,'feb':2,'mrt':3,'apr':4,'mei':5,'jun':6,'jul':7,'aug':8,'sep':9,'okt':10,'nov':11,'dec':12}`.
  Convert to UTC-aware `datetime`.
- Keep relevant columns; rename to English snake_case for downstream sanity:

  | Source (Dutch) | Target | Unit |
  |---|---|---|
  | Activiteits-ID | `activity_id` | int |
  | Datum van activiteit | `start_time_utc` | datetime |
  | Naam activiteit | `name` | str |
  | Beweegtijd | `moving_time_s` | float seconds |
  | Verstreken tijd | `elapsed_time_s` | float seconds |
  | Afstand | `distance_m` | float meters |
  | Totale stijging | `elev_gain_m` | float |
  | Totale daling | `elev_loss_m` | float |
  | Gemiddelde hartslag | `avg_hr` | float |
  | Max. hartslag | `max_hr` | float |
  | Gemiddelde cadans | `avg_cadence` | float |
  | Max. cadans | `max_cadence` | float |
  | Calorieën | `calories` | float |
  | Ervaren inspanning | `perceived_effort` | float (nullable) |
  | Trainingsbelasting | `training_load` | float (nullable) |
  | Bestandsnaam | `fit_path` | relative str |

### 4.2 Parse FIT streams

For each row's `fit_path`:

- Open via `gzip.open` + `fitparse.FitFile` from BytesIO.
- Skip and warn for `.gpx` files (parse separately later if needed).
- Iterate `record` messages; collect: `timestamp, position_lat, position_long, distance, speed, heart_rate, cadence, altitude, power`.
- Convert `position_lat/long` from semicircles to degrees (`val * (180 / 2**31)`).
- Drop columns where all values are null.
- Write per-activity rows to a streams DataFrame keyed by `activity_id`.

### 4.3 Per-activity derived metrics (computed from streams)

Added to the activity row before writing `activities.parquet`:

- **`indoor`** — `True` if no GPS samples (lat all-null).
- **`avg_pace_s_per_km`** — `moving_time_s / (distance_m / 1000)`.
- **`splits`** — list[dict] of 1-km splits: `{km, pace_s_per_km, avg_hr, elev_gain_m}`.
- **`hr_zones_seconds`** — dict z1..z5 of moving-time seconds in each zone.
  Zones derived from threshold HR `LTHR = 0.95 * global_max_hr` (override via env var `LTHR` at prepare time).
  z1 < 0.81·LTHR, z2 0.81–0.89, z3 0.89–0.94, z4 0.94–1.00, z5 ≥ 1.00.
  **Note:** zones are baked into the parquet at prepare time. Changing `LTHR` requires `python prepare.py --rebuild-zones` (re-runs zone calc only, no FIT re-parse).
- **`hr_drift_pct`** — `(hr_2nd_half_avg - hr_1st_half_avg) / hr_1st_half_avg`, each half by moving time.
- **`best_efforts`** — dict of fastest rolling-window times for distances 1k/5k/10k/21.0975k/42.195k that the run reaches; otherwise null.
- **`gap_avg_pace_s_per_km`** — optional grade-adjusted pace (Strava-style polynomial on grade per stream sample). Gated behind `--gap` flag in `prepare.py`; default off.
- **`low_quality`** — `True` if `distance_m < 500` or `moving_time_s < 120`.

### 4.4 Persistence

- `data/activities.parquet`: one row per run, columns above. ~1008 rows × ~30 cols.
- `data/streams.parquet`: per-second records, partitioned by `year=` directory (pyarrow dataset).
  Estimated 50–200 MB total.
- `SCHEMA_VERSION = 1` constant written as parquet metadata. App refuses to load mismatched version → user reruns prepare.

### 4.5 Incremental & resilience

- Skip activity ids already present in existing parquet (re-runs cheap).
- Per-file `try/except`: log `activity_id, error` to `data/parse_errors.log`; continue.
- End-of-run summary print: `parsed=N skipped=M failed=K total_km=… date_range=…`.
- Hard fail (`sys.exit(1)`) if zero runs after filter, or if no activities.csv found.

## 5. App structure (`app.py`)

Streamlit single-page app with sidebar globals + 4 tabs.

### 5.1 Sidebar (global filters)

- Date range slider (defaults to full range).
- Year multiselect (defaults all).
- Distance bucket multiselect: `<5k`, `5–10k`, `10–21k`, `21k+`.
- Toggle: "include low-quality runs" (default off).
- Toggle: "include indoor runs" (default on).

State held in `st.session_state`. All views recompute against the filtered subset.

### 5.2 Tab 1 — Volume trends

- KPI cards: total km, total runs, total moving time, current 4-wk avg km vs 1-yr-ago 4-wk avg.
- Stacked bar: weekly distance, color = year.
- Line: 4-week rolling distance + 4-week rolling moving-time hours (dual y-axis).
- Year-over-year overlay: monthly km, x = month-of-year (1–12), one line per year.

### 5.3 Tab 2 — Pace & HR efficiency

- Scatter: each run as point, x = `start_time_utc`, y = `avg_pace_s_per_km` (mm:ss formatted), size = `distance_m`, color = `avg_hr`. Hover shows name + activity id.
- Line: rolling 30-run avg pace, faceted into the 4 distance buckets.
- **Aerobic efficiency**: line of pace at a target HR (configurable via sidebar slider, default ±3 bpm around `0.75 * global_max_hr` — typical aerobic pace anchor) over time (monthly aggregate). If a month has fewer than 3 qualifying runs, drop that month. Computed from per-run summaries (`avg_hr`, `avg_pace_s_per_km`), not stream samples — cheap and stable.
- HR-zone distribution: stacked area, monthly aggregation, % of moving time in z1..z5.
- HR drift: line of monthly avg `hr_drift_pct`.

### 5.4 Tab 3 — Personal records by year

- Table: best 1k / 5k / 10k / half-marathon / marathon per year. Cells colored green if PR vs prior year, red if regression.
- Line: PR progression — one line per distance, x = year, y = best time (mm:ss).
- Bar: long-run count per year (long = `distance_m >= 15000`).

### 5.5 Tab 4 — Calendar & consistency

- GitHub-style yearly heatmap stacked by year, intensity = distance that day (`plotly.graph_objects.Heatmap` reshaped to weeks×days).
- Stat cards: longest streak (consecutive run-days), current streak, days/wk avg by year.
- Day-of-week histogram (Mon..Sun, distance summed).
- Hour-of-day histogram of `start_time_utc.hour`.

### 5.6 Caching & performance

- `@st.cache_data` on parquet readers, keyed on file mtime.
- Streams parquet is loaded **lazily** per-tab; volume/PR/calendar use only `activities.parquet`.
- Filter operations on aggregate parquet are O(1008) — no perf concern.

### 5.7 Empty / error states

- If `data/activities.parquet` missing: full-page message "Run `python prepare.py` first" with a copy-pastable command.
- If schema version mismatch: error message + same instruction.
- If filter selection produces empty subset: each chart shows "No runs match current filters."

## 6. Tests (light)

Personal tool — tests cover the deterministic pure functions, not UI.

- `tests/test_parsing.py`:
  - Dutch date parser handles all 12 months and edge formats.
  - Activity row mapping/renaming.
  - Indoor detection (synthetic stream with all-null lat).
- `tests/test_metrics.py`:
  - PR detection on a hand-built stream of known fastest 1k/5k.
  - HR-zone bucketing against fixed LTHR.
  - 1-km split computation.
  - HR drift on synthetic stream.

Run with `pytest`. No CI.

## 7. Risks & open questions

- **FIT parse time**: 1008 files × ~50 ms = ~1 min realistic, up to ~15 min worst case. Mitigated by incremental skip-already-parsed.
- **LTHR default may misclassify zones** — user can override via env var without rebuild.
- **Dutch month dict** — relies on Strava using these abbreviations; will hard-fail loudly if a row doesn't match (no silent NaT).
- `.gpx` files (1 in sample) skipped from streams; their summary row still contributes to volume/PR. Acceptable for v1.

## 8. Done criteria

- `python prepare.py` completes against the export, writes both parquets, logs no fatal errors.
- `streamlit run app.py` opens and all 4 tabs render with the full dataset.
- All four view groups work with sidebar filters applied live.
- `pytest` passes.
