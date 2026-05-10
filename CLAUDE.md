# Claude reference — Strava Running Coach

You are working in Thomas's personal running coach project. Read this entire file before doing anything substantive. The conventions here are non-obvious and the data is real (not test data) — careless changes affect actual training decisions.

## What this project is

A self-hosted training coach. Two layers:

1. **Engine** — Python + SQLite. Stores everything (activities, plan, load curves, check-ins, decisions). All mutations go through CLI modules. Files: `coach/*.py`, data in `coach.db`.
2. **Skill** — Claude Code skill at `.claude/skills/coach/SKILL.md`. Reads engine state, makes coaching decisions, writes adjustments back through the engine. The skill is the coach; the engine is the data layer.

If a user says "weekly review" / "/coach-review" / "I just ran X" / "post-run" / "/coach-postrun" / "review my week" / "Sunday review" — invoke the **coach** skill.

## Athlete profile

- **Thomas Vrolix.** 8 years running, 1,005 logged runs, ~7,500 km lifetime.
- **5K PR: 17:30** (3:30/km). User-confirmed. Any sub-3:00/km values in raw data are GPS errors — exclude in any analysis.
- **Peak year 2021:** 1,251 km, marathon distance reached, best 10K @ 3:53/km, avg HR 170.
- **HRmax ~198, assumed HRrest 50.** These are the constants in `coach/load.py`.
- **Injury-sensitive: shins (tibial stress) + knees (patellofemoral).** Currently healthy. Strength work is non-negotiable for prevention.
- **Sep-Dec 2025 was a forced break** (injuries + work). 6-month trailing volume dropped to ~57 km/month, but actual recent baseline is ~70-86 km/month — the trailing avg is dragged down by the dip. Don't quote 57 km/month as "current state".

## Goals (in priority order)

1. **24h lap event ~2026-09-26 (week 20):** ~10 reps of 520m laps over 24h. Each lap must be sub-1:23 (the ceiling). **Target pace 1:18-1:20** = 2:30-2:35/km. Multi-hour rest between reps. Speed-on-demand event, not endurance event. Has done this format before — knows it's reachable.
2. **10K time trial ~2026-08-01 (week 12):** sub-40 target. Acts as both fitness checkpoint and aerobic ceiling driver for the lap event.
3. **Half marathon explicitly NOT a target.** De-prioritized in intake. Don't propose it.

## The 20-week plan

Started Mon 2026-05-11. Five phases:

| Phase | Weeks | Focus |
|-|-|-|
| Base | 1–4 | Recovery + easy + first strides |
| Build | 5–8 | Aerobic + VO₂ intro + threshold |
| 10K block | 9–12 | Race-pace + week-12 TT |
| Bridge | 13–16 | Cold-start 520m repeats begin |
| Sharpen + race | 17–20 | Lap-specific + taper + week-20 race |

The full template lives in `coach/plan.py:PHASE1..PHASE5`. To see the day-by-day, run:

```bash
cd ~/Documents/strava-dashboard && .venv/bin/python -m coach.plan --show
```

Or open the visual: `.venv/bin/python -m coach.dashboard --open`.

## Hard rules — never violate

These are enforced in code AND in the skill. If you find yourself rationalizing past them, stop.

1. **Never modify a `completed` session.** `coach.adjust` errors out. Don't bypass via direct SQL.
2. **Race week (week 20) is hard-locked.** `coach.adjust._check_lock()` blocks `_execute()` for any op targeting week 20. The only override is editing the DB directly — and you should only do that after explicit user confirmation in the same turn.
3. **Never schedule quality back-to-back.** Always 1+ easy day or rest between threshold/VO2/race-pace work. The plan template enforces this; don't break it with adjustments.
4. **Pain reported (not "tight" or "sore" — actual pain language: "hurts", "sharp", "sore for >3 days"):** cancel quality for 7 days, replace with easy. Log to coach_log.
5. **TSB <-25:** force rest in next 48h. If today is already rest, force tomorrow rest.
6. **Every change goes through `coach.adjust`** (with `--reason`). Every call writes to `coach_log`. No direct DB writes for plan mutations.
7. **Don't propose more than 5 adjustments in one weekly review.** If the situation needs more, escalate: tell the user the plan needs a re-seed, not just adjustments.

## What you do, by user request

### "weekly review" / `/coach-review` / "Sunday review"

Invoke the **coach** skill. The skill instructions are in `.claude/skills/coach/SKILL.md`. Briefly: read live state via `coach.brief`, identify red flags using `references/adjustment-rules.md`, ask 1-3 clarifying questions only if data is ambiguous, propose adjustments via `coach.adjust`, output the 4-section brief.

### "I just ran X" / `/coach-postrun` / "post-run"

Invoke the **coach** skill, post-run mode. Identify the run from latest activity, compare to prescription, decide if nearby sessions need adjustment.

### "show me my plan" / "what's next" / "today's session"

Just run `python -m coach.brief --section week`. Don't invoke the skill — this is read-only.

### "sync my activities" / "pull from Strava"

