# Strava Running Coach

Self-hosted running coach for Thomas. Combines a Strava bulk export, a live Strava API sync, training-load analytics (CTL/ATL/TSB), a 20-week dynamic plan, and a Claude Code skill that adjusts the plan based on actual runs and subjective check-ins.

Two layers:

1. **Engine** (`coach/`) — Python + SQLite. Pulls activities, computes load, holds the plan, applies adjustments. Pure CLI.
2. **Skill** (`.claude/skills/coach/`) — Claude Code skill that drives the engine with judgment. Reads state, decides what to change, writes adjustments via the engine, produces a brief.

The original Streamlit retrospective dashboard (`app.py`) still works for historical analysis.

## Quick start

```bash
cd ~/Documents/strava-dashboard

# One-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# One-time backfill from existing parquet (optional, skips if no parquet)
.venv/bin/python -m coach.backfill

# Strava OAuth (one time — see coach/README.md for full instructions)
.venv/bin/python -m coach.strava_sync --auth

# Seed the 20-week plan (must be a Monday)
.venv/bin/python -m coach.plan --seed 2026-05-11

# Daily check-in (sync + load + brief + prompt)
.venv/bin/python -m coach.checkin

# Visual dashboard
.venv/bin/python -m coach.dashboard --open
```

After setup, daily use is one command: `python -m coach.checkin`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Strava API                            │
└─────────────────────────────────┬───────────────────────┘
                                  │
                       ┌──────────▼──────────┐
                       │  coach.strava_sync  │  OAuth + activity pull
                       └──────────┬──────────┘
                                  │
                       ┌──────────▼──────────┐
                       │     coach.db        │  SQLite store
                       │  (activities, plan, │  (single source of truth)
                       │   load, checkins,   │
                       │   staging, log)     │
                       └──────────┬──────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                          │
   ┌────▼─────┐         ┌─────────▼─────────┐      ┌────────▼─────────┐
   │coach.load│         │   coach.brief     │      │  coach.adjust    │
   │ (TRIMP/  │         │ (read-only views  │      │ (propose/apply/  │
   │  CTL/ATL/│         │  for skill + CLI) │      │  reject + 5 ops) │
   │   TSB)   │         └─────────┬─────────┘      └────────┬─────────┘
   └──────────┘                   │                          │
                       ┌──────────▼──────────┐               │
                       │    coach.checkin    │               │
                       │  (daily CLI flow)   │               │
                       └─────────────────────┘               │
                                                             │
                       ┌──────────────────────┐              │
                       │ .claude/skills/coach │  reads brief │
                       │   (Claude skill)     ├──────────────┘
                       │  - SKILL.md          │  writes via adjust
                       │  - references/       │
                       │  - examples/         │
                       └──────────────────────┘

                       ┌──────────────────────┐
                       │  coach.dashboard     │  HTML view
                       │  (regenerated from   │  of all the above
                       │   coach.db on demand)│
                       └──────────────────────┘
