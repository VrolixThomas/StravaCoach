"""20-week plan template. Targets: 10K speed (week 12) + 24h lap event (week 20).
Run plan.seed(start_date) once to populate plan_weeks + plan_sessions tables.
"""
from __future__ import annotations
from datetime import date, timedelta
from dataclasses import dataclass, field

from . import db


@dataclass
class WeekTemplate:
    week_num: int
    phase: str
    target_km: float
    target_long_km: float
    notes: str
    sessions: list[tuple[int, str, str, dict]] = field(default_factory=list)
    # session: (day_of_week 0=Mon, type, prescription, targets dict)


# Pace targets by phase (min/km). Adjusted as fitness rebuilds.
EASY_PACE = 5.20            # ~5:12/km
LONG_PACE = 5.30            # ~5:18/km
THRESHOLD_PACE = 4.20       # ~4:12/km (build); shifts to 4.10 by week 12
TENK_RACE_PACE = 4.00       # 10K target pace (week 12 TT goal sub-40)
VO2_PACE_400 = 3.55         # 400m @ ~1:30
LAP_PACE = 2.55             # 520m at goal (~1:20/lap)


def _strength_session():
    return (3, "strength", "Strength A: calf raises 3×15 ea, glute bridge 3×10 ea, "
                            "Bulgarian split squat 3×8 ea, tibialis raises 3×20, "
                            "side plank 3×30s ea, dead bug 3×10", {})


def _strength_session_b():
    return (5, "strength", "Strength B: as Strength A + add 1×8 each side single-leg deadlift "
                            "and 3×30s dead hang once available", {})


