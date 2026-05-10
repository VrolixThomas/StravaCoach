# Coach skill — design plan

Plan for a Claude Code skill that turns the static 20-week template into a dynamically-adjusted plan based on Strava data + subjective input. Lives at `.claude/skills/coach/SKILL.md` inside the strava-dashboard project.

## Goal

Two trigger modes, one skill:

1. **Weekly review** (run on Sunday): summarize past week, compare planned vs actual, propose adjustments to the coming week, write them to the DB.
2. **Post-run check** (run after a session): assess what just happened, flag if it diverged from prescription, decide whether to shift nearby sessions.

Outcome each invocation:
- Markdown brief shown to user
- Concrete plan-row mutations in `plan_sessions`
- Audit entry in `coach_log` (every adjustment recorded with reason)
- Updated dashboard.html (regenerated from DB)

## Why a skill (not just a CLI)

The current `coach.checkin` CLI is **deterministic**: it prints today's session, asks for legs rating, prints tomorrow. It has zero judgment.

A skill adds **judgment**: read recent activities, recognize patterns ("two threshold sessions in a row, HR climbing, legs 5/10 — drop tomorrow's quality"), ask the right clarifying question, decide between half a dozen plausible plan revisions, write the chosen one. That's reasoning work, not flow-control.

The CLI stays the data layer. The skill is the coach.

## Architecture

```
┌─ User ─┐
│        │   "/coach-review" or "I just did 6×400, felt rough"
│        ▼
│   ┌────────────────┐
│   │ Skill          │ — invoked by description match or slash command
│   │ SKILL.md       │   reads context via inline !`...` blocks
│   └─────┬──────────┘
│         │ Claude
│         │ reads + reasons
│         ▼
│   ┌────────────────┐
│   │ coach.brief    │ JSON dump: load curves, recent runs, planned week,
│   │ (new module)   │ checkins, plan-vs-actual diffs
│   └────────────────┘
│         │
│         ▼
│   ┌────────────────┐
│   │ coach.adjust   │ mutate plan_sessions, log to coach_log
│   │ (new module)   │ atomic ops: shift / replace / cancel / scale
│   └────────────────┘
│         │
│         ▼
│   ┌────────────────┐
│   │ coach.dashboard│ regenerate HTML report from DB
│   │ (refactor)     │
│   └────────────────┘
```

## Skill structure (project-local)

```
~/Documents/strava-dashboard/
  .claude/
    skills/
      coach/
        SKILL.md             ← main entry, ≤300 lines, instructions only
        references/
          adjustment-rules.md ← decision matrix: when to shift/scale/replace
          pace-zones.md       ← TRIMP, CTL/ATL/TSB math, pace targets per phase
          training-principles.md ← 80/20, recovery rules, taper logic
        examples/
          weekly-review.md    ← worked example output
          post-run-easy.md    ← post-run examples for each session_type
          post-run-bad-day.md
```

**Why project-local, not `~/.claude/skills/`:** Skill is tightly coupled to `coach.db` schema, `coach.*` Python modules, and this athlete's data. Not portable. Project-local also means the skill is auto-discovered when the strava-dashboard dir is the cwd in any Claude Code session.

## SKILL.md frontmatter

```yaml
---
name: coach
description: Use when reviewing the running week, planning upcoming sessions, adjusting the training plan, or evaluating a just-completed run. Triggers on phrases like "weekly review", "review my week", "I just ran X", "adjust the plan", "/coach-review", "/coach-postrun".
allowed-tools: Bash Read Edit Write
---
```

Frontmatter rules followed (per writing-skills + Anthropic docs):
- `description` is "Use when..." — triggering conditions, not behavior
- ≤1024 chars total
- `allowed-tools` pre-approves Bash (CLI), Read, Edit (revising plan files), Write (dashboard HTML). User can still revoke per-call.

## SKILL.md body outline

