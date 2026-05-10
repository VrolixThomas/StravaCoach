# Coach — Strava-driven dynamic training plan

CLI coach that pulls activities from Strava, tracks training load, and adjusts the prescribed session against your readiness.

## What's in here

| File | Purpose |
|-|-|
| `db.py` | SQLite schema + helpers. DB lives at `../coach.db`. |
| `strava_sync.py` | OAuth flow + activity pull. Tokens cached in `.strava_tokens.json`. |
| `load.py` | TRIMP load + CTL / ATL / TSB rolling fitness curves. |
| `plan.py` | 20-week plan template. `--seed` to instantiate with a Monday start date. |
| `backfill.py` | One-time import from `../data/activities.parquet` for history. |
| `checkin.py` | Daily CLI: sync → recompute load → today's session + readiness. |

## One-time setup

1. **Strava API app** (5 min)

   Go to https://www.strava.com/settings/api → create app:
   - Application Name: `Personal Coach`
   - Category: `Training`
   - Authorization Callback Domain: `localhost`
   - Upload any image

   Copy **Client ID** and **Client Secret**.

2. **Drop them in `coach/.env`**

   ```
   STRAVA_CLIENT_ID=12345
   STRAVA_CLIENT_SECRET=abcd1234ef...
   ```

   File is gitignored.

3. **Run OAuth once**

   ```
   .venv/bin/python -m coach.strava_sync --auth
   ```

   Browser opens → click Authorize → tokens saved to `coach/.strava_tokens.json`.

4. **Backfill history from existing parquet** (optional, populates DB before first sync)

   ```
   .venv/bin/python -m coach.backfill
   ```

5. **Seed the plan** (Monday start date)

   ```
   .venv/bin/python -m coach.plan --seed 2026-05-11 --show
   ```

## Daily use

```
.venv/bin/python -m coach.checkin
```

Output:

```
[1/4] Sync: 1 new, 0 updated.
[2/4] Load: CTL 27.4 · ATL 28.1 · TSB -0.7 (Δ7d: CTL +0.8, ATL +1.4)
[3/4] ✓ Yesterday: long matched to 'Ochtendloop' (14.2 km · 5:21/km · HR 148)

=== Today · Tue 12 May 2026 · Week 1 (easy) ===
  50 min easy + 4×20s strides on flat (HR cap 150)
  Target: 50:00 @ 5:12/km
  Readiness: [OK] TSB -0.7. Proceed with planned session.

Legs rating 1-10 (Enter to skip): 7
Soreness/notes (Enter for none): mild left calf

Tomorrow (Wed): rest — Rest or 30 min walk
```

## Flags

```
.venv/bin/python -m coach.checkin --no-sync          # skip Strava pull
.venv/bin/python -m coach.checkin --since-days 30    # widen sync window
.venv/bin/python -m coach.checkin --no-prompt        # CI / non-interactive
```

## Schema

See `db.py` — `activities`, `daily_load`, `plan_weeks`, `plan_sessions`, `daily_checkin`, `coach_log`, `sync_state`.

`coach_log` records every plan adjustment so the trail is auditable.

## Adjusting the plan

Edit phase definitions in `plan.py` and re-seed (this wipes `plan_sessions` + `plan_weeks` — completed-session matches are lost too unless you patch `seed()` to preserve them).

Pace targets (`EASY_PACE`, `THRESHOLD_PACE`, etc.) are constants at the top of `plan.py` — bump them after phase 2 once 10K TT shows new fitness.

## Limits

- Strava rate limit: 100 reqs / 15 min, 1,000 / day. Plenty for daily polling.
- TRIMP uses `HR_MAX = 198` and `HR_REST = 50` — adjust in `load.py` if your numbers differ.
- The plan is a template. Adjust real-time via the readiness logic in `checkin.py:_readiness()` and the `coach_log` actions.