# Phase 1 — Base + speed reawakening (weeks 1-4)
PHASE1 = [
    WeekTemplate(1, "base", 32, 14, "Recovery from Batavieren. Easy + first strides.", [
        (0, "easy",  "20-25 min very easy + mobility (HR cap 140)",
            {"target_duration_s": 1500}),
        (1, "easy",  "50 min easy + 4×20s strides on flat (HR cap 150)",
            {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        (2, "rest",  "Rest or 30 min walk", {}),
        _strength_session(),
        (3, "easy",  "45 min easy", {"target_duration_s": 2700, "target_pace_min_km": EASY_PACE}),
        (4, "rest",  "Rest", {}),
        (5, "long",  "14 km long run, conversational (HR cap 150)",
            {"target_distance_km": 14, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min easy recovery OR cross-train (bike)",
            {"target_duration_s": 1800}),
    ]),
    WeekTemplate(2, "base", 36, 16, "Add second strides session. Hold easy effort.", [
        (0, "rest",  "Rest", {}),
        (1, "easy",  "55 min easy + 5×20s strides",
            {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        (2, "easy",  "40 min easy", {"target_duration_s": 2400, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "50 min easy + 4×20s strides",
            {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        _strength_session_b(),
        (5, "long",  "16 km long run", {"target_distance_km": 16, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(3, "base", 40, 18, "Introduce hill sprints. Speed primer, low impact.", [
        (0, "rest",  "Rest", {}),
        (1, "speed", "WU 15min + 6×10s steep hill sprints (full recovery walk-down) + CD 15min",
            {"target_duration_s": 2400}),
        (2, "easy",  "45 min easy", {"target_duration_s": 2700, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "60 min easy + 4×20s strides",
            {"target_duration_s": 3600, "target_pace_min_km": EASY_PACE}),
        _strength_session_b(),
        (5, "long",  "18 km long run", {"target_distance_km": 18, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "35 min recovery", {"target_duration_s": 2100}),
    ]),
    WeekTemplate(4, "base", 36, 14, "Down week. Recover, consolidate.", [
        (0, "rest",  "Rest", {}),
        (1, "easy",  "50 min easy + 4×20s strides",
            {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        (2, "rest",  "Rest", {}),
        _strength_session(),
        (3, "easy",  "45 min easy", {"target_duration_s": 2700, "target_pace_min_km": EASY_PACE}),
        (4, "rest",  "Rest", {}),
        (5, "long",  "14 km easy long run + 6×20s strides at end",
            {"target_distance_km": 14, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
]

# Phase 2 — Aerobic build + VO2 intro (weeks 5-8)
PHASE2 = [
    WeekTemplate(5, "build", 42, 20, "Introduce VO₂ work via short reps.", [
        (0, "rest",  "Rest", {}),
        (1, "vo2",   "WU 15min + 8×400m @ 1:30 / 90s jog + CD 10min",
            {"target_duration_s": 3000, "target_pace_min_km": VO2_PACE_400}),
        (2, "easy",  "45 min easy", {"target_duration_s": 2700, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "55 min easy + 5×20s strides",
            {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        _strength_session_b(),
        (5, "long",  "20 km long run", {"target_distance_km": 20, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "35 min recovery", {"target_duration_s": 2100}),
    ]),
    WeekTemplate(6, "build", 46, 22, "Threshold rep introduction.", [
        (0, "rest",  "Rest", {}),
        (1, "threshold", "WU 15min + 3×8min @ 4:15/km (2 min jog) + CD 10min",
            {"target_pace_min_km": THRESHOLD_PACE}),
        (2, "easy",  "50 min easy", {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "60 min easy + 6×20s strides",
            {"target_duration_s": 3600, "target_pace_min_km": EASY_PACE}),
        _strength_session_b(),
        (5, "long",  "22 km long run", {"target_distance_km": 22, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "40 min recovery", {"target_duration_s": 2400}),
    ]),
    WeekTemplate(7, "build", 50, 24, "Stack VO₂ + threshold weeks. Two quality days.", [
        (0, "rest",  "Rest", {}),
        (1, "vo2",   "WU 15min + 6×600m @ 3:55/km (90s jog) + CD 10min",
            {"target_pace_min_km": VO2_PACE_400}),
        (2, "easy",  "50 min easy", {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "60 min easy + 6×20s strides",
            {"target_duration_s": 3600, "target_pace_min_km": EASY_PACE}),
        (4, "threshold", "WU 10min + 4×6min @ 4:15/km (90s jog) + CD 10min",
            {"target_pace_min_km": THRESHOLD_PACE}),
        (5, "long",  "24 km long run", {"target_distance_km": 24, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(8, "build", 38, 16, "Down week, consolidate.", [
        (0, "rest",  "Rest", {}),
        (1, "easy",  "55 min easy + 4×20s strides",
            {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        (2, "rest",  "Rest", {}),
        _strength_session(),
        (3, "easy",  "50 min easy", {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        (4, "rest",  "Rest", {}),
        (5, "long",  "16 km easy", {"target_distance_km": 16, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
]

# Phase 3 — 10K block (weeks 9-12). Week 12 = 10K time trial.
PHASE3 = [
    WeekTemplate(9, "tenk", 50, 22, "10K-pace introduction.", [
        (0, "rest",  "Rest", {}),
        (1, "tenk",  "WU 15min + 5×1km @ 4:00/km (2min jog) + CD 10min",
            {"target_pace_min_km": TENK_RACE_PACE}),
        (2, "easy",  "55 min easy", {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "60 min easy + 6×20s strides",
            {"target_duration_s": 3600, "target_pace_min_km": EASY_PACE}),
        (4, "threshold", "WU 10min + 2×10min @ 4:15/km (3min jog) + CD 10min",
            {"target_pace_min_km": THRESHOLD_PACE}),
        (5, "long",  "22 km long run", {"target_distance_km": 22, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(10, "tenk", 52, 24, "Race-pace volume up.", [
        (0, "rest",  "Rest", {}),
        (1, "tenk",  "WU 15min + 6×1km @ 4:00/km (90s jog) + CD 10min",
            {"target_pace_min_km": TENK_RACE_PACE}),
        (2, "easy",  "60 min easy", {"target_duration_s": 3600, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "55 min easy + 6×20s strides",
            {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        (4, "vo2",   "WU 10min + 8×400m @ 1:28 (90s jog) + CD 10min",
            {"target_pace_min_km": VO2_PACE_400}),
        (5, "long",  "24 km long run", {"target_distance_km": 24, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "35 min recovery", {"target_duration_s": 2100}),
    ]),
    WeekTemplate(11, "tenk", 50, 26, "Peak quality before TT.", [
        (0, "rest",  "Rest", {}),
        (1, "tenk",  "WU 15min + 4×2km @ 4:05/km (2min jog) + CD 10min",
            {"target_pace_min_km": TENK_RACE_PACE}),
        (2, "easy",  "55 min easy", {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "55 min easy + 6×20s strides",
            {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        (4, "rest",  "Rest", {}),
        (5, "long",  "26 km long run", {"target_distance_km": 26, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(12, "tenk", 38, 12, "10K time trial week. Taper into Sat.", [
        (0, "rest",  "Rest", {}),
        (1, "tenk",  "WU 15min + 3×1km @ 4:00/km (2min jog) + CD 10min — primer",
            {"target_pace_min_km": TENK_RACE_PACE}),
        (2, "easy",  "40 min easy", {"target_duration_s": 2400, "target_pace_min_km": EASY_PACE}),
        (3, "rest",  "Rest", {}),
        (4, "easy",  "30 min easy + 4×100m strides",
            {"target_duration_s": 1800}),
        (5, "race",  "10K time trial — A test. Goal: sub-40. WU 20min, CD 15min.",
            {"target_distance_km": 10, "target_pace_min_km": TENK_RACE_PACE}),
        (6, "easy",  "30 min very easy recovery", {"target_duration_s": 1800}),
    ]),
]

# Phase 4 — 10K → lap event bridge (weeks 13-16)
PHASE4 = [
    WeekTemplate(13, "bridge", 44, 22, "Cold-start lap repeats begin. THE key session.", [
        (0, "rest",  "Rest after TT", {}),
        (1, "easy",  "50 min easy + 6×20s strides",
            {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        (2, "lap",   "Cold-start protocol: 5 min dynamic WU only, then 4×520m @ 1:20 "
                      "with 6 min walk recovery between. CD 10min.",
            {"target_pace_min_km": LAP_PACE}),
        _strength_session(),
        (3, "easy",  "55 min easy", {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        _strength_session_b(),
        (5, "long",  "22 km steady", {"target_distance_km": 22, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(14, "bridge", 48, 22, "Lap reps up to 5×.", [
        (0, "rest",  "Rest", {}),
        (1, "tenk",  "WU 15min + 4×1km @ 4:00/km (90s jog) + CD 10min",
            {"target_pace_min_km": TENK_RACE_PACE}),
        (2, "easy",  "60 min easy + 6×20s strides",
            {"target_duration_s": 3600, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "lap",   "Cold-start: 5×520m @ 1:18-1:20, 6 min walk recovery.",
            {"target_pace_min_km": LAP_PACE}),
        _strength_session_b(),
        (5, "long",  "22 km", {"target_distance_km": 22, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "35 min recovery", {"target_duration_s": 2100}),
    ]),
    WeekTemplate(15, "bridge", 50, 22, "Peak lap reps + race-pace volume.", [
        (0, "rest",  "Rest", {}),
        (1, "lap",   "Cold-start: 6×520m @ 1:18, 5 min walk recovery.",
            {"target_pace_min_km": LAP_PACE}),
        (2, "easy",  "55 min easy", {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "easy",  "60 min easy + 6×20s strides",
            {"target_duration_s": 3600, "target_pace_min_km": EASY_PACE}),
        (4, "tenk",  "WU 10min + 3×1km @ 4:00/km (2min jog) + CD 10min",
            {"target_pace_min_km": TENK_RACE_PACE}),
        (5, "long",  "22 km easy", {"target_distance_km": 22, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(16, "bridge", 38, 16, "Down week.", [
        (0, "rest",  "Rest", {}),
        (1, "easy",  "55 min easy + 6×20s strides",
            {"target_duration_s": 3300, "target_pace_min_km": EASY_PACE}),
        (2, "rest",  "Rest", {}),
        _strength_session(),
        (3, "lap",   "Light: 3×520m @ 1:20, 6 min walk recovery.",
            {"target_pace_min_km": LAP_PACE}),
        (4, "rest",  "Rest", {}),
        (5, "long",  "16 km easy", {"target_distance_km": 16, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
]

# Phase 5 — Sharpen + cold-leg drills (weeks 17-20)
PHASE5 = [
    WeekTemplate(17, "sharpen", 44, 18, "Off-hour cold sprint added.", [
        (0, "rest",  "Rest", {}),
        (1, "lap",   "Off-hour: 3×520m @ 1:18, full 8 min walk recovery. Run AT EVENT TIME OF DAY.",
            {"target_pace_min_km": LAP_PACE}),
        (2, "easy",  "50 min easy + 6×20s strides",
            {"target_duration_s": 3000, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "vo2",   "WU 10min + 6×400m @ 1:25 (90s jog) + CD 10min",
            {"target_pace_min_km": VO2_PACE_400}),
        (4, "easy",  "40 min easy", {"target_duration_s": 2400, "target_pace_min_km": EASY_PACE}),
        (5, "long",  "18 km", {"target_distance_km": 18, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(18, "sharpen", 42, 16, "Peak sharpness. 6×520m simulation.", [
        (0, "rest",  "Rest", {}),
        (1, "lap",   "Cold-start simulation: 6×520m @ 1:16-1:18, 6 min walk recovery. Race-spec.",
            {"target_pace_min_km": LAP_PACE}),
        (2, "easy",  "45 min easy", {"target_duration_s": 2700, "target_pace_min_km": EASY_PACE}),
        _strength_session(),
        (3, "vo2",   "WU 10min + 5×400m @ 1:25 (2min jog) + CD 10min",
            {"target_pace_min_km": VO2_PACE_400}),
        (4, "easy",  "35 min easy", {"target_duration_s": 2100, "target_pace_min_km": EASY_PACE}),
        (5, "long",  "16 km", {"target_distance_km": 16, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "30 min recovery", {"target_duration_s": 1800}),
    ]),
    WeekTemplate(19, "taper", 32, 12, "Taper. Sharpness only.", [
        (0, "rest",  "Rest", {}),
        (1, "lap",   "3×520m @ 1:18, 6 min walk. Stay sharp, don't deplete.",
            {"target_pace_min_km": LAP_PACE}),
        (2, "easy",  "40 min easy", {"target_duration_s": 2400, "target_pace_min_km": EASY_PACE}),
        (3, "rest",  "Rest", {}),
        (4, "easy",  "30 min easy + 6×100m strides",
            {"target_duration_s": 1800}),
        (5, "long",  "12 km easy", {"target_distance_km": 12, "target_pace_min_km": LONG_PACE}),
        (6, "easy",  "25 min recovery", {"target_duration_s": 1500}),
    ]),
    WeekTemplate(20, "race", 18, 0, "Race week. Final taper into 24h event.", [
        (0, "easy",  "30 min very easy + 4×100m strides",
            {"target_duration_s": 1800}),
        (1, "lap",   "WU 10min + 2×520m @ 1:18 (full recovery between) + CD 5min — sharpener",
            {"target_pace_min_km": LAP_PACE}),
        (2, "easy",  "20 min very easy", {"target_duration_s": 1200}),
        (3, "rest",  "Rest", {}),
        (4, "easy",  "15 min easy + 4×80m strides",
            {"target_duration_s": 900}),
        (5, "race",  "24h LAP EVENT — A race. Pacing strategy: target 1:18-1:20 per lap.",
            {"target_pace_min_km": LAP_PACE}),
        (6, "rest",  "Recovery", {}),
    ]),
]

ALL_PHASES = PHASE1 + PHASE2 + PHASE3 + PHASE4 + PHASE5


def seed(start_date: date) -> None:
    """Instantiate the 20-week plan starting on `start_date` (must be a Monday)."""
    if start_date.weekday() != 0:
        raise ValueError(f"start_date must be a Monday, got {start_date.strftime('%A')}")
    db.init()
    with db.conn() as c:
        c.execute("DELETE FROM plan_sessions")
        c.execute("DELETE FROM plan_weeks")
        for w in ALL_PHASES:
            wk_start = start_date + timedelta(weeks=w.week_num - 1)
            c.execute("""INSERT INTO plan_weeks(week_num,start_date,phase,target_km,target_long_km,notes)
                         VALUES(?,?,?,?,?,?)""",
                      (w.week_num, wk_start.isoformat(), w.phase, w.target_km, w.target_long_km, w.notes))
            for dow, stype, prescription, targets in w.sessions:
                d = wk_start + timedelta(days=dow)
                c.execute("""INSERT INTO plan_sessions
                             (week_num,date,day_of_week,session_type,prescription,
                              target_distance_km,target_duration_s,target_pace_min_km)
                             VALUES(?,?,?,?,?,?,?,?)""",
                          (w.week_num, d.isoformat(), dow, stype, prescription,
                           targets.get("target_distance_km"),
                           targets.get("target_duration_s"),
                           targets.get("target_pace_min_km")))


def session_for_date(d: date) -> dict | None:
    row = db.get_session(d.isoformat())
    return dict(row) if row else None


def upcoming(today: date, days: int = 7) -> list[dict]:
    end = today + timedelta(days=days - 1)
    return [dict(r) for r in db.get_sessions_in_range(today.isoformat(), end.isoformat())]


def current_week(today: date) -> int | None:
    with db.conn() as c:
        row = c.execute("""SELECT week_num FROM plan_weeks
                           WHERE start_date <= ? ORDER BY start_date DESC LIMIT 1""",
                        (today.isoformat(),)).fetchone()
        return row["week_num"] if row else None


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--seed", help="Start date YYYY-MM-DD (must be Monday)")
    p.add_argument("--show", action="store_true", help="Print the plan summary")
    args = p.parse_args()

    if args.seed:
        d = date.fromisoformat(args.seed)
        seed(d)
        print(f"Seeded 20-week plan starting {d}")
    if args.show:
        with db.conn() as c:
            for w in c.execute("SELECT * FROM plan_weeks ORDER BY week_num"):
                print(f"Wk{w['week_num']:2d} ({w['start_date']}) {w['phase']:<8s} "
                      f"{w['target_km']:>4.0f} km, long {w['target_long_km']:.0f} km — {w['notes']}")
