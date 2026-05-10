"""Generate the coach HTML dashboard from coach.db.

Adds plan-vs-actual overlay + coach_log timeline on top of the original
retrospective view (volume, pace/HR, fitness/fatigue/form, PRs).

Output: ../dashboard.html
"""
from __future__ import annotations
import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db, load

OUT = Path(__file__).parent.parent / "dashboard.html"


def _pace_str(p: float | None) -> str:
    if p is None: return "—"
    m = int(p); s = int(round((p - m) * 60))
    if s == 60: m += 1; s = 0
    return f"{m}:{s:02d}"


def _fmt_dur(sec: int | None) -> str:
    if not sec: return "—"
    sec = int(sec)
    h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _load_runs():
    with db.conn() as c:
        return list(c.execute(
            "SELECT * FROM activities WHERE type='Run' ORDER BY start_dt"))


def _monthly_aggregates(runs):
    months = defaultdict(lambda: {'count': 0, 'km': 0.0, 'sec': 0, 'load': 0.0,
                                   'hr_sum': 0.0, 'hr_n': 0, 'pace_sum': 0.0, 'pace_n': 0,
                                   'ascent': 0.0, 'longest_km': 0.0, 'best_pace': None,
                                   'long_runs': 0})
    for r in runs:
        dt = datetime.fromisoformat(r['start_dt'].replace('Z', '+00:00'))
        key = (dt.year, dt.month)
        m = months[key]
        m['count'] += 1
        km = (r['distance_m'] or 0) / 1000
        m['km'] += km
        m['sec'] += r['moving_s'] or 0
        m['load'] += load.trimp(r['moving_s'], r['avg_hr'])
        if r['avg_hr']: m['hr_n'] += 1; m['hr_sum'] += r['avg_hr']
        if r['moving_s'] and km >= 1:
            p = r['moving_s'] / 60 / km
            if 3.0 <= p <= 12.0:
                m['pace_n'] += 1; m['pace_sum'] += p
                if km >= 5 and (m['best_pace'] is None or p < m['best_pace']):
                    m['best_pace'] = p
        m['ascent'] += r['total_ascent'] or 0
        if km > m['longest_km']: m['longest_km'] = km
        if km >= 15 or (r['moving_s'] and r['moving_s'] >= 5400): m['long_runs'] += 1
    return months


def _build_monthly_series(months, runs):
    if not runs: return []
    first_dt = datetime.fromisoformat(runs[0]['start_dt'].replace('Z', '+00:00'))
    last_dt = datetime.fromisoformat(runs[-1]['start_dt'].replace('Z', '+00:00'))
    keys = []
    y, mn = first_dt.year, first_dt.month
    while (y, mn) <= (last_dt.year, last_dt.month):
        keys.append((y, mn))
        mn += 1
        if mn > 12: mn = 1; y += 1
    out = []
    for k in keys:
        m = months.get(k)
        label = f'{k[0]}-{k[1]:02d}'
        if m is None or m['count'] == 0:
            out.append({'label': label, 'count': 0, 'km': 0, 'hours': 0, 'load': 0,
                        'avg_hr': None, 'avg_pace': None, 'ascent': 0, 'longest_km': 0,
                        'long_runs': 0, 'best_pace': None, 'eff': None})
        else:
            avg_hr = m['hr_sum']/m['hr_n'] if m['hr_n'] else None
            avg_pace = m['pace_sum']/m['pace_n'] if m['pace_n'] else None
            eff = None
            if avg_pace and avg_hr:
                eff = round((60.0/avg_pace)/avg_hr*100, 3)
            out.append({
                'label': label, 'count': m['count'],
                'km': round(m['km'], 1),
                'hours': round(m['sec']/3600, 2),
                'load': round(m['load'], 0),
                'avg_hr': round(avg_hr, 1) if avg_hr else None,
                'avg_pace': round(avg_pace, 2) if avg_pace else None,
                'ascent': round(m['ascent'], 0),
                'longest_km': round(m['longest_km'], 1),
                'long_runs': m['long_runs'],
                'best_pace': round(m['best_pace'], 2) if m['best_pace'] else None,
                'eff': eff,
            })
    return out