```markdown
# Coach

You are an experienced running coach for Thomas. Your job: read the current state from coach.db, judge what should change, ask the right clarifying questions, write adjustments to the DB, and produce a brief.

## Context (live data, injected at skill load)

Current week: !`cd ~/Documents/strava-dashboard && .venv/bin/python -m coach.brief --section week`
Last 14 days: !`cd ~/Documents/strava-dashboard && .venv/bin/python -m coach.brief --section recent`
Load curves: !`cd ~/Documents/strava-dashboard && .venv/bin/python -m coach.brief --section load`
Plan vs actual (last 7 days): !`cd ~/Documents/strava-dashboard && .venv/bin/python -m coach.brief --section diff`
Latest checkin: !`cd ~/Documents/strava-dashboard && .venv/bin/python -m coach.brief --section checkin`

## Detect mode

If the user said "weekly review" / "/coach-review" / "Sunday review" → see "Weekly review flow".
If the user mentioned a specific session they just did → see "Post-run flow".
If unclear → ask which.

## Weekly review flow

1. Read the data above. Compute: planned km, actual km, planned quality sessions, actual quality sessions, missed sessions, load delta.
2. Identify red flags: see references/adjustment-rules.md for thresholds (e.g. CTL drop >5/wk, TSB <-20 for 2+ days, 2+ missed sessions, soreness flagged twice).
3. Ask 1-3 clarifying questions only if data is ambiguous. Don't ask if the data already tells you. Examples:
   - "Did you skip Wed's session because of legs or schedule?"
   - "How did the long run feel in the last 5 km?"
4. Decide adjustments to next week's plan_sessions rows. Use the decision matrix in references/adjustment-rules.md.
5. Apply via `python -m coach.adjust <op> ...`. Each call writes to coach_log.
6. Output a brief in this format: [...spec...]
7. Regenerate dashboard: `python -m coach.dashboard`.

## Post-run flow

1. Identify the run from latest activity (auto if today, else ask user which).
2. Compare to prescription: pace, duration, HR. Was it on target? Easier? Harder? Did they stop early?
3. Cross-check load curves: did this run push TSB into red?
4. Decide: do nothing, soften tomorrow, replace tomorrow, add a recovery day, etc. See decision matrix.
5. Apply adjustments. Log.
6. Output a brief.

## Adjustment operations

Available via `coach.adjust`:
- `shift --session <date> --to <date>` (move a session)
- `replace --session <date> --type <new_type> --prescription "..."` (swap session)
- `cancel --session <date>` (remove)
- `scale --week <n> --factor 0.7` (down-week)
- `add --date <date> --type rest` (insert)

Every op takes `--reason "..."` which is appended to coach_log.

## Hard rules (never violate)

- Never delete a `completed` session
- Never add quality back-to-back (always 1+ easy day between)
- Never modify the race-week (week 20) without explicit user OK
- Always log every change to coach_log with reason
- If TSB < -25, force a rest day in the next 48h
- If user reports new pain (not soreness), cancel quality for 7 days

## Output format

Markdown brief, 4 sections:
1. **What happened** — past week summary
2. **What I'm changing** — bulleted diff of plan adjustments with reasons
3. **This coming week** — table of next 7 days
4. **Watch for** — 1-3 things to monitor

Tone: confident, terse, technical. No hedging.
```

## New Python modules required

### `coach/brief.py`
Read-only state dump for the skill. Sections selectable via flag; outputs human-readable text (skill needs context, not JSON):
- `--section week` → current week meta + planned sessions
- `--section recent` → last N runs with key metrics
- `--section load` → CTL/ATL/TSB last 14 days
- `--section diff` → planned vs actual table
- `--section checkin` → recent legs ratings + soreness
- `--section all` → everything (default)

Pure functions over `coach.db`. ~150 lines.

### `coach/adjust.py`
Mutation operations on plan_sessions, each atomically logged to coach_log:
- `shift(session_date, new_date, reason)`
- `replace(session_date, new_type, new_prescription, targets, reason)`
- `cancel(session_date, reason)`
- `scale_week(week_num, factor, reason)` — multiplies all distances/durations
- `add_session(date, type, prescription, targets, reason)`

CLI shim so the skill can call `python -m coach.adjust shift --date 2026-05-13 --to 2026-05-14 --reason "..."`. ~200 lines.

### `coach/dashboard.py`
Refactor of the one-shot `analyze.py` to read from SQLite instead of CSV. Adds plan vs actual overlay, coach_log timeline. Output: `~/Documents/strava-dashboard/dashboard.html`. ~300 lines.

## Reference subfiles (drafted later, not now)

### `references/adjustment-rules.md`
Decision matrix in tabular form. Each row: trigger condition → recommended adjustment. Examples:
| Trigger | Adjustment |
|-|-|
| TSB < −20 for 2+ days | Replace next quality with easy or rest |
| Legs ≤ 4/10 morning | Replace today with rest; shift today's session +1 day if not already a quality day |
| Missed 2+ sessions in a week | Scale next week ×0.85; preserve long run |
| Long run pace > target +30 sec/km AND HR > target +10 bpm | Hold long-run distance, don't extend |
| Quality session pace > target +10% | Reduce next quality intensity by one tier |
| New pain (not soreness) | Cancel all quality for 7 days; switch to easy + cross-train |
| TSB > +15 for 3+ days | Add quality earlier; consider compressing taper |

### `references/pace-zones.md`
Pace targets per phase, TRIMP formula, CTL/ATL/TSB definitions, HR zone math. Single page, lifted from existing constants in `load.py` + `plan.py`.

### `references/training-principles.md`
The "why" behind the rules. 80/20, polarization, supercompensation, taper science. ~1 page. Skill can quote from here when explaining adjustments.

## Build sequence

1. **Build `coach/brief.py`** first. Verify section outputs by running each manually. Feed sample output into a draft SKILL.md by hand to make sure the skill gets enough context. *~30 min*

2. **Build `coach/adjust.py`** with the five ops. Test each by hand: shift a session, scale a week, verify coach_log entries. *~45 min*

3. **Refactor `analyze.py` → `coach/dashboard.py`** reading from SQLite. *~30 min*