```

## Project structure

```
~/Documents/strava-dashboard/
├── README.md                     ← you are here
├── CLAUDE.md                     ← agent / Claude reference (read this first if you're Claude)
├── requirements.txt
├── .gitignore
│
├── coach.db                      ← SQLite, generated, gitignored
├── dashboard.html                ← visual coach dashboard, regenerated on demand
│
├── coach/                        ← coaching engine (Python + SQLite)
│   ├── __init__.py
│   ├── README.md                 ← engine setup + Strava OAuth
│   ├── SKILL_PLAN.md             ← architecture spec for the skill
│   ├── .env                      ← STRAVA_CLIENT_ID / SECRET (gitignored)
│   ├── .strava_tokens.json       ← OAuth tokens, auto-rotates (gitignored)
│   ├── db.py                     ← SQLite schema + helpers
│   ├── strava_sync.py            ← OAuth + activity pull
│   ├── load.py                   ← TRIMP / CTL / ATL / TSB
│   ├── plan.py                   ← 20-week template + seed
│   ├── brief.py                  ← read-only state dumps (week, recent, load, diff, checkin, staged, log)
│   ├── adjust.py                 ← propose/apply/reject + 5 mutation ops
│   ├── checkin.py                ← daily CLI flow
│   ├── dashboard.py              ← HTML dashboard generator
│   └── backfill.py               ← one-shot import from parquet
│
├── .claude/
│   └── skills/
│       └── coach/                ← Claude skill, project-local
│           ├── SKILL.md
│           ├── references/
│           │   ├── adjustment-rules.md
│           │   ├── pace-zones.md
│           │   └── training-principles.md
│           └── examples/
│               ├── weekly-review.md
│               ├── post-run-on-target.md
│               └── post-run-bad-day.md
│
├── prepare.py                    ← legacy: bulk export ETL → parquet
├── app.py                        ← legacy: Streamlit retrospective dashboard
├── lib/                          ← legacy: parquet-side parsing / metrics / views
├── data/                         ← legacy: generated parquets (gitignored)
├── strava/                       ← symlink to raw Strava export dir
├── plans/, specs/, tests/        ← legacy from the original dashboard project
```

## Reference: every command

### Coaching engine

```bash
# Strava sync
.venv/bin/python -m coach.strava_sync --auth                # one-time OAuth
.venv/bin/python -m coach.strava_sync                       # incremental sync
.venv/bin/python -m coach.strava_sync --since-days 30       # widen pull window

# Plan management
.venv/bin/python -m coach.plan --seed 2026-05-11            # instantiate 20-week plan from a Monday
.venv/bin/python -m coach.plan --show                       # print 20-week summary

# Daily checkin (the main one)
.venv/bin/python -m coach.checkin                           # sync + load + today's brief + prompt
.venv/bin/python -m coach.checkin --no-sync                 # skip Strava call
.venv/bin/python -m coach.checkin --no-prompt               # skip interactive checkin
.venv/bin/python -m coach.checkin --since-days 30           # widen sync window

# Inspect any state slice
.venv/bin/python -m coach.brief --section all               # everything (default)
.venv/bin/python -m coach.brief --section week              # current week + sessions
.venv/bin/python -m coach.brief --section recent --days 14  # recent activities
.venv/bin/python -m coach.brief --section load --days 14    # CTL/ATL/TSB curves
.venv/bin/python -m coach.brief --section diff --days 7     # planned vs actual
.venv/bin/python -m coach.brief --section checkin           # leg ratings + soreness
.venv/bin/python -m coach.brief --section staged            # pending plan adjustments
.venv/bin/python -m coach.brief --section log --days 30     # coach decision audit
.venv/bin/python -m coach.brief --date 2026-05-15           # override "today" for testing

# Plan adjustments (every change writes to coach_log)
.venv/bin/python -m coach.adjust shift --from-date 2026-05-13 --to-date 2026-05-14 \
    --reason "..." --apply
.venv/bin/python -m coach.adjust replace --from-date 2026-05-12 --type easy \
    --prescription "30 min easy" --duration-s 1800 --reason "..." --apply
.venv/bin/python -m coach.adjust cancel --from-date 2026-05-15 --reason "..." --apply
.venv/bin/python -m coach.adjust scale-week --week 6 --factor 0.85 --reason "..."
.venv/bin/python -m coach.adjust add --date 2026-05-15 --type rest \
    --prescription "Forced rest" --reason "..." --apply
.venv/bin/python -m coach.adjust list                       # pending proposals
.venv/bin/python -m coach.adjust apply --all                # commit all pending
.venv/bin/python -m coach.adjust apply --id 5               # commit one
.venv/bin/python -m coach.adjust reject --id 5 --note "..." # discard one

# Dashboard
.venv/bin/python -m coach.dashboard                         # write dashboard.html
.venv/bin/python -m coach.dashboard --open                  # write + open in browser

# Load math (manual recompute, rarely needed)
.venv/bin/python -m coach.load                              # rebuild CTL/ATL/TSB

# One-time backfill (only after fresh setup)
.venv/bin/python -m coach.backfill                          # parquet → SQLite
```

### Legacy Streamlit dashboard (still works)

```bash
.venv/bin/python prepare.py                                 # parquet ETL
.venv/bin/streamlit run app.py                              # browser dashboard
```

## Daily workflow

1. **Morning:** `python -m coach.checkin` → see today's session + readiness, log overnight legs rating
2. **Train:** do the prescribed session (or improvise if needed)
3. **Optional after a tough run:** open Claude Code in this dir, say "I just ran X, felt rough" → skill assesses + adjusts
4. **Sunday:** open Claude Code, say "weekly review" → skill summarizes the week + adjusts next week

The system is designed so that Day 1 → Day 140 of training works without you having to think about plan management. Just do the daily check-in and the weekly skill review.

## How the skill is triggered

Open a Claude Code session from `~/Documents/strava-dashboard/`. The skill at `.claude/skills/coach/SKILL.md` auto-loads. Then:

| You say | What fires |
|-|-|
| "weekly review" / `/coach-review` / "Sunday review" | Weekly review flow — summarize past week, adjust upcoming |
| "I just ran X" / `/coach-postrun` / "post-run check" | Post-run flow — assess just-completed session, adjust nearby |
| "/coach" alone | Skill asks which mode |

Skill outputs a 4-section markdown brief: **What happened / What I'm changing / This coming week / Watch for**.

## What's actually in the database

```
activities              every Strava run (1,005 currently)
plan_weeks              20 rows, one per week of the plan
plan_sessions           ~140 rows, one per planned session
daily_load              one row per day with TRIMP, km, CTL, ATL, TSB
daily_checkin           one row per day with legs rating, sleep, soreness, RHR
proposed_adjustments    staging area for plan changes (pending/applied/rejected)
coach_log               audit trail — every adjustment writes here with reason
sync_state              key/value: last sync timestamp, etc.
```

Direct SQL access:
```bash
sqlite3 ~/Documents/strava-dashboard/coach.db
sqlite> .schema
sqlite> SELECT * FROM plan_sessions WHERE date = '2026-05-11';
```

## Hard rules baked into the system

- Race week (week 20) is hard-locked. Auto-apply refuses; manual edit only.
- Completed sessions cannot be modified by `coach.adjust`. The CLI rejects.
- Every adjustment writes to `coach_log` with a `--reason`. No silent mutations.
- TRIMP uses HRmax 198, HRrest 50 (in `coach/load.py` constants).
- Pace targets are in `coach/plan.py` constants, anchored to 2021 fitness.

## Goals

**Primary race targets:**
1. **Week 12** (2026-08-01): 10K time trial — sub-40 target
2. **Week 20** (2026-09-26): 24h lap event — max sub-1:23 laps over 520m

**Constraints:**
- Injury-sensitive shins/knees — strength work is non-negotiable
- 5 days/week capacity, 45-75 min weekday + 2-3h weekend long run
- Recovering from Sep-Dec 2025 break (injuries + work crunch)

See `CLAUDE.md` for the full athlete profile and decision-making context.

## Documentation map

- `README.md` — this file (what's available)
- `CLAUDE.md` — agent reference (project goals, conventions, what to do)
- `coach/README.md` — engine setup + Strava OAuth
- `coach/SKILL_PLAN.md` — architecture spec for the skill
- `.claude/skills/coach/SKILL.md` — the skill itself
- `.claude/skills/coach/references/adjustment-rules.md` — decision matrix
- `.claude/skills/coach/references/pace-zones.md` — pace targets + TRIMP math
- `.claude/skills/coach/references/training-principles.md` — the "why"

## Tests

```bash
.venv/bin/pytest
```

(Existing tests cover the legacy parquet ETL. No tests yet for `coach/` modules — TODO.)