def _yearly_aggregates(runs):
    yearly = defaultdict(lambda: {'count': 0, 'km': 0.0, 'sec': 0, 'hr_sum': 0.0, 'hr_n': 0,
                                   'best_5k': None, 'best_10k': None, 'longest': 0.0,
                                   'long_runs': 0, 'load': 0.0, 'ascent': 0.0,
                                   'pace_sum': 0.0, 'pace_n': 0})
    for r in runs:
        dt = datetime.fromisoformat(r['start_dt'].replace('Z', '+00:00'))
        a = yearly[dt.year]
        a['count'] += 1
        km = (r['distance_m'] or 0) / 1000
        a['km'] += km
        a['sec'] += r['moving_s'] or 0
        a['load'] += load.trimp(r['moving_s'], r['avg_hr'])
        if r['avg_hr']: a['hr_n'] += 1; a['hr_sum'] += r['avg_hr']
        if r['moving_s'] and km >= 1:
            p = r['moving_s'] / 60 / km
            if 3.0 <= p <= 12.0:
                a['pace_n'] += 1; a['pace_sum'] += p
                if km >= 5 and (a['best_5k'] is None or p < a['best_5k']):
                    a['best_5k'] = p
                if km >= 10 and (a['best_10k'] is None or p < a['best_10k']):
                    a['best_10k'] = p
        if km > a['longest']: a['longest'] = km
        if km >= 15: a['long_runs'] += 1
        a['ascent'] += r['total_ascent'] or 0
    out = []
    for y in sorted(yearly):
        a = yearly[y]
        out.append({
            'year': y, 'count': a['count'],
            'km': round(a['km']), 'hours': round(a['sec']/3600, 1),
            'load': round(a['load']),
            'avg_hr': round(a['hr_sum']/a['hr_n'], 1) if a['hr_n'] else None,
            'avg_pace': round(a['pace_sum']/a['pace_n'], 2) if a['pace_n'] else None,
            'best_5k': round(a['best_5k'], 2) if a['best_5k'] else None,
            'best_10k': round(a['best_10k'], 2) if a['best_10k'] else None,
            'longest': round(a['longest'], 1),
            'long_runs': a['long_runs'],
            'ascent': round(a['ascent']),
        })
    return out


def _load_curves():
    rows = db.get_load_history()
    return [{'d': r['date'], 'ctl': r['ctl'] or 0, 'atl': r['atl'] or 0,
             'tsb': r['tsb'] or 0, 'km': r['km'] or 0, 'trimp': r['trimp'] or 0}
            for r in rows]


def _plan_vs_actual_summary():
    """Return per-week planned km vs actual km from current plan."""
    with db.conn() as c:
        weeks = list(c.execute("SELECT * FROM plan_weeks ORDER BY week_num"))
        if not weeks: return []
        out = []
        for w in weeks:
            wk_start = date.fromisoformat(w['start_date'])
            wk_end = wk_start + timedelta(days=6)
            # planned
            planned_sessions = list(c.execute(
                "SELECT * FROM plan_sessions WHERE week_num=?", (w['week_num'],)))
            planned_km = sum(s['target_distance_km'] or 0 for s in planned_sessions)
            # actual
            actuals = list(c.execute(
                "SELECT distance_m FROM activities WHERE type='Run' AND start_dt >= ? AND start_dt <= ?",
                (wk_start.isoformat(), (wk_end + timedelta(days=1)).isoformat())))
            actual_km = sum((a['distance_m'] or 0) for a in actuals) / 1000
            out.append({
                'week_num': w['week_num'], 'start_date': w['start_date'], 'phase': w['phase'],
                'planned_km': round(planned_km, 1), 'actual_km': round(actual_km, 1),
                'target_km': w['target_km'],
            })
        return out


def _full_plan():
    """Return week-by-week sessions for the visual plan view."""
    with db.conn() as c:
        weeks = list(c.execute("SELECT * FROM plan_weeks ORDER BY week_num"))
        out = []
        for w in weeks:
            sessions = list(c.execute(
                "SELECT * FROM plan_sessions WHERE week_num=? ORDER BY date, id",
                (w['week_num'],)))
            out.append({'week': dict(w), 'sessions': [dict(s) for s in sessions]})
        return out


def _coach_log_recent(days: int = 30):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM coach_log WHERE ts >= ? ORDER BY ts DESC", (cutoff,))]


