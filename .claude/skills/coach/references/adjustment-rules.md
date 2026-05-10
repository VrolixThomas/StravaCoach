# Adjustment decision matrix

The single source of truth for "when do I change the plan, and to what?". Each row: trigger condition → recommended adjustment. Pick the smallest change that addresses the issue.

## Triggers based on training load

| Trigger | Action | Severity |
|-|-|-|
| TSB > +15 for 3+ days | Bring forward a quality session, or compress taper if near race | low |
| TSB between -10 and +10 | Proceed as planned | none |
| TSB <-15 for 1 day | Note it, no action yet | low |
| TSB <-15 for 3+ days | `replace` next quality with easy; preserve volume | medium |
| TSB <-20 for 2+ days | `scale_week` next week ×0.85 + replace next quality with easy | high |
| TSB <-25 (any day) | `add` rest day in next 48h; replace any quality in next 4 days | critical |
| CTL drop >5 in 7 days | Volume too low — `scale_week` upcoming week ×1.10 (only if no injury signal) | medium |
| ATL spike +50% in 7 days | Single big session distorted load — verify, then no action unless legs flag | low |

## Triggers based on session execution

| Trigger | Action |
|-|-|
| Quality session pace ≥ target +5% but HR within +5 bpm | No change. Heat / fatigue / fueling — note it. |
| Quality session pace ≥ target +10%, HR ≥ target +10 bpm | `replace` next quality with one tier easier (threshold→tempo, vo2→threshold). |
| Quality session aborted early due to fatigue (not pain) | Replace next quality with easy. Don't cancel — keep the slot for movement. |
| Quality session aborted due to pain | See "Pain" section below. |
| Easy run pace > target +30s/km AND HR > target +5 bpm | Note it. If repeats next session, `replace` next quality with easy. |
| Long run pace blew up in last 25% (HR drift >10%) | Hold long-run distance next week — don't extend. |
| Long run completed on target | Continue progression. |
| Crushed prescription (much faster, low HR) | Keep current plan. Optionally raise next quality target by one notch. Don't add volume. |

## Triggers based on subjective check-ins

| Trigger | Action |
|-|-|
| Legs ≤ 4/10 (single day) | If today is quality: `replace` with rest or 25 min easy. If today is easy: continue but cap HR. |
| Legs ≤ 5/10 (2+ consecutive days) | `add` extra rest in next 48h. Defer next quality by 24-48h. |
| Sleep <6h reported (single day) | If today is quality: replace with easy. |
| Sleep <6h reported (3+ days running) | `scale_week` current week ×0.85. Sleep is the bottleneck. |
| RHR elevated >10 bpm above 7-day average | Treat as illness signal — easy day, no quality. |

## Triggers based on injury / pain language

**Distinguish pain words carefully:**
- "tight", "sore", "stiff" → normal training response, no action unless persists 3+ days
- "hurts", "sharp", "shooting", "stabbing", "swollen", "limping" → pain → action
- "left shin sore for 4 days" → escalating, treat as pain
- "DOMS", "post-long-run sore" → expected, no action

| Trigger | Action |
|-|-|
| First mention of pain in shin/knee/calf/achilles | `cancel` next quality session in next 7 days; `replace` it with easy. Surface to user. |
| Pain persisting 3+ days OR pain mentioned 2+ checkins | `cancel` ALL quality for 7 days; `replace` with easy or cross-train. Recommend rest day if not present. Tell user to consider seeing physio. |
| Pain that prevents running | `cancel` all running for next 5 days; `replace` long run with cross-train (bike/swim) if available. |

## Triggers based on plan completion

| Trigger | Action |
|-|-|
| 1 missed session | If quality and rescheduling possible same week → `shift` to next available day with no quality back-to-back. Else accept the loss. |
| 2 missed sessions | `scale_week` next week ×0.90. Don't try to make up missed work. |
| 3+ missed sessions | Don't adjust week-by-week — escalate. Tell user the plan may need re-seeding (call `python -m coach.plan --seed`). |
| Sequence of 5+ on-plan sessions | No adjustment. Acknowledge in brief. |

## Auto-apply vs propose-only

| Op + scope | Default behavior |
|-|-|
| `shift` single session within same week | Auto-apply |
| `replace` single session, lower intensity | Auto-apply |
| `replace` single session, higher intensity | Propose, ask user |
| `cancel` single session | Auto-apply if reason is fatigue/pain; propose if reason is schedule |
| `scale_week` (any factor) | Always propose, never auto-apply |
| `add` rest or easy session | Auto-apply |
| `add` quality session | Propose |
| Anything in race week (week 20) | Always propose, even if user asks for it directly |

## Conflict resolution

If two rules suggest different actions, follow this priority:
1. Pain rules (always win)
2. TSB rules
3. Subjective check-in rules
4. Session execution rules
5. Plan completion rules

Example: TSB <-25 says "force rest" AND legs 8/10 says "proceed". Pain rules don't apply. TSB beats subjective → force rest.

## What NOT to adjust

- Don't move long runs unless absolutely necessary. They're the spine.
- Don't replace strength sessions with running — they protect the shins.
- Don't compress phase boundaries (don't move from base to build early).
- Don't extend long runs beyond what the phase template prescribes — even if the user is feeling great.
- Don't add quality "to make up" for a missed quality. Volume + consistency > catching up.
