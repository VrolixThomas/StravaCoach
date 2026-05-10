"""TRIMP-based training load. CTL/ATL/TSB curves recomputed from activities table."""
from __future__ import annotations
import math
from datetime import date, timedelta
from collections import defaultdict

from . import db

HR_MAX = 198.0
HR_REST = 50.0


def trimp(moving_s: int | None, avg_hr: float | None) -> float:
    if not moving_s or moving_s <= 0:
        return 0.0
    minutes = moving_s / 60.0
    if not avg_hr or avg_hr <= HR_REST:
        return minutes * 0.5
    hrr = max(0.0, min(1.0, (avg_hr - HR_REST) / (HR_MAX - HR_REST)))
    return minutes * hrr * 0.64 * math.exp(1.92 * hrr)


def _ewm(values: list[float], halflife_days: int) -> list[float]:
    alpha = 1 - math.exp(math.log(0.5) / halflife_days)
    out = []
    cur = 0.0
    for v in values:
        cur = alpha * v + (1 - alpha) * cur
        out.append(cur)
    return out


def recompute() -> None:
    """Rebuild daily_load + CTL/ATL/TSB from activities."""
    db.init()
    with db.conn() as c:
        rows = list(c.execute(
            "SELECT start_dt, moving_s, distance_m, avg_hr FROM activities WHERE type='Run'"))

    if not rows:
        return

    day_trimp: dict[str, float] = defaultdict(float)
    day_km: dict[str, float] = defaultdict(float)
    day_sec: dict[str, int] = defaultdict(int)

    for r in rows:
        d = r["start_dt"][:10]
        day_trimp[d] += trimp(r["moving_s"], r["avg_hr"])
        day_km[d] += (r["distance_m"] or 0) / 1000.0
        day_sec[d] += r["moving_s"] or 0

    first = min(day_trimp.keys())
    last_dt = date.today()
    cur = date.fromisoformat(first)
    days: list[date] = []
    while cur <= last_dt:
        days.append(cur); cur += timedelta(days=1)

    trimps = [day_trimp.get(d.isoformat(), 0.0) for d in days]
    ctl = _ewm(trimps, 42)
    atl = _ewm(trimps, 7)

    for i, d in enumerate(days):
        iso = d.isoformat()
        db.upsert_daily_load(iso, day_trimp.get(iso, 0.0),
                              day_km.get(iso, 0.0),
                              day_sec.get(iso, 0))
        db.update_load_curves(iso, ctl[i], atl[i], ctl[i] - atl[i])


def latest() -> dict | None:
    rows = db.get_load_history()
    if not rows: return None
    last = rows[-1]
    return {"date": last["date"], "ctl": last["ctl"], "atl": last["atl"], "tsb": last["tsb"]}


def trend(days: int = 7) -> dict | None:
    rows = db.get_load_history()
    if len(rows) < days + 1: return None
    a, b = rows[-days - 1], rows[-1]
    return {
        "ctl_delta": b["ctl"] - a["ctl"],
        "atl_delta": b["atl"] - a["atl"],
        "tsb_delta": b["tsb"] - a["tsb"],
    }


if __name__ == "__main__":
    recompute()
    cur = latest()
    if cur:
        print(f"Latest {cur['date']}: CTL {cur['ctl']:.1f} ATL {cur['atl']:.1f} TSB {cur['tsb']:+.1f}")
    t = trend(7)
    if t:
        print(f"7-day trend: CTL {t['ctl_delta']:+.1f}, ATL {t['atl_delta']:+.1f}, TSB {t['tsb_delta']:+.1f}")
