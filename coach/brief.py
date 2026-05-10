"""Read-only state dump for the coach skill. Outputs human-readable text by section.

Usage:
    python -m coach.brief --section week        Current week + planned sessions
    python -m coach.brief --section recent      Last 14 days of activities
    python -m coach.brief --section load        CTL/ATL/TSB last 14 days
    python -m coach.brief --section diff        Plan vs actual, last 7 days
    python -m coach.brief --section checkin     Recent legs ratings + soreness
    python -m coach.brief --section staged      Pending plan adjustments
    python -m coach.brief --section all         Everything (default)
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timedelta

from . import db, plan


def _pace_str(p: float | None) -> str:
    if p is None: return "—"
    m = int(p); s = int(round((p - m) * 60))
    if s == 60: m += 1; s = 0
    return f"{m}:{s:02d}"


def _fmt_dur(sec: int | None) -> str:
    if not sec: return "—"
    h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _pace_from(distance_m: float | None, moving_s: int | None) -> str:
    if not distance_m or not moving_s or distance_m < 100: return "—"
    return _pace_str(moving_s / 60 / (distance_m / 1000))


def section_week(today: date) -> str:
    wk_num = plan.current_week(today)
    if wk_num is None:
        # Either pre-plan or post-plan
        with db.conn() as c:
            first = c.execute("SELECT MIN(start_date) FROM plan_weeks").fetchone()[0]
            last = c.execute("SELECT MAX(start_date) FROM plan_weeks").fetchone()[0]
        if not first:
            return "## WEEK: No plan seeded. Run `python -m coach.plan --seed YYYY-MM-DD` (must be a Monday)."
        if today.isoformat() < first:
            days_to = (date.fromisoformat(first) - today).days
            return f"## WEEK: Plan starts {first} ({days_to} day{'s' if days_to != 1 else ''} away). Pre-plan period."
        return f"## WEEK: Plan ended (last week started {last}). Re-seed for new cycle."
    week = db.get_week(wk_num)
    sessions = db.get_week_sessions(wk_num)
    out = []
    out.append(f"## CURRENT WEEK — {wk_num}/20 ({week['phase']}, started {week['start_date']})")
    out.append(f"Targets: {week['target_km']:.0f} km total, long run {week['target_long_km']:.0f} km")
    if week['notes']: out.append(f"Notes: {week['notes']}")
    out.append("")
    out.append("Sessions:")
    out.append(f"{'Day':<5}{'Date':<12}{'Type':<11}{'Status':<11}{'Prescription'}")
    days_short = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    for s in sessions:
        d = date.fromisoformat(s['date'])
        marker = "← today" if d == today else ""
        prescription = s['prescription']
        if len(prescription) > 70: prescription = prescription[:67] + "..."
        out.append(f"{days_short[s['day_of_week']]:<5}{s['date']:<12}{s['session_type']:<11}"
                   f"{s['status']:<11}{prescription} {marker}")
    return "\n".join(out)


def section_recent(today: date, days: int = 14) -> str:
    activities = db.get_recent_activities(days)
    if not activities:
        return f"## RECENT ACTIVITIES ({days}d): none"
    out = []
    out.append(f"## RECENT ACTIVITIES (last {days} days, {len(activities)} runs)")
    out.append(f"{'Date':<11}{'Name':<30}{'km':>6}  {'Pace':>6}  {'AvgHR':>5}  {'MaxHR':>5}  {'Asc':>5}")
    total_km = 0.0
    for a in activities:
        d = a['start_dt'][:10]
        name = (a['name'] or '')[:28]
        km = (a['distance_m'] or 0) / 1000
        total_km += km
        pace = _pace_from(a['distance_m'], a['moving_s'])
        ahr = f"{a['avg_hr']:.0f}" if a['avg_hr'] else "—"
        mhr = f"{a['max_hr']:.0f}" if a['max_hr'] else "—"
        asc = f"{a['total_ascent']:.0f}" if a['total_ascent'] else "—"
        out.append(f"{d:<11}{name:<30}{km:>6.1f}  {pace:>6}  {ahr:>5}  {mhr:>5}  {asc:>5}")
    out.append(f"\nTotal: {total_km:.1f} km / {len(activities)} runs / "
               f"{total_km/days*7:.1f} km per 7-day window")
    return "\n".join(out)


def section_load(today: date, days: int = 14) -> str:
    start = (today - timedelta(days=days - 1)).isoformat()
    end = today.isoformat()
    rows = db.get_load_range(start, end)
    if not rows:
        return "## LOAD: no data"
    out = []
    out.append(f"## TRAINING LOAD (last {days} days)")
    out.append(f"{'Date':<11}{'TRIMP':>6}  {'km':>5}  {'CTL':>5}  {'ATL':>5}  {'TSB':>6}")
    for r in rows:
        out.append(f"{r['date']:<11}{r['trimp']:>6.1f}  {r['km']:>5.1f}  "
                   f"{r['ctl']:>5.1f}  {r['atl']:>5.1f}  {r['tsb']:>+6.1f}")
    if len(rows) >= 2:
        first, last = rows[0], rows[-1]
        out.append(f"\nDelta {len(rows)}d: CTL {last['ctl']-first['ctl']:+.1f}, "
                   f"ATL {last['atl']-first['atl']:+.1f}, TSB {last['tsb']-first['tsb']:+.1f}")
    if rows:
        last = rows[-1]
        flags = []
        if last['tsb'] < -25: flags.append("⚠ TSB <-25 (very fatigued)")
        elif last['tsb'] < -15: flags.append("TSB <-15 (fatigued)")
        if last['tsb'] > 15: flags.append("TSB >+15 (very fresh — may be undertrained)")
        if flags: out.append("Flags: " + " | ".join(flags))
    return "\n".join(out)


def section_diff(today: date, days: int = 7) -> str:
    """Compare planned vs actual for the past `days` days."""
    start = today - timedelta(days=days - 1)
    sessions = db.get_sessions_in_range(start.isoformat(), today.isoformat())
    activities = db.get_recent_activities(days + 1)
    acts_by_day: dict[str, list] = {}
    for a in activities:
        d = a['start_dt'][:10]
        acts_by_day.setdefault(d, []).append(a)

    out = [f"## PLAN vs ACTUAL (last {days} days)"]
    out.append(f"{'Date':<11}{'Type':<11}{'Status':<11}{'Planned':<35}{'Actual'}")
    planned_km = actual_km = 0.0
    missed = mismatched = matched = 0
    for s in sessions:
        d = s['date']
        planned = ""
        if s['target_distance_km']: planned = f"{s['target_distance_km']:.1f} km"
        elif s['target_duration_s']: planned = _fmt_dur(s['target_duration_s'])
        if s['target_pace_min_km']: planned += f" @ {_pace_str(s['target_pace_min_km'])}"
        if s['session_type'] in ("rest", "strength"):
            planned = s['session_type']
        if s['target_distance_km']: planned_km += s['target_distance_km']

        actuals = acts_by_day.get(d, [])
        actual_str = "—"
        if actuals:
            a = max(actuals, key=lambda x: x['distance_m'] or 0)
            km = (a['distance_m'] or 0) / 1000
            actual_km += km
            actual_str = f"{km:.1f} km @ {_pace_from(a['distance_m'], a['moving_s'])}"
            if a['avg_hr']: actual_str += f" HR{a['avg_hr']:.0f}"

        if s['session_type'] in ("rest", "strength"):
            status = "—"
        elif actuals:
            matched += 1
            status = "✓"
        else:
            missed += 1
            status = "MISSED"
        out.append(f"{d:<11}{s['session_type']:<11}{status:<11}{planned:<35}{actual_str}")
    out.append(f"\nPlanned km: {planned_km:.1f} · Actual km: {actual_km:.1f} · "
               f"Matched: {matched} · Missed: {missed}")
    return "\n".join(out)


def section_checkin(days: int = 14) -> str:
    rows = db.get_recent_checkins(days)
    if not rows:
        return f"## CHECKINS (last {days}d): none logged"
    out = [f"## CHECKINS (last {days}d, {len(rows)} entries)"]
    out.append(f"{'Date':<11}{'Legs':<5}{'Sleep':<6}{'RHR':<5}{'Soreness / Notes'}")
    for r in rows:
        legs = str(r['legs_rating']) if r['legs_rating'] is not None else "—"
        sleep = f"{r['sleep_h']:.1f}h" if r['sleep_h'] is not None else "—"
        rhr = str(r['rhr']) if r['rhr'] is not None else "—"
        notes = " · ".join(filter(None, [r['soreness'], r['notes']])) or ""
        out.append(f"{r['date']:<11}{legs:<5}{sleep:<6}{rhr:<5}{notes}")
    return "\n".join(out)


def section_staged() -> str:
    rows = db.get_pending_adjustments()
    if not rows:
        return "## STAGED ADJUSTMENTS: none pending"
    out = [f"## STAGED ADJUSTMENTS ({len(rows)} pending)"]
    out.append(f"{'ID':<4}{'Op':<14}{'Target':<14}{'Reason':<40}")
    for r in rows:
        target = r['target_date'] or (f"sess#{r['target_session_id']}" if r['target_session_id'] else "—")
        reason = (r['reason'] or '')[:38]
        out.append(f"{r['id']:<4}{r['op']:<14}{target:<14}{reason}")
        try:
            payload = json.loads(r['payload_json'])
            out.append(f"     payload: {payload}")
        except Exception:
            pass
    out.append("\nApply: `python -m coach.adjust apply --id <id>` (or `--all`)")
    out.append("Reject: `python -m coach.adjust reject --id <id>`")
    return "\n".join(out)


def section_log(days: int = 14) -> str:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with db.conn() as c:
        rows = list(c.execute(
            "SELECT * FROM coach_log WHERE ts >= ? ORDER BY ts DESC LIMIT 50", (cutoff,)))
    if not rows:
        return f"## COACH LOG (last {days}d): no entries"
    out = [f"## COACH LOG (last {days}d, {len(rows)} entries)"]
    for r in rows:
        out.append(f"{r['ts'][:16]}  [{r['date'] or '—'}]  {r['action']}  ← {r['reason']}")
    return "\n".join(out)


def section_all(today: date) -> str:
    parts = [
        section_week(today),
        section_recent(today),
        section_load(today),
        section_diff(today),
        section_checkin(),
        section_staged(),
        section_log(),
    ]
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--section", default="all",
                   choices=["week", "recent", "load", "diff", "checkin", "staged", "log", "all"])
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--date", help="Override 'today' for testing (YYYY-MM-DD)")
    args = p.parse_args(argv)
    today = date.fromisoformat(args.date) if args.date else date.today()
    db.init()
    fn_map = {
        "week": lambda: section_week(today),
        "recent": lambda: section_recent(today, args.days),
        "load": lambda: section_load(today, args.days),
        "diff": lambda: section_diff(today, args.days),
        "checkin": lambda: section_checkin(args.days),
        "staged": lambda: section_staged(),
        "log": lambda: section_log(args.days),
        "all": lambda: section_all(today),
    }
    print(fn_map[args.section]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