`python -m coach.checkin` (does sync + load + brief in one). Or `python -m coach.strava_sync` for sync only.

### "open the dashboard"

`python -m coach.dashboard --open`.

### Anything code-related (modifying the engine)

Read this whole file first. Then read `coach/SKILL_PLAN.md` for the architecture spec. Test changes against `coach.db` (it's a real DB with real data — back it up before destructive operations: `cp coach.db coach.db.bak`).

## Conventions

- **All CLI modules are `python -m coach.<module>`.** Always run from the project root (`~/Documents/strava-dashboard/`). The venv is at `.venv/`. Python 3.11+ required.
- **SQLite is the source of truth.** Activities, plan, load, checkins, log — all in `coach.db`. The legacy parquet (`data/activities.parquet`) is read-only history; don't write to it.
- **Pace constants** live in `coach/plan.py` top of file (`EASY_PACE`, `THRESHOLD_PACE`, etc.). Re-anchor after week 12 TT (see open question 3 in `coach/SKILL_PLAN.md`).
- **TRIMP formula** in `coach/load.py`. HRmax/HRrest hardcoded as constants. Update if athlete's HRmax changes (rare).
- **Strava tokens** in `coach/.strava_tokens.json` (gitignored, 0600 perms). Auto-rotate via refresh token. Re-auth via `python -m coach.strava_sync --auth` if expired.
- **Plan re-seeding wipes `plan_sessions` AND `coach_log` mutation history.** Only do it between phases or if the plan structure fundamentally changes. Warn the user before suggesting.

## Decision-making framework

When the skill (or you, if doing it manually) needs to adjust the plan:

1. **Read state** via `coach.brief --section all`.
2. **Identify red flags** using `.claude/skills/coach/references/adjustment-rules.md`. The file has a precedence order: pain rules > TSB rules > subjective rules > execution rules > completion rules.
3. **Pick the smallest change** that addresses the issue. Don't cascade.
4. **Apply via `coach.adjust`.** Auto-apply small single-session changes; propose-only multi-session changes (`scale_week`, multiple cancels).
5. **Output the standard brief format**: What happened / What I'm changing / This coming week / Watch for.

Detailed rules in `.claude/skills/coach/references/`. Read those before making coaching judgments.

## Common mistakes (don't make these)

| Mistake | Why it's wrong | What to do instead |
|-|-|-|
| Asking "how do you feel?" | Daily checkin captures it | Read `coach.brief --section checkin` first |
| Quoting "57 km/month" as current state | It's a 6-month trailing avg dragged by Sep-Dec 2025 dip | Use last 3 months avg or April 2026 actual (~73-86 km/month) |
| Suggesting half marathon | User explicitly de-prioritized it | Stay focused on 10K + lap event |
| Modifying race week | Hard rule | Surface the lock, require explicit user confirmation |
| Direct SQL writes to plan_sessions | Bypasses coach_log audit | Use `coach.adjust` |
| Re-seeding plan to "freshen it" | Wipes coach_log + completed-session matches | Use `adjust` ops; only re-seed if structure changes |
| Recommending nutrition / sleep without data | Out of lane | Stay running-focused unless data clearly points there |
| Proposing 6+ adjustments in a review | Too much change at once | Cap at 5; escalate if more needed |
| Treating sub-3:00/km PRs as real | GPS junk in the dataset | Filter pace 3:00–12:00 min/km |
| Auto-applying without summarizing 3+ changes | Loses user trust | List them, then apply |

## Getting unstuck

If the engine errors out and you can't tell why:

```bash
# Inspect DB directly
sqlite3 ~/Documents/strava-dashboard/coach.db ".tables"
sqlite3 ~/Documents/strava-dashboard/coach.db ".schema plan_sessions"
sqlite3 ~/Documents/strava-dashboard/coach.db "SELECT * FROM coach_log ORDER BY id DESC LIMIT 10"

# Backup before destructive ops
cp ~/Documents/strava-dashboard/coach.db ~/Documents/strava-dashboard/coach.db.bak.$(date +%s)

# Test a single module
.venv/bin/python -c "from coach import db; db.init(); print('ok')"
.venv/bin/python -c "from coach import load; load.recompute(); print(load.latest())"
```

If `coach.strava_sync` is failing with 401: re-auth (`python -m coach.strava_sync --auth`).

If a session won't apply: check `coach.adjust list`, then `coach.adjust apply --id N`. If you get a lock error, week 20 is the only locked week — verify which week the target is in.

## Memory hygiene

The user's auto-memory at `~/.claude/projects/-Users-Werk-Documents-provider-service/memory/project_running_coaching.md` mirrors this file's key facts. If you change something here that affects ongoing coaching (goals, hard rules, athlete state), update that memory entry too.

## When in doubt

1. Read the skill: `.claude/skills/coach/SKILL.md`.
2. Read the rules: `.claude/skills/coach/references/adjustment-rules.md`.
3. Read the principles: `.claude/skills/coach/references/training-principles.md`.
4. Look at the examples: `.claude/skills/coach/examples/`.

These four files together are the coaching brain. This CLAUDE.md is the operating manual for the project that surrounds them.
