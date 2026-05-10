# Pace zones, TRIMP & load math

## Pace targets per phase

Anchored on Thomas's 5K PR (17:30) and 2021 best 10K pace (3:53/km). All in min/km.

| Pace name | Value | Used for | Description |
|-|-|-|-|
| Recovery | 5:30–6:00 | Day after quality, post-long-run | Easy enough to talk in full sentences. HR cap 130. |
| Easy | 5:00–5:20 | Standard easy days, base building | Conversational. HR cap 145–150. |
| Long-run | 5:15–5:35 | Long runs in base & build phases | Slightly easier than easy pace, sustained. |
| Marathon pace | 4:30–4:40 | Steady-state efforts (not currently target) | — |
| Threshold | 4:10–4:25 | Tempo + threshold reps in build/10K phase | Comfortably hard. HR ~85% max. ~10K race effort. |
| 10K race | 3:50–4:00 | 1km reps in 10K block, race target | Hard. HR ~90% max. |
| 5K race | 3:30 | 400m–800m reps, primer | Very hard. HR 92–95% max. |
| VO₂max (400m) | 1:25–1:30 (≈3:35/km) | 400m / 600m intervals | Brutal but short. |
| Lap event (520m) | 1:18–1:20 (≈2:30/km) | Cold-start 520m repeats wks 13–20 | Sprint pace. Anaerobic. Goal pace for 24h event laps. |

## TRIMP formula (Banister)

```
HRR  = (avg_hr - HR_REST) / (HR_MAX - HR_REST)         clamped to [0,1]
TRIMP = minutes × HRR × 0.64 × exp(1.92 × HRR)
```

Constants in `coach/load.py`:
- `HR_MAX = 198`
- `HR_REST = 50`

If avg_hr is missing → fallback `TRIMP = minutes × 0.5` (treat as easy).

## CTL / ATL / TSB

Daily TRIMP totals are smoothed:

```
α_42 = 1 - exp(ln(0.5) / 42)    # ≈ 0.0163, half-life 42 days
α_7  = 1 - exp(ln(0.5) / 7)     # ≈ 0.0941, half-life 7 days

CTL[t] = α_42 × TRIMP[t] + (1 - α_42) × CTL[t-1]    # fitness
ATL[t] = α_7  × TRIMP[t] + (1 - α_7)  × ATL[t-1]    # fatigue
TSB[t] = CTL[t] - ATL[t]                              # form
```

Same convention as TrainingPeaks.

### Reading the curves

| TSB range | Interpretation |
|-|-|
| > +25 | Detraining or peak taper |
| +10 to +25 | Fresh, race-ready |
| -10 to +10 | Productive training zone |
| -10 to -20 | Loaded, tolerable short-term |
| -20 to -25 | Overload — recovery needed |
| < -25 | Critical — force rest |

### Reading CTL changes

- CTL rising 3-7 / week = healthy build
- CTL flat = maintenance
- CTL dropping >5 / week = detraining or forced break
- CTL rising >10 / week = ramp too fast, injury risk

## HR zones (% of HRmax)

| Zone | % HRmax | bpm range (HRmax 198) | Use |
|-|-|-|-|
| Z1 recovery | <70% | <139 | Recovery jogs, walking |
| Z2 easy | 70-80% | 139–158 | All easy + long runs |
| Z3 tempo | 80-87% | 158–172 | Steady-state work (rare in current plan) |
| Z4 threshold | 87-93% | 172–184 | Threshold reps, 10K efforts |
| Z5 VO₂max | 93-100% | 184–198 | Short intervals, 5K-pace |

## Pace–HR decoupling

If during an easy run, HR drifts >5 bpm in second half at constant pace → aerobic system not recovered. Note in coach_log; if recurs 3+ runs, scale current week by 0.85.

## Lap event math

Goal: each 520m lap under 1:23 (ceiling), targeting 1:18-1:20 (2:30-2:35/km).

```
Lap pace 1:18 = 78 sec / 520 m × 1000 = 150 sec/km = 2:30/km
Lap pace 1:23 = 83 sec / 520 m × 1000 = 159.6 sec/km = 2:39.6/km
```

For Thomas's 5K PR (17:30 = 3:30/km), this lap pace is significantly faster. Achievable on fresh legs given:
- 10 reps total over 24h → multi-hour rest each
- Speed-on-demand training in weeks 13-20
- Strong aerobic base from 10K block enables better recovery between laps

## Constants in code

If pace targets need re-anchoring (e.g. after 10K TT shows higher fitness), edit at top of `coach/plan.py`:

```python
EASY_PACE = 5.20
LONG_PACE = 5.30
THRESHOLD_PACE = 4.20
TENK_RACE_PACE = 4.00
VO2_PACE_400 = 3.55
LAP_PACE = 2.55
```

Then re-seed: `python -m coach.plan --seed YYYY-MM-DD`. **Re-seeding wipes plan_sessions and coach_log adjustments are lost** — only do this between phases.

(Future: move these to a `pace_targets` table so re-seed preserves history. Tracked in SKILL_PLAN.md open Q3.)
