"""SQLite store for coaching state. Activities mirror Strava; plan + checkins are local."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "coach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id              INTEGER PRIMARY KEY,
    start_dt        TEXT NOT NULL,
    type            TEXT,
    name            TEXT,
    distance_m      REAL,
    moving_s        INTEGER,
    elapsed_s       INTEGER,
    avg_hr          REAL,
    max_hr          REAL,
    avg_speed       REAL,
    gap_speed       REAL,
    total_ascent    REAL,
    cadence         REAL,
    calories        REAL,
    perceived_exertion REAL,
    suffer_score    REAL,
    has_heartrate   INTEGER,
    raw_json        TEXT,
    fetched_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_dt ON activities(start_dt);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(type);

CREATE TABLE IF NOT EXISTS daily_load (
    date            TEXT PRIMARY KEY,
    trimp           REAL DEFAULT 0,
    km              REAL DEFAULT 0,
    moving_s        INTEGER DEFAULT 0,
    ctl             REAL,
    atl             REAL,
    tsb             REAL
);

CREATE TABLE IF NOT EXISTS plan_weeks (
    week_num        INTEGER PRIMARY KEY,
    start_date      TEXT NOT NULL,
    phase           TEXT NOT NULL,
    target_km       REAL,
    target_long_km  REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS plan_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    week_num            INTEGER NOT NULL REFERENCES plan_weeks(week_num),
    date                TEXT NOT NULL,
    day_of_week         INTEGER NOT NULL,
    session_type        TEXT NOT NULL,
    prescription        TEXT NOT NULL,
    target_distance_km  REAL,
    target_duration_s   INTEGER,
    target_pace_min_km  REAL,
    matched_activity_id INTEGER REFERENCES activities(id),
    status              TEXT DEFAULT 'planned',
    completion_note     TEXT
);
CREATE INDEX IF NOT EXISTS idx_plan_sessions_date ON plan_sessions(date);

CREATE TABLE IF NOT EXISTS daily_checkin (
    date            TEXT PRIMARY KEY,
    legs_rating     INTEGER,
    sleep_h         REAL,
    soreness        TEXT,
    rhr             INTEGER,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS coach_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT DEFAULT CURRENT_TIMESTAMP,
    date            TEXT,
    reason          TEXT,
    action          TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    key             TEXT PRIMARY KEY,
    value           TEXT
);

-- Staged plan adjustments. Skill proposes here; user accepts/rejects.
-- On apply: each row spawns a coach_log entry + mutates plan_sessions.
CREATE TABLE IF NOT EXISTS proposed_adjustments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    op              TEXT NOT NULL,    -- shift|replace|cancel|scale_week|add
    target_date     TEXT,             -- session date or week-start (for scale_week)
    target_session_id INTEGER,        -- nullable; if set, op binds to this row
    payload_json    TEXT NOT NULL,    -- op-specific args
    reason          TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',  -- pending|applied|rejected
    decided_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_proposed_status ON proposed_adjustments(status);
"""


@contextmanager
def conn(db_path: Path = DB_PATH):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init(db_path: Path = DB_PATH) -> None:
    with conn(db_path) as c:
        c.executescript(SCHEMA)