4. **Write `.claude/skills/coach/SKILL.md`** without subfiles. Test both modes manually:
   - `/coach-review` invocation: walk through a fake Sunday review
   - `/coach-postrun` after a real session
   - Look for: does Claude pick the right adjustment? Does it ask too many questions? Too few? Does it hallucinate session details? *~1 hr iterating*

5. **Add `references/adjustment-rules.md`** based on what gaps the test invocations exposed. The TDD approach from writing-skills: see what Claude rationalizes wrongly without explicit rules, then write rules that close those loopholes.

6. **Add `references/pace-zones.md` and `training-principles.md`** for breadth.

7. **(Optional) Wrap `examples/`** with 3-5 worked transcripts.

Total: ~4 hours focused work. Build over 2-3 sessions, not one.

## Testing protocol

For each test scenario, the skill should produce a *defendable* adjustment. Not necessarily the same one a different coach would pick — but one that's internally consistent with the rules and the data.

| Scenario | Setup | Expected adjustment |
|-|-|-|
| Clean week | All sessions completed on target, TSB +2 | No adjustments. Brief confirms green light. |
| Missed Tue quality | Tue empty, legs 5/10 logged | Skill asks why; if scheduling, reschedule to Wed and shift easy day. If legs, drop the session. |
| Two hard sessions | Tue + Thu both at higher HR than target | Scale next week ×0.85, replace Tue with easy. |
| Pain reported | Soreness "left shin" logged for 3 days | Cancel all quality for 7 days, log to coach_log with reason. |
| TSB collapse | TSB went from +5 to −22 in 4 days (overload) | Insert rest tomorrow, scale this week's remaining sessions. |
| Long run blow-up | Last Sunday's long run had HR drift +15% second half | Don't extend long run distance next week, hold. |
| Race week | Currently in week 20 | Skill must NOT modify; if asked, refuses + cites hard rule. |

These become the "RED" cases per writing-skills TDD.

## Open questions

1. **Should the skill auto-apply adjustments or always confirm?**
   Recommend: confirm in weekly review (lots of changes), auto-apply in post-run if change is small (single session shift), confirm if multiple sessions touched.

2. **Where does new perceived-effort / soreness data enter?**
   Either the skill prompts the user, or `coach.checkin` already captures it. Recommend: skill never prompts for routine data — that's what daily checkin is for. Skill only asks judgment questions ("did you stop because of pain or schedule?").

3. **How does pace-target updating work?**
   When the 10K TT happens (week 12), pace targets for later phases should re-anchor. Recommend: add a `coach.calibrate` command that reads the TT result and updates `EASY_PACE`, `THRESHOLD_PACE`, `TENK_RACE_PACE` constants in the DB (move them out of `plan.py` constants into a `pace_targets` table). The skill can then call `calibrate` after a TT.

4. **Multi-session conversations?**
   If user says "let me sleep on it" after the skill proposes adjustments, do we save the proposal? Recommend: stage adjustments in a `proposed_adjustments` table; user accepts/rejects on next invocation. Adds complexity — skip until v2 if not needed.

## Out of scope (v1)

- Race-day tactics module (lap pacing strategy for the 24h event) — separate skill or doc later
- Multi-athlete support
- Injury rehab plans (different domain)
- Nutrition / strength session tracking (no data source)

## Risks

- **Skill rationalizes around hard rules.** Mitigation: explicit "Hard rules (never violate)" section in SKILL.md + references/adjustment-rules.md citing thresholds.
- **Claude over-asks.** Mitigation: explicit examples of when NOT to ask, ratio guidance ("max 3 clarifying questions per review").
- **Plan diverges from template intent.** Mitigation: every adjustment requires `reason`; weekly review summarizes cumulative changes vs original template.
- **DB schema migrations break the skill.** Mitigation: version the schema; the skill reads via `coach.brief` (a stable interface), not raw SQL.

## Decisions locked (2026-05-10)

1. ✅ Project-local skill location (`.claude/skills/coach/`)
2. ✅ Build new `coach/brief.py` + `coach/adjust.py` modules
3. ✅ **Staging IS in v1.** Add `proposed_adjustments` table; skill stages, user accepts/rejects on next invocation. Affects:
   - `db.py`: new table + helpers
   - `adjust.py`: split into `propose()` (writes to staging) + `apply()` (moves staged → live + logs to coach_log) + `reject()` (deletes staged)
   - `brief.py`: new `--section staged` showing pending proposals
   - `SKILL.md`: every adjustment goes through propose; auto-apply rule = "small, single-session shifts apply immediately on user confirm in the same turn"
4. ✅ Build order as planned: brief → adjust → dashboard → SKILL.md

## Apply mode (decided)

**Confirm major, auto-apply small.** Implementation:
- Single-session shift / single-session intensity scale → skill proposes + auto-applies in same turn, shows diff
- Multi-session change (scale_week, cancel multiple, add new sessions) → skill proposes only, user types "apply" to accept
- Race-week (week 20) changes → always require explicit user confirmation, no auto-apply