def render() -> str:
    db.init()
    runs = _load_runs()
    if not runs:
        return "<html><body><p>No activities in DB. Run backfill or sync first.</p></body></html>"

    months_data = _monthly_aggregates(runs)
    monthly = _build_monthly_series(months_data, runs)
    yearly = _yearly_aggregates(runs)
    curves = _load_curves()
    plan_vs = _plan_vs_actual_summary()
    full_plan = _full_plan()
    log = _coach_log_recent()
    today_iso = date.today().isoformat()

    total_runs = len(runs)
    total_km = sum((r['distance_m'] or 0) for r in runs) / 1000
    total_hours = sum((r['moving_s'] or 0) for r in runs) / 3600
    total_ascent = sum((r['total_ascent'] or 0) for r in runs)

    # Down-sample curves to weekly
    weekly_curves = []
    for i in range(0, len(curves), 7):
        j = min(i + 6, len(curves) - 1)
        weekly_curves.append({'d': curves[j]['d'],
                               'ctl': round(curves[j]['ctl'], 1),
                               'atl': round(curves[j]['atl'], 1),
                               'tsb': round(curves[j]['tsb'], 1),
                               'km': round(sum(c['km'] for c in curves[i:j+1]), 1)})

    peak_ctl = max(c['ctl'] for c in curves) if curves else 0
    peak_idx = max(range(len(curves)), key=lambda i: curves[i]['ctl']) if curves else 0
    peak_date = curves[peak_idx]['d'] if curves else "—"
    cur = curves[-1] if curves else None

    js = lambda o: json.dumps(o, default=str)

    def yr_row(y):
        return (f"<tr><td><strong>{y['year']}</strong></td>"
                f"<td class='num'>{y['count']}</td>"
                f"<td class='num'>{y['km']:,.0f}</td>"
                f"<td class='num'>{y['hours']:.1f}</td>"
                f"<td class='num'>{y['ascent']:,.0f}</td>"
                f"<td class='num'>{_pace_str(y['avg_pace'])}</td>"
                f"<td class='num'>{y['avg_hr'] or '—'}</td>"
                f"<td class='num'>{_pace_str(y['best_5k'])}</td>"
                f"<td class='num'>{_pace_str(y['best_10k'])}</td>"
                f"<td class='num'>{y['longest']:.1f}</td>"
                f"<td class='num'>{y['long_runs']}</td>"
                f"<td class='num'>{y['load']:,.0f}</td></tr>")

    def plan_row(p):
        delta_pct = ""
        if p['planned_km'] > 0:
            pct = p['actual_km'] / p['planned_km'] * 100
            cls = "h-good" if 90 <= pct <= 110 else ("h-warn" if 75 <= pct < 90 or 110 < pct <= 120 else "h-bad")
            delta_pct = f"<span class='{cls}'>{pct:.0f}%</span>"
        return (f"<tr><td>{p['week_num']}</td><td>{p['start_date']}</td><td>{p['phase']}</td>"
                f"<td class='num'>{p['planned_km']:.0f}</td>"
                f"<td class='num'>{p['actual_km']:.0f}</td>"
                f"<td class='num'>{delta_pct}</td></tr>")

    def session_row(s):
        days_short = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        cls = ""
        if s['date'] == today_iso: cls = "today"
        elif s['status'] == 'completed': cls = "done"
        elif s['date'] < today_iso: cls = "past"
        type_color = {
            "easy": "easy", "long": "long", "rest": "rest", "strength": "strength",
            "threshold": "qual", "vo2": "qual", "tenk": "qual", "lap": "qual",
            "speed": "qual", "race": "race",
        }.get(s['session_type'], "easy")
        target = ""
        if s['target_distance_km']: target = f"{s['target_distance_km']:.0f}km"
        elif s['target_duration_s']: target = f"{s['target_duration_s']//60}min"
        return (f"<tr class='{cls}'><td class='dow'>{days_short[s['day_of_week']]}</td>"
                f"<td class='dt'>{s['date'][5:]}</td>"
                f"<td><span class='pill {type_color}'>{s['session_type']}</span></td>"
                f"<td class='tgt'>{target}</td>"
                f"<td class='presc'>{s['prescription']}</td></tr>")

    plan_html = ""
    for wk in full_plan:
        w = wk['week']
        is_current = w['start_date'] <= today_iso <= (
            (date.fromisoformat(w['start_date']) + timedelta(days=6)).isoformat())
        wk_class = "current-week" if is_current else ""
        plan_html += f"""
<details class="week {wk_class}" {'open' if is_current else ''}>
<summary>
  <span class="wknum">Week {w['week_num']}</span>
  <span class="phase phase-{w['phase']}">{w['phase']}</span>
  <span class="dates">{w['start_date']}</span>
  <span class="km">{w['target_km']:.0f} km · long {w['target_long_km']:.0f} km</span>
  <span class="notes">{w['notes']}</span>
</summary>
<table class="plan-table">
<thead><tr><th>Day</th><th>Date</th><th>Type</th><th>Target</th><th>Prescription</th></tr></thead>
<tbody>
{''.join(session_row(s) for s in wk['sessions'])}
</tbody>
</table>
</details>
"""

    def log_row(l):
        return (f"<tr><td>{l['ts'][:16]}</td><td>{l['date'] or '—'}</td>"
                f"<td>{l['action']}</td><td class='muted'>{l['reason']}</td></tr>")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Coach Dashboard</title>