def get_state(key: str, default: str | None = None) -> str | None:
    with conn() as c:
        row = c.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_state(key: str, value: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO sync_state(key,value) VALUES(?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def upsert_activity(a: dict) -> bool:
    """Returns True if inserted (new), False if already existed."""
    with conn() as c:
        existing = c.execute("SELECT id FROM activities WHERE id=?", (a["id"],)).fetchone()
        c.execute("""
            INSERT INTO activities
              (id,start_dt,type,name,distance_m,moving_s,elapsed_s,
               avg_hr,max_hr,avg_speed,gap_speed,total_ascent,cadence,
               calories,perceived_exertion,suffer_score,has_heartrate,raw_json,fetched_at)
            VALUES (:id,:start_dt,:type,:name,:distance_m,:moving_s,:elapsed_s,
               :avg_hr,:max_hr,:avg_speed,:gap_speed,:total_ascent,:cadence,
               :calories,:perceived_exertion,:suffer_score,:has_heartrate,:raw_json,:fetched_at)
            ON CONFLICT(id) DO UPDATE SET
               start_dt=excluded.start_dt, type=excluded.type, name=excluded.name,
               distance_m=excluded.distance_m, moving_s=excluded.moving_s, elapsed_s=excluded.elapsed_s,
               avg_hr=excluded.avg_hr, max_hr=excluded.max_hr, avg_speed=excluded.avg_speed,
               gap_speed=excluded.gap_speed, total_ascent=excluded.total_ascent, cadence=excluded.cadence,
               calories=excluded.calories, perceived_exertion=excluded.perceived_exertion,
               suffer_score=excluded.suffer_score, has_heartrate=excluded.has_heartrate,
               raw_json=excluded.raw_json, fetched_at=excluded.fetched_at
        """, a)
        return existing is None


def get_activities_since(date_iso: str) -> list[sqlite3.Row]:
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM activities WHERE start_dt >= ? AND type='Run' ORDER BY start_dt", (date_iso,)))


def upsert_daily_load(date: str, trimp: float, km: float, moving_s: int) -> None:
    with conn() as c:
        c.execute("""
            INSERT INTO daily_load(date,trimp,km,moving_s)
            VALUES(?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
               trimp=excluded.trimp, km=excluded.km, moving_s=excluded.moving_s
        """, (date, trimp, km, moving_s))


def update_load_curves(date: str, ctl: float, atl: float, tsb: float) -> None:
    with conn() as c:
        c.execute("UPDATE daily_load SET ctl=?, atl=?, tsb=? WHERE date=?",
                  (ctl, atl, tsb, date))


def get_load_history() -> list[sqlite3.Row]:
    with conn() as c:
        return list(c.execute("SELECT * FROM daily_load ORDER BY date"))


def get_session(date: str) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM plan_sessions WHERE date=?", (date,)).fetchone()


def get_sessions_in_range(start: str, end: str) -> list[sqlite3.Row]:
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM plan_sessions WHERE date BETWEEN ? AND ? ORDER BY date", (start, end)))


def mark_session_completed(session_id: int, activity_id: int, note: str | None = None) -> None:
    with conn() as c:
        c.execute("""UPDATE plan_sessions
                     SET matched_activity_id=?, status='completed', completion_note=?
                     WHERE id=?""", (activity_id, note, session_id))


def upsert_checkin(date: str, **fields) -> None:
    keys = ["legs_rating", "sleep_h", "soreness", "rhr", "notes"]
    values = {k: fields.get(k) for k in keys}
    with conn() as c:
        c.execute("""
            INSERT INTO daily_checkin(date,legs_rating,sleep_h,soreness,rhr,notes)
            VALUES(:date,:legs_rating,:sleep_h,:soreness,:rhr,:notes)
            ON CONFLICT(date) DO UPDATE SET
              legs_rating=COALESCE(excluded.legs_rating, daily_checkin.legs_rating),
              sleep_h=COALESCE(excluded.sleep_h, daily_checkin.sleep_h),
              soreness=COALESCE(excluded.soreness, daily_checkin.soreness),
              rhr=COALESCE(excluded.rhr, daily_checkin.rhr),
              notes=COALESCE(excluded.notes, daily_checkin.notes)
        """, {"date": date, **values})


def get_checkin(date: str) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM daily_checkin WHERE date=?", (date,)).fetchone()


def log_action(date: str, reason: str, action: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO coach_log(date,reason,action) VALUES(?,?,?)", (date, reason, action))


def get_session_by_id(session_id: int) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM plan_sessions WHERE id=?", (session_id,)).fetchone()


def update_session(session_id: int, **fields) -> None:
    if not fields: return
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE plan_sessions SET {cols} WHERE id=?",
                  (*fields.values(), session_id))


def insert_session(week_num: int, date: str, day_of_week: int, session_type: str,
                   prescription: str, target_distance_km: float | None = None,
                   target_duration_s: int | None = None,
                   target_pace_min_km: float | None = None) -> int:
    with conn() as c:
        cur = c.execute("""INSERT INTO plan_sessions
                          (week_num,date,day_of_week,session_type,prescription,
                           target_distance_km,target_duration_s,target_pace_min_km)
                          VALUES(?,?,?,?,?,?,?,?)""",
                       (week_num, date, day_of_week, session_type, prescription,
                        target_distance_km, target_duration_s, target_pace_min_km))
        return cur.lastrowid


def delete_session(session_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM plan_sessions WHERE id=?", (session_id,))


def get_recent_activities(days: int) -> list[sqlite3.Row]:
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM activities WHERE start_dt >= ? AND type='Run' ORDER BY start_dt DESC",
            (cutoff,)))


def get_load_range(start: str, end: str) -> list[sqlite3.Row]:
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM daily_load WHERE date BETWEEN ? AND ? ORDER BY date", (start, end)))


def get_recent_checkins(days: int) -> list[sqlite3.Row]:
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM daily_checkin WHERE date >= ? ORDER BY date DESC", (cutoff,)))


def get_week(week_num: int) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM plan_weeks WHERE week_num=?", (week_num,)).fetchone()


def get_week_sessions(week_num: int) -> list[sqlite3.Row]:
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM plan_sessions WHERE week_num=? ORDER BY date", (week_num,)))


# --- proposed_adjustments helpers ---
def propose_adjustment(op: str, reason: str, payload: dict,
                       target_date: str | None = None,
                       target_session_id: int | None = None) -> int:
    import json
    with conn() as c:
        cur = c.execute("""INSERT INTO proposed_adjustments
                          (op,target_date,target_session_id,payload_json,reason)
                          VALUES(?,?,?,?,?)""",
                       (op, target_date, target_session_id, json.dumps(payload), reason))
        return cur.lastrowid


def get_pending_adjustments() -> list[sqlite3.Row]:
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM proposed_adjustments WHERE status='pending' ORDER BY id"))


def get_adjustment(adj_id: int) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM proposed_adjustments WHERE id=?", (adj_id,)).fetchone()


def mark_adjustment(adj_id: int, status: str) -> None:
    from datetime import datetime, timezone
    with conn() as c:
        c.execute("UPDATE proposed_adjustments SET status=?, decided_at=? WHERE id=?",
                  (status, datetime.now(timezone.utc).isoformat(), adj_id))
