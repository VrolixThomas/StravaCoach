"""Plan adjustments: propose → user accepts → apply (+ log).

Operations:
  shift       Move a session from one date to another
  replace     Swap a session's type/prescription/targets
  cancel      Delete a session
  scale_week  Scale all distance/duration in a week by a factor
  add         Insert a new session

Workflow:
  1. Skill calls `propose <op> --reason "..." [op-args]` → row in proposed_adjustments
  2. User reviews via `python -m coach.brief --section staged`
  3. Skill or user calls `apply --id N` (or `--all`) → mutation + coach_log entry
  4. Or `reject --id N` → marked rejected, no mutation

A small auto-apply path is exposed: `propose <op> --apply` immediately applies
in the same call (used by skill for single-session shifts when user already confirmed
inline). Race week (week 20) blocks auto-apply.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date

from . import db


RACE_WEEK = 20
HARD_LOCK_WEEKS = {RACE_WEEK}


# ---------- internal mutators (applied to plan_sessions) ----------

def _do_shift(session_id: int, new_date: str, reason: str) -> str:
    sess = db.get_session_by_id(session_id)
    if sess is None: raise ValueError(f"session {session_id} not found")
    if sess['status'] == 'completed':
        raise ValueError(f"session {session_id} is completed; cannot modify")
    new_dow = date.fromisoformat(new_date).weekday()
    db.update_session(session_id, date=new_date, day_of_week=new_dow)
    msg = f"shifted session#{session_id} ({sess['session_type']}) from {sess['date']} to {new_date}"
    db.log_action(new_date, reason, msg)
    return msg


def _do_replace(session_id: int, new_type: str, new_prescription: str,
                target_distance_km: float | None, target_duration_s: int | None,
                target_pace_min_km: float | None, reason: str) -> str:
    sess = db.get_session_by_id(session_id)
    if sess is None: raise ValueError(f"session {session_id} not found")
    if sess['status'] == 'completed':
        raise ValueError(f"session {session_id} is completed; cannot modify")
    db.update_session(session_id, session_type=new_type, prescription=new_prescription,
                      target_distance_km=target_distance_km,
                      target_duration_s=target_duration_s,
                      target_pace_min_km=target_pace_min_km)
    msg = (f"replaced session#{session_id} on {sess['date']}: "
           f"{sess['session_type']} → {new_type} ({new_prescription[:60]})")
    db.log_action(sess['date'], reason, msg)
    return msg


def _do_cancel(session_id: int, reason: str) -> str:
    sess = db.get_session_by_id(session_id)
    if sess is None: raise ValueError(f"session {session_id} not found")
    if sess['status'] == 'completed':
        raise ValueError(f"session {session_id} is completed; cannot delete")
    db.delete_session(session_id)
    msg = f"cancelled session#{session_id} ({sess['session_type']} on {sess['date']})"
    db.log_action(sess['date'], reason, msg)
    return msg


def _do_scale_week(week_num: int, factor: float, reason: str) -> str:
    if factor <= 0 or factor > 2.0:
        raise ValueError(f"scale factor {factor} out of safe range (0, 2.0]")
    sessions = db.get_week_sessions(week_num)
    touched = 0
    for s in sessions:
        if s['status'] == 'completed': continue
        if s['session_type'] in ("strength", "rest", "race"): continue
        kwargs = {}
        if s['target_distance_km']:
            kwargs['target_distance_km'] = round(s['target_distance_km'] * factor, 1)
        if s['target_duration_s']:
            kwargs['target_duration_s'] = int(s['target_duration_s'] * factor)
        if kwargs:
            db.update_session(s['id'], **kwargs)
            touched += 1
    msg = f"scaled week {week_num} by ×{factor:.2f} ({touched} sessions touched)"
    db.log_action(date.today().isoformat(), reason, msg)
    return msg


def _do_add(week_num: int, session_date: str, session_type: str, prescription: str,
            target_distance_km: float | None, target_duration_s: int | None,
            target_pace_min_km: float | None, reason: str) -> str:
    dow = date.fromisoformat(session_date).weekday()
    sid = db.insert_session(week_num, session_date, dow, session_type, prescription,
                             target_distance_km, target_duration_s, target_pace_min_km)
    msg = f"added session#{sid} ({session_type} on {session_date}): {prescription[:60]}"
    db.log_action(session_date, reason, msg)
    return msg


def _is_locked(week_num: int) -> bool:
    return week_num in HARD_LOCK_WEEKS


def _week_for_date(d: str) -> int | None:
    with db.conn() as c:
        row = c.execute("""SELECT week_num FROM plan_weeks
                          WHERE start_date <= ? ORDER BY start_date DESC LIMIT 1""", (d,)).fetchone()
        return row['week_num'] if row else None


# ---------- propose / apply / reject ----------

def propose(op: str, reason: str, payload: dict, target_date: str | None = None,
            target_session_id: int | None = None) -> int:
    """Stage an adjustment. Returns the proposed_adjustments.id."""
    db.init()
    return db.propose_adjustment(op, reason, payload,
                                  target_date=target_date,
                                  target_session_id=target_session_id)


def _check_lock(target_session_id: int | None, target_date: str | None,
                payload: dict) -> None:
    """Raise if the target falls in a hard-locked week."""
    wk = payload.get("week_num")
    if wk is None and target_session_id is not None:
        sess = db.get_session_by_id(target_session_id)
        if sess: wk = sess['week_num']
    if wk is None and target_date:
        wk = _week_for_date(target_date)
    if wk is not None and _is_locked(wk):
        raise ValueError(f"week {wk} is hard-locked; manual override required")


def _execute(op: str, payload: dict, reason: str,
             target_session_id: int | None, target_date: str | None) -> str:
    _check_lock(target_session_id, target_date, payload)
    if op == "shift":
        return _do_shift(target_session_id, payload["new_date"], reason)
    if op == "replace":
        return _do_replace(target_session_id, payload["new_type"], payload["new_prescription"],
                           payload.get("target_distance_km"), payload.get("target_duration_s"),
                           payload.get("target_pace_min_km"), reason)
    if op == "cancel":
        return _do_cancel(target_session_id, reason)
    if op == "scale_week":
        return _do_scale_week(payload["week_num"], payload["factor"], reason)
    if op == "add":
        wk = payload.get("week_num") or _week_for_date(target_date)
        if wk is None: raise ValueError(f"can't determine week for date {target_date}")
        return _do_add(wk, target_date, payload["session_type"], payload["prescription"],
                       payload.get("target_distance_km"), payload.get("target_duration_s"),
                       payload.get("target_pace_min_km"), reason)
    raise ValueError(f"unknown op {op}")


def apply(adj_id: int) -> str:
    db.init()
    adj = db.get_adjustment(adj_id)
    if adj is None: raise ValueError(f"adjustment {adj_id} not found")
    if adj['status'] != 'pending': raise ValueError(f"adjustment {adj_id} is {adj['status']}, not pending")
    payload = json.loads(adj['payload_json'])
    msg = _execute(adj['op'], payload, adj['reason'],
                   adj['target_session_id'], adj['target_date'])
    db.mark_adjustment(adj_id, 'applied')
    return msg


def reject(adj_id: int, note: str | None = None) -> None:
    db.init()
    adj = db.get_adjustment(adj_id)
    if adj is None: raise ValueError(f"adjustment {adj_id} not found")
    if adj['status'] != 'pending': raise ValueError(f"adjustment {adj_id} is {adj['status']}")
    db.mark_adjustment(adj_id, 'rejected')
    if note:
        db.log_action(date.today().isoformat(), note, f"rejected adjustment#{adj_id} ({adj['op']})")


def apply_all() -> list[str]:
    pending = db.get_pending_adjustments()
    return [apply(a['id']) for a in pending]


# ---------- CLI ----------

def _add_op_args(p):
    p.add_argument("--reason", required=True)
    p.add_argument("--apply", action="store_true",
                   help="Apply immediately after staging (single-session ops only)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Plan adjustment ops")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("apply", help="Apply a staged adjustment")
    sp.add_argument("--id", type=int)
    sp.add_argument("--all", action="store_true")

    sp = sub.add_parser("reject", help="Reject a staged adjustment")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--note", default=None)

    sp = sub.add_parser("list", help="List pending adjustments")

    sp = sub.add_parser("shift", help="Move a session to a new date")
    sp.add_argument("--session-id", type=int)
    sp.add_argument("--from-date", help="Pick session by date (alternative to --session-id)")
    sp.add_argument("--to-date", required=True)
    _add_op_args(sp)

    sp = sub.add_parser("replace", help="Replace a session's content")
    sp.add_argument("--session-id", type=int)
    sp.add_argument("--from-date")
    sp.add_argument("--type", required=True, dest="new_type")
    sp.add_argument("--prescription", required=True)
    sp.add_argument("--distance-km", type=float, default=None)
    sp.add_argument("--duration-s", type=int, default=None)
    sp.add_argument("--pace-min-km", type=float, default=None)
    _add_op_args(sp)

    sp = sub.add_parser("cancel", help="Delete a session")
    sp.add_argument("--session-id", type=int)
    sp.add_argument("--from-date")
    _add_op_args(sp)

    sp = sub.add_parser("scale-week", help="Scale all sessions in a week")
    sp.add_argument("--week", type=int, required=True)
    sp.add_argument("--factor", type=float, required=True)
    _add_op_args(sp)

    sp = sub.add_parser("add", help="Add a new session")
    sp.add_argument("--date", required=True)
    sp.add_argument("--type", required=True, dest="session_type")
    sp.add_argument("--prescription", required=True)
    sp.add_argument("--distance-km", type=float, default=None)
    sp.add_argument("--duration-s", type=int, default=None)
    sp.add_argument("--pace-min-km", type=float, default=None)
    _add_op_args(sp)

    args = p.parse_args(argv)
    db.init()

    if args.cmd == "apply":
        if args.all:
            for msg in apply_all(): print(f"applied: {msg}")
        elif args.id:
            print(f"applied: {apply(args.id)}")
        else:
            print("Provide --id or --all", file=sys.stderr); return 1
        return 0

    if args.cmd == "reject":
        reject(args.id, args.note)
        print(f"rejected adjustment#{args.id}")
        return 0

    if args.cmd == "list":
        from . import brief
        print(brief.section_staged())
        return 0

    # ops that propose
    def _resolve_session_id(args):
        if getattr(args, "session_id", None): return args.session_id
        if getattr(args, "from_date", None):
            sess = db.get_session(args.from_date)
            if sess is None: raise ValueError(f"no session on {args.from_date}")
            return sess['id']
        raise ValueError("must provide --session-id or --from-date")

    if args.cmd == "shift":
        sid = _resolve_session_id(args)
        sess = db.get_session_by_id(sid)
        adj_id = propose("shift", args.reason, {"new_date": args.to_date},
                          target_date=sess['date'], target_session_id=sid)
        print(f"proposed adjustment#{adj_id}: shift session#{sid} ({sess['date']} → {args.to_date})")
        if args.apply:
            print(f"applied: {apply(adj_id)}")
        return 0

    if args.cmd == "replace":
        sid = _resolve_session_id(args)
        sess = db.get_session_by_id(sid)
        payload = {"new_type": args.new_type, "new_prescription": args.prescription,
                   "target_distance_km": args.distance_km,
                   "target_duration_s": args.duration_s,
                   "target_pace_min_km": args.pace_min_km}
        adj_id = propose("replace", args.reason, payload,
                          target_date=sess['date'], target_session_id=sid)
        print(f"proposed adjustment#{adj_id}: replace session#{sid} ({sess['session_type']} → {args.new_type})")
        if args.apply:
            print(f"applied: {apply(adj_id)}")
        return 0

    if args.cmd == "cancel":
        sid = _resolve_session_id(args)
        sess = db.get_session_by_id(sid)
        adj_id = propose("cancel", args.reason, {},
                          target_date=sess['date'], target_session_id=sid)
        print(f"proposed adjustment#{adj_id}: cancel session#{sid} ({sess['session_type']} on {sess['date']})")
        if args.apply:
            print(f"applied: {apply(adj_id)}")
        return 0

    if args.cmd == "scale-week":
        adj_id = propose("scale_week", args.reason,
                          {"week_num": args.week, "factor": args.factor},
                          target_date=date.today().isoformat())
        print(f"proposed adjustment#{adj_id}: scale week {args.week} ×{args.factor}")
        if args.apply:
            if _is_locked(args.week):
                print(f"  REJECTED: week {args.week} is hard-locked. Use propose-only or override manually.",
                      file=sys.stderr)
                return 2
            print(f"applied: {apply(adj_id)}")
        return 0

    if args.cmd == "add":
        wk = _week_for_date(args.date)
        if wk is None:
            print(f"No plan_week covers {args.date}", file=sys.stderr); return 1
        payload = {"session_type": args.session_type, "prescription": args.prescription,
                   "week_num": wk,
                   "target_distance_km": args.distance_km,
                   "target_duration_s": args.duration_s,
                   "target_pace_min_km": args.pace_min_km}
        adj_id = propose("add", args.reason, payload, target_date=args.date)
        print(f"proposed adjustment#{adj_id}: add {args.session_type} on {args.date}")
        if args.apply:
            print(f"applied: {apply(adj_id)}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