<style>
:root {{ --bg:#0b0f14; --panel:#121821; --panel-2:#1a2230; --line:#243042;
  --text:#e8edf2; --muted:#8a9aae; --accent:#fc4c02; --accent-2:#22d3ee;
  --good:#22c55e; --warn:#f59e0b; --bad:#ef4444; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif; }}
.wrap {{ max-width:1280px; margin:0 auto; padding:32px 24px 80px; }}
h1 {{ font-size:28px; margin:0 0 4px; letter-spacing:-0.01em; }}
h2 {{ font-size:18px; margin:32px 0 12px; }}
h3 {{ font-size:14px; margin:0 0 6px; color:var(--muted); font-weight:500;
      text-transform:uppercase; letter-spacing:0.05em; }}
.sub {{ color:var(--muted); font-size:13px; margin-bottom:8px; }}
.grid {{ display:grid; gap:16px; }}
.kpi-grid {{ grid-template-columns:repeat(6,1fr); }}
.kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.kpi .v {{ font-size:22px; font-weight:600; }}
.kpi .l {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:0.05em; }}
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px 20px; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-weight:500; text-transform:uppercase; letter-spacing:0.04em; font-size:11px; }}
td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
canvas {{ width:100%; display:block; }}
.legend {{ display:flex; gap:14px; font-size:12px; color:var(--muted); margin-top:6px; flex-wrap:wrap; }}
.legend span::before {{ content:""; display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:middle; }}
.lg-vol::before {{ background:var(--accent); }}
.lg-load::before {{ background:var(--accent-2); }}
.lg-ctl::before {{ background:#60a5fa; }}
.lg-atl::before {{ background:#f472b6; }}
.lg-tsb::before {{ background:#facc15; }}
.h-good {{ color:var(--good); }} .h-warn {{ color:var(--warn); }} .h-bad {{ color:var(--bad); }}
.muted {{ color:var(--muted); }}
details.week {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; margin:8px 0; }}
details.week summary {{ padding:14px 18px; cursor:pointer; display:grid; grid-template-columns: 80px 90px 110px 1fr 2fr; gap:14px; align-items:center; list-style:none; }}
details.week summary::-webkit-details-marker {{ display:none; }}
details.week summary:hover {{ background:var(--panel-2); }}
details.week.current-week {{ border-color:var(--accent); border-width:2px; }}
details.week.current-week summary {{ background:rgba(252,76,2,0.08); }}
.wknum {{ font-weight:600; font-size:14px; }}
.phase {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; text-transform:uppercase; letter-spacing:0.05em; }}
.phase-base {{ background:#1e3a5f; color:#93c5fd; }}
.phase-build {{ background:#1e4f3a; color:#86efac; }}
.phase-tenk {{ background:#5f3a1e; color:#fdba74; }}
.phase-bridge {{ background:#5f1e4f; color:#f0abfc; }}
.phase-sharpen {{ background:#3a1e5f; color:#c4b5fd; }}
.phase-taper {{ background:#3a3a3a; color:#d1d5db; }}
.phase-race {{ background:#5f1e1e; color:#fca5a5; }}
.dates {{ color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }}
.km {{ color:var(--text); font-size:12px; }}
.notes {{ color:var(--muted); font-size:12px; font-style:italic; text-align:right; }}
table.plan-table {{ margin:0; }}
table.plan-table th, table.plan-table td {{ padding:6px 14px; }}
table.plan-table tr.today {{ background:rgba(252,76,2,0.12); }}
table.plan-table tr.today td {{ font-weight:500; }}
table.plan-table tr.done {{ opacity:0.6; }}
table.plan-table tr.past {{ opacity:0.5; }}
.dow {{ font-weight:500; color:var(--muted); width:50px; }}
.dt {{ color:var(--muted); width:60px; font-variant-numeric:tabular-nums; }}
.tgt {{ color:var(--accent-2); font-variant-numeric:tabular-nums; width:60px; }}
.presc {{ color:var(--text); }}
.pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; text-transform:uppercase; letter-spacing:0.04em; font-weight:500; }}
.pill.easy {{ background:#1e3a5f; color:#93c5fd; }}
.pill.long {{ background:#1e4f3a; color:#86efac; }}
.pill.rest {{ background:#2a2a2a; color:#9ca3af; }}
.pill.strength {{ background:#5f3a1e; color:#fdba74; }}
.pill.qual {{ background:#5f1e4f; color:#f0abfc; }}
.pill.race {{ background:#5f1e1e; color:#fca5a5; }}
.tooltip {{ position:fixed; z-index:50; pointer-events:none; background:#0b0f14; border:1px solid var(--line); border-radius:6px; padding:6px 10px; font-size:12px; white-space:nowrap; box-shadow:0 4px 18px rgba(0,0,0,0.4); display:none; }}
hr {{ border:none; border-top:1px solid var(--line); margin:28px 0 0; }}
</style></head><body><div class="wrap">

<h1>Coach Dashboard</h1>
<div class="sub">{runs[0]['start_dt'][:10]} → {runs[-1]['start_dt'][:10]} · {total_runs} runs · live from coach.db</div>

<h2>At a glance</h2>
<div class="grid kpi-grid">
  <div class="kpi"><div class="l">Runs</div><div class="v">{total_runs:,}</div></div>
  <div class="kpi"><div class="l">Distance</div><div class="v">{total_km:,.0f} km</div></div>
  <div class="kpi"><div class="l">Time</div><div class="v">{total_hours:,.0f} h</div></div>
  <div class="kpi"><div class="l">Ascent</div><div class="v">{total_ascent:,.0f} m</div></div>
  <div class="kpi"><div class="l">Current CTL</div><div class="v">{cur['ctl']:.1f}</div></div>
  <div class="kpi"><div class="l">Current TSB</div><div class="v">{cur['tsb']:+.1f}</div></div>
</div>

<h2>Fitness vs fatigue (CTL/ATL/TSB)</h2>
<div class="panel">
  <canvas id="cFit" height="280"></canvas>
  <div class="legend">
    <span class="lg-ctl">CTL — fitness</span>
    <span class="lg-atl">ATL — fatigue</span>
    <span class="lg-tsb">TSB — form</span>
  </div>
  <div style="margin-top:12px"><strong>Peak fitness:</strong> {peak_ctl:.1f} CTL on {peak_date}</div>
</div>

<h2>Volume by month</h2>
<div class="panel">
  <canvas id="cVol" height="220"></canvas>
  <div class="legend"><span class="lg-vol">km / month</span><span class="lg-load">training load</span></div>
</div>

<h2>Day-by-day plan</h2>
<div class="sub">Current week is auto-expanded. Click any week to expand. Today is highlighted orange.</div>
{plan_html}

<h2>Plan vs actual (week-level rollup)</h2>
<div class="panel">
<table>
  <thead><tr><th>Wk</th><th>Start</th><th>Phase</th><th class="num">Planned km</th><th class="num">Actual km</th><th class="num">% of plan</th></tr></thead>
  <tbody>
""" + "".join(plan_row(p) for p in plan_vs) + f"""
  </tbody>
</table>
</div>

<h2>Recent coach decisions</h2>
<div class="panel">
""" + ("<table><thead><tr><th>When</th><th>Date</th><th>Action</th><th>Reason</th></tr></thead><tbody>"
       + "".join(log_row(l) for l in log[:20]) + "</tbody></table>"
       if log else "<p class='muted'>No coach_log entries yet.</p>") + f"""
</div>

<h2>Year-by-year</h2>
<div class="panel">
<table>
  <thead><tr><th>Year</th><th class="num">Runs</th><th class="num">km</th><th class="num">Hours</th><th class="num">Ascent</th><th class="num">Avg pace</th><th class="num">Avg HR</th><th class="num">Best 5K</th><th class="num">Best 10K</th><th class="num">Longest</th><th class="num">Long runs</th><th class="num">Load</th></tr></thead>
  <tbody>
""" + "".join(yr_row(y) for y in yearly) + f"""
  </tbody>
</table>
</div>

<hr><p class="muted">Generated {datetime.now().strftime('%d %b %Y %H:%M')} from coach.db. CTL/ATL/TSB use exponential 42-day / 7-day half-lives over locally computed TRIMP scores (HRmax 198, HRrest 50).</p>
<div class="tooltip" id="tt"></div>

<script>
const monthly = {js(monthly)};
const weekly  = {js(weekly_curves)};

function setupCanvas(c) {{
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  c.width = w*dpr; c.height = h*dpr;
  const ctx = c.getContext('2d'); ctx.scale(dpr,dpr);
  return {{ctx, w, h}};
}}

(function(){{
  const c = document.getElementById('cVol');
  const {{ctx, w, h}} = setupCanvas(c);
  const pad = {{l:40, r:40, t:20, b:24}};
  const N = monthly.length;
  if (!N) return;
  const maxKm = Math.max(...monthly.map(m=>m.km), 1);
  const maxLoad = Math.max(...monthly.map(m=>m.load), 1);
  ctx.strokeStyle = '#243042';
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, h-pad.b); ctx.lineTo(w-pad.r, h-pad.b);
  ctx.stroke();
  const barW = (w-pad.l-pad.r)/N * 0.7;
  monthly.forEach((m,i) => {{
    const x = pad.l + (w-pad.l-pad.r)*i/(N-1) - barW/2;
    const y = pad.t + (h-pad.t-pad.b)*(1 - m.km/maxKm);
    ctx.fillStyle = '#fc4c02';
    ctx.fillRect(x, y, barW, h-pad.b-y);
  }});
  ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 2; ctx.beginPath();
  monthly.forEach((m,i) => {{
    const x = pad.l + (w-pad.l-pad.r)*i/(N-1);
    const y = pad.t + (h-pad.t-pad.b)*(1 - m.load/maxLoad);
    if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  }});
  ctx.stroke();
  ctx.fillStyle='#8a9aae'; ctx.font='10px -apple-system';
  monthly.forEach((m,i) => {{
    if (i % 6 !== 0) return;
    const x = pad.l + (w-pad.l-pad.r)*i/(N-1);
    ctx.fillText(m.label, x-14, h-pad.b+14);
  }});
}})();

(function(){{
  const c = document.getElementById('cFit');
  const {{ctx, w, h}} = setupCanvas(c);
  const pad = {{l:44, r:14, t:20, b:24}};
  const N = weekly.length; if (!N) return;
  const yMax = Math.max(...weekly.flatMap(w=>[w.ctl,w.atl,w.tsb]))+5;
  const yMin = Math.min(...weekly.flatMap(w=>[w.tsb,0]))-5;
  ctx.strokeStyle='#243042'; ctx.beginPath();
  ctx.moveTo(pad.l,pad.t); ctx.lineTo(pad.l,h-pad.b); ctx.lineTo(w-pad.r,h-pad.b);
  ctx.stroke();
  const yZero = pad.t + (h-pad.t-pad.b)*(1-(0-yMin)/(yMax-yMin));
  ctx.strokeStyle='rgba(255,255,255,0.12)'; ctx.setLineDash([2,4]);
  ctx.beginPath(); ctx.moveTo(pad.l,yZero); ctx.lineTo(w-pad.r,yZero); ctx.stroke();
  ctx.setLineDash([]);
  function line(arr, color, lw) {{
    ctx.strokeStyle=color; ctx.lineWidth=lw; ctx.beginPath();
    arr.forEach((v,i) => {{
      const x = pad.l + (w-pad.l-pad.r)*i/(N-1);
      const y = pad.t + (h-pad.t-pad.b)*(1-(v-yMin)/(yMax-yMin));
      if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }});
    ctx.stroke();
  }}
  line(weekly.map(w=>w.ctl), '#60a5fa', 2);
  line(weekly.map(w=>w.atl), '#f472b6', 1.5);
  line(weekly.map(w=>w.tsb), '#facc15', 1.5);
  ctx.fillStyle='#8a9aae'; ctx.font='10px -apple-system';
  for (let i=0; i<8; i++) {{
    const idx = Math.floor((N-1)*i/7);
    const x = pad.l + (w-pad.l-pad.r)*idx/(N-1);
    ctx.fillText(weekly[idx].d.slice(0,7), x-18, h-pad.b+14);
  }}
}})();
</script>
</div></body></html>"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--open", action="store_true", help="Open in browser after generating")
    args = p.parse_args(argv)
    html = render()
    args.out.write_text(html, encoding='utf-8')
    print(f"Wrote {args.out} ({args.out.stat().st_size//1024} KB)")
    if args.open:
        import subprocess
        subprocess.run(["open", str(args.out)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
