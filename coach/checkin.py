"""Daily check-in CLI: sync Strava → recompute load → match completed sessions →
print today's brief → prompt for legs rating + log."""
from __future__ import annotations
import argparse, sys
from datetime import date, datetime, timezone, timedelta

from . import db, load, plan, strava_sync


def _pace_str(p: float | None) -> str:
    if p is None: return "—"
    m = int(p); s = int(round((p - m) * 60))
    if s == 60: m += 1; s = 0
    return f"{m}:{s:02d}"


def _fmt_dur(sec: int | None) -> str:
    if sec is None: return "—"
    h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _match_yesterday(yesterday: date) -> str | None:
    """If yesterday had a planned session and a Strava activity that fits, link them."""
    sess = plan.session_for_date(yesterday)
    if not sess or sess["status"] != "planned":
        return None
    if sess["session_type"] in ("rest", "strength"):
        return None
    acts = db.get_activities_since(yesterday.isoformat())
    same_day = [a for a in acts if a["start_dt"][:10] == yesterday.isoformat()]
    if not same_day:
        return f"⚠ Yesterday's planned {sess['session_type']} ({sess['prescription'][:60]}…) — no activity logged."
    a = max(same_day, key=lambda x: x["distance_m"] or 0)
    db.mark_session_completed(sess["id"], a["id"], note=f"matched on {date.today().isoformat()}")
    km = (a["distance_m"] or 0) / 1000
    pace = (a["moving_s"] / 60 / km) if km else None
    return (f"✓ Yesterday: {sess['session_type']} matched to '{a['name']}' "
            f"({km:.1f} km · {_pace_str(pace)}/km · HR {a['avg_hr'] or '—'})")


def _readiness(latest: dict | None, ci: dict | None) -> tuple[str, str]:
    """Return (status, advice)."""
    if not latest:
        return ("?", "No load data yet — sync first.")
    tsb = latest["tsb"]
    rating = ci["legs_rating"] if ci and ci["legs_rating"] is not None else None
    if rating is not None:
        if rating <= 4:
            return ("RECOVER", f"Legs {rating}/10. Replace today's session with rest or 25 min very easy.")
        if rating <= 6 and tsb < -10:
            return ("EASE", f"Legs {rating}/10, TSB {tsb:+.0f}. Cap intensity. Easy day even if quality scheduled.")
    if tsb < -20:
        return ("FATIGUED", f"TSB {tsb:+.0f}. Two days under-20 = forced down day. Cap intensity.")
    if tsb > 10:
        return ("FRESH", f"TSB {tsb:+.0f}. Good window for quality work.")
    return ("OK", f"TSB {tsb:+.0f}. Proceed with planned session.")


def run(skip_sync: bool = False, since_days: int = 14, no_prompt: bool = False) -> int:
    today = date.today()
    yesterday = today - timedelta(days=1)

    # 1. Sync
    if not skip_sync:
        try:
            since = datetime.now(timezone.utc) - timedelta(days=since_days)
            new, upd = strava_sync.sync(since)
            print(f"[1/4] Sync: {new} new, {upd} updated.")
        except FileNotFoundError as e:
            print(f"[1/4] Sync skipped: {e}")
        except Exception as e:
            print(f"[1/4] Sync FAILED: {e}", file=sys.stderr)
    else:
        print("[1/4] Sync: skipped (--no-sync)")

    # 2. Recompute load
    load.recompute()
    cur = load.latest()
    trend = load.trend(7)
    if cur:
        delta = ""
        if trend:
            delta = f" (Δ7d: CTL {trend['ctl_delta']:+.1f}, ATL {trend['atl_delta']:+.1f})"
        print(f"[2/4] Load: CTL {cur['ctl']:.1f} · ATL {cur['atl']:.1f} · TSB {cur['tsb']:+.1f}{delta}")
    else:
        print("[2/4] Load: no data yet.")

    # 3. Match yesterday
    msg = _match_yesterday(yesterday)
    if msg:
        print(f"[3/4] {msg}")
    else:
        print("[3/4] Yesterday: nothing to match.")

    # 4. Today + readiness
    sess = plan.session_for_date(today)
    if not sess:
        print(f"[4/4] No plan session for {today}. Run `python -m coach.plan --seed YYYY-MM-DD` to seed.")
        return 0
    wk = plan.current_week(today)
    ci = db.get_checkin(today.isoformat())
    ci_dict = dict(ci) if ci else None
    status, advice = _readiness(cur, ci_dict)

    print()
    print(f"=== Today · {today.strftime('%a %d %b %Y')} · Week {wk} ({sess['session_type']}) ===")
    print(f"  {sess['prescription']}")
    if sess["target_distance_km"]:
        print(f"  Target: {sess['target_distance_km']} km", end="")
        if sess["target_pace_min_km"]:
            print(f" @ {_pace_str(sess['target_pace_min_km'])}/km", end="")
        print()
    elif sess["target_duration_s"]:
        print(f"  Target: {_fmt_dur(sess['target_duration_s'])}")
    print(f"  Readiness: [{status}] {advice}")

    # 5. Optional checkin prompt
    if not no_prompt and (not ci or ci["legs_rating"] is None):
        print()
        try:
            rating = input("Legs rating 1-10 (Enter to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            rating = ""
        if rating.isdigit():
            r = int(rating)
            soreness = input("Soreness/notes (Enter for none): ").strip() or None
            db.upsert_checkin(today.isoformat(), legs_rating=r, soreness=soreness)
            print(f"Logged: legs {r}/10" + (f", '{soreness}'" if soreness else ""))
            # Re-evaluate readiness with the new rating
            new_ci = db.get_checkin(today.isoformat())
            new_status, new_advice = _readiness(cur, dict(new_ci))
            if new_status != status:
                print(f"  → Updated: [{new_status}] {new_advice}")

    # 6. Tomorrow preview
    tomorrow = today + timedelta(days=1)
    next_sess = plan.session_for_date(tomorrow)
    if next_sess:
        print()
        print(f"Tomorrow ({tomorrow.strftime('%a')}): {next_sess['session_type']} — {next_sess['prescription'][:80]}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-sync", action="store_true", help="Skip Strava sync")
    p.add_argument("--since-days", type=int, default=14, help="How far back to sync")
    p.add_argument("--no-prompt", action="store_true", help="Skip interactive checkin prompt")
    args = p.parse_args()
    sys.exit(run(skip_sync=args.no_sync, since_days=args.since_days, no_prompt=args.no_prompt))
