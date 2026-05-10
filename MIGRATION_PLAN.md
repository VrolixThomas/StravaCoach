# Migration plan — Bun web app + Supabase

Migrate the Python+SQLite coach into a Bun-powered Next.js web app on Vercel, backed by Supabase Postgres. Keep the Claude skill working throughout. Estimated total effort: 18-25 hours focused work.

## Final stack (decided based on 2026 research)

| Layer | Choice | Why |
|-|-|-|
| Framework | **Next.js 16 App Router** | Vercel-native, App Router stable, richest React chart ecosystem |
| Runtime | **Bun on Vercel** (native, public beta) | ~28% faster cold starts vs Node, single tool for dev + deploy |
| Database | **Supabase Postgres** | Managed, free tier fits, realtime + auth bundled |
| ORM / DB client | **Drizzle ORM** | TS-native, lightweight, plays well with Postgres + Bun. Alternative: `@supabase/supabase-js` for read-mostly |
| Auth | **Supabase magic link** | Single-user, no OAuth dance, free |
| Styling | **Tailwind CSS v4** | Default in Next 16 setups |
| Charts | **Recharts** | Tabular numerals, dark mode, line+bar+area, no enterprise pricing |
| Strava sync | **Webhooks → API route** + Vercel daily cron fallback | Real-time on new activity, cron catches misses |
| Connection pool | **Supabase PgBouncer (port 6543)** | Required for serverless functions |

**Skipped/deferred:**
- Row Level Security (single user — magic-link auth is the security boundary)
- Realtime subscriptions (overkill for daily check-in cadence; revisit if needed)
- SvelteKit/Remix (Next.js wins for chart libs + Vercel features)

## The big architectural question: what happens to Python?

Three paths, ranked. Pick one before any code is written.

### Path A — Full TS rewrite (recommended)

Rewrite `coach/*.py` as TS modules in the Next.js app. Same logic (TRIMP, CTL/ATL, plan adjustments) as TypeScript. CLI scripts via `bun run coach:brief` etc. Python becomes a one-time migration script then sunsets.

**Pros:**
- Single codebase, single deploy target
- Web app and engine share types
- Skill calls `bun run coach:X` — same Bash UX
- No two-DB-state risk

**Cons:**
- ~1000 lines to port
- Must re-test every adjustment op against real DB

**Effort: ~14 hours.**

### Path B — Keep Python, point at Supabase

Swap `sqlite3` for `psycopg2` / `supabase-py` in the existing Python. Web app is read-only viewer hitting Supabase from Next.js. Python runs locally for now, eventually on a cron service (Railway / Render / GitHub Actions).

**Pros:**
- ~3 hours of changes to Python
- All existing skill invocations still work
- Lowest risk to coaching continuity

**Cons:**
- Two deployment targets to maintain
- Python writes happen out-of-band from web app
- If laptop is off, no sync (until you set up external cron)

**Effort: ~6 hours (web app read-only) + Python edits.**

### Path C — Hybrid (read-only web, Python writes)

Web app is read-only. Python remains the writer. Skill keeps calling Python.

**Pros:**
- Smallest blast radius
- Web app deployable in a weekend

**Cons:**
- Awkward division of responsibility
- Doesn't fully solve "host on Vercel easily"

**Effort: ~8 hours.**

### Recommendation: Path A

Path A pays off the most over 6+ months. The plan below assumes A. If you want to shortcut to a deployed dashboard fast, Path C is the off-ramp; we can revisit A later.

## Target architecture (Path A)

```
┌──────────────────┐
│   Strava API     │
└────────┬─────────┘
         │ webhook on new activity
         │ (or daily cron fallback)
         ▼
┌─────────────────────────────────────────────────┐
│  Vercel deployment                               │
│  ┌──────────────────┐  ┌──────────────────────┐ │
│  │  Next.js routes  │  │  API routes          │ │
│  │  - /             │  │  - /api/strava/sync  │ │
│  │  - /plan         │  │  - /api/strava/      │ │
│  │  - /load         │  │    webhook           │ │
│  │  - /history      │  │  - /api/adjust       │ │
│  │  - /settings     │  │  - /api/checkin      │ │
│  │  (RSC + Recharts)│  │  (Bun runtime)       │ │
│  └────────┬─────────┘  └─────────┬────────────┘ │
│           │                       │              │
│           └───────────┬───────────┘              │
│                       │ Drizzle ORM              │
└───────────────────────┼──────────────────────────┘
                        │ PgBouncer :6543
                        ▼
                ┌───────────────┐
                │  Supabase     │
                │  Postgres     │
                │  + Auth       │
                └───────────────┘
                        ▲
                        │ same DB
                        │
              ┌─────────┴────────┐
              │  Local CLI       │
              │  bun run coach:* │
              │  (used by skill) │
              └──────────────────┘
```

## Repo structure (post-migration)

```
~/Documents/strava-coach/                    ← rename from strava-dashboard
├── README.md
├── CLAUDE.md
├── package.json                             ← bun + next + drizzle + recharts
├── bun.lockb
├── vercel.json                              ← bunVersion: "1.x", cron config
├── next.config.ts
├── tailwind.config.ts
├── drizzle.config.ts
├── .env.local                               ← STRAVA_*, SUPABASE_*, dev only
│
├── src/
│   ├── app/                                 ← Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx                         ← today's session + readiness
│   │   ├── plan/page.tsx                    ← week-by-week
│   │   ├── load/page.tsx                    ← CTL/ATL/TSB charts
│   │   ├── history/page.tsx                 ← retrospective view (legacy dashboard)
│   │   ├── settings/page.tsx                ← Strava OAuth, pace targets
│   │   ├── api/
│   │   │   ├── strava/sync/route.ts         ← incremental pull
│   │   │   ├── strava/webhook/route.ts      ← realtime push
│   │   │   ├── strava/auth/route.ts         ← OAuth initiate
│   │   │   ├── strava/callback/route.ts     ← OAuth callback
│   │   │   ├── adjust/route.ts              ← propose/apply/reject
│   │   │   ├── checkin/route.ts             ← daily checkin POST
│   │   │   └── cron/sync/route.ts           ← daily cron job
│   │   └── auth/
│   │       └── (supabase magic link pages)
│   ├── components/
│   │   ├── charts/
│   │   │   ├── FitnessChart.tsx             ← CTL/ATL/TSB
│   │   │   ├── VolumeChart.tsx              ← km + load
│   │   │   ├── PaceChart.tsx                ← pace/HR/eff
│   │   │   └── PlanGrid.tsx                 ← week-by-week table
│   │   ├── PlanWeekCard.tsx
│   │   ├── SessionRow.tsx
│   │   ├── CheckinForm.tsx
│   │   └── ReadinessBadge.tsx
│   ├── lib/
│   │   ├── db/
│   │   │   ├── schema.ts                    ← Drizzle schema
│   │   │   ├── client.ts                    ← supabase + drizzle setup
│   │   │   └── queries/                     ← typed query helpers
│   │   ├── coach/                           ← engine logic, ported from Python
│   │   │   ├── load.ts                      ← TRIMP, CTL/ATL/TSB
│   │   │   ├── plan.ts                      ← 20-week template + seed
│   │   │   ├── adjust.ts                    ← propose/apply/reject
│   │   │   ├── brief.ts                     ← read-only state dumps
│   │   │   └── strava.ts                    ← API client + sync
│   │   └── utils/
│   │       ├── pace.ts                      ← format helpers
│   │       └── dates.ts
│   └── scripts/                             ← bun run coach:X
│       ├── seed-plan.ts                     ← bun run coach:seed
│       ├── checkin.ts                       ← bun run coach:checkin
│       ├── brief.ts                         ← bun run coach:brief
│       ├── adjust.ts                        ← bun run coach:adjust
│       └── sync.ts                          ← bun run coach:sync
│
├── migrations/                              ← drizzle generated
│   └── 0000_initial.sql
│
├── .claude/
│   └── skills/
│       └── coach/                           ← skill stays — only commands change
│           ├── SKILL.md                     ← updated `!`...`` blocks
│           └── references/, examples/
│
└── _legacy/                                 ← Python kept for reference, not used
    ├── coach/
    ├── prepare.py
    ├── app.py
    └── lib/
```

## Migration phases

Each phase is shippable + reversible. Don't proceed if the current phase isn't green.

### Phase 0 — Decisions + accounts (1 hr)

- [ ] Confirm Path A (full TS rewrite). If Path B/C, the rest of this plan changes.
- [ ] Create Supabase project (free tier). Capture URL + anon key + service role key.
- [ ] Create Vercel account + project (don't deploy yet).
- [ ] Decide repo location: rename `strava-dashboard` → `strava-coach`, or new repo?
- [ ] Push current state to a git branch named `pre-bun-migration` for rollback.

### Phase 1 — Schema migration (2 hr)

- [ ] Translate `coach/db.py` SCHEMA → Drizzle schema in `src/lib/db/schema.ts`. Convert types:
  - SQLite `TEXT` (ISO dates) → Postgres `timestamp with time zone`
  - SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` → Postgres `serial primary key` (or `identity`)
  - SQLite booleans (0/1) → Postgres `boolean`
  - Add `user_id uuid` columns for future RLS (nullable for now, single user)
- [ ] Run Drizzle migration locally against Supabase: `bunx drizzle-kit push`.
- [ ] Verify schema in Supabase dashboard.
- [ ] **Don't migrate data yet** — schema-only first.

### Phase 2 — Data migration (2 hr)

- [ ] Use `pgloader` to bulk-copy `coach.db` → Supabase. Single command:
  ```bash
  pgloader sqlite:///Users/Werk/Documents/strava-dashboard/coach.db \
    postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres
  ```
- [ ] Spot-check counts: `SELECT COUNT(*) FROM activities` should show ~1,005.
- [ ] Spot-check date conversions on a few rows.
- [ ] Re-run `bun run coach:load` (after Phase 4) to verify CTL/ATL/TSB recompute matches what was in SQLite.

### Phase 3 — Next.js + Bun scaffold (2 hr)

- [ ] `bunx create-next-app@latest strava-coach --typescript --tailwind --app`
- [ ] Add `vercel.json` with `"bunVersion": "1.x"`
- [ ] Add Drizzle: `bun add drizzle-orm postgres && bun add -D drizzle-kit`
- [ ] Add Supabase client: `bun add @supabase/supabase-js @supabase/ssr`
- [ ] Add Recharts: `bun add recharts`
- [ ] Set up `.env.local` with all Supabase + Strava credentials
- [ ] First page (`app/page.tsx`): "Hello from Bun + Next + Supabase" with a count from `activities` table. Confirms full stack wired.
- [ ] Local dev: `bun run dev` should hot-reload, hit Supabase, render.

### Phase 4 — Port the engine (read-only first) (4 hr)

Port modules in dependency order:

- [ ] `src/lib/coach/load.ts` — TRIMP + CTL/ATL/TSB (port `coach/load.py`)
- [ ] `src/lib/coach/brief.ts` — read-only state dumps (port `coach/brief.py`)
- [ ] `src/scripts/brief.ts` — CLI wrapper: `bun run coach:brief --section week`
- [ ] Add to `package.json`:
  ```json
  "scripts": {
    "coach:brief": "bun run src/scripts/brief.ts",
    "coach:checkin": "bun run src/scripts/checkin.ts",
    "coach:adjust": "bun run src/scripts/adjust.ts",
    "coach:sync": "bun run src/scripts/sync.ts",
    "coach:seed": "bun run src/scripts/seed-plan.ts"
  }
  ```
- [ ] Verify: `bun run coach:brief --section week` produces same output as current Python version (compare side-by-side against the SQLite copy).

### Phase 5 — Port the writers (4 hr)

- [ ] `src/lib/coach/plan.ts` — phase templates + seed (port `coach/plan.py`)
- [ ] `src/lib/coach/adjust.ts` — propose/apply/reject + 5 ops (port `coach/adjust.py`)
- [ ] `src/scripts/adjust.ts`, `src/scripts/seed-plan.ts` — CLI wrappers
- [ ] Verify: every CLI op produces identical DB state vs Python equivalent on a backup DB.
- [ ] **Critical:** preserve hard rules — race week lock, completed-session protection, every change to `coach_log`.

### Phase 6 — Strava sync as API routes (3 hr)

- [ ] `src/lib/coach/strava.ts` — token refresh + activity fetch (port `coach/strava_sync.py`)
- [ ] `src/app/api/strava/auth/route.ts` — initiate OAuth (redirect to Strava)
- [ ] `src/app/api/strava/callback/route.ts` — handle callback, exchange code, store tokens in Supabase (new `strava_tokens` table or use Supabase user metadata)
- [ ] `src/app/api/strava/sync/route.ts` — incremental pull, write to `activities`
- [ ] `src/app/api/strava/webhook/route.ts` — handle webhook event (verify owner_id, fetch activity, write)
- [ ] `src/app/api/cron/sync/route.ts` — daily cron handler (calls sync route)
- [ ] Add to `vercel.json`:
  ```json
  "crons": [{"path": "/api/cron/sync", "schedule": "0 6 * * *"}]
  ```
- [ ] Register Strava webhook subscription pointing to deployed `/api/strava/webhook`
- [ ] Verify: a fresh activity in Strava lands in Supabase within ~30 seconds (webhook) or within 24h (cron fallback)

### Phase 7 — UI pages with Recharts (4 hr)

Port the dashboard sections:

- [ ] `src/app/page.tsx` — today's session, readiness, latest checkin form
- [ ] `src/app/plan/page.tsx` — full 20-week plan, current week expanded, color-coded session pills (replicate the dashboard.html plan view)
- [ ] `src/app/load/page.tsx` — CTL/ATL/TSB Recharts line chart, volume bars
- [ ] `src/app/history/page.tsx` — year-by-year table, monthly km, retrospective stats (replaces the current dashboard.html retrospective)
- [ ] `src/app/settings/page.tsx` — Strava OAuth status, pace target overrides, manual sync button
- [ ] All Server Components where possible; client components only for charts + forms
- [ ] Tailwind dark mode default; match the current dashboard's color palette

### Phase 8 — Auth (1 hr)

- [ ] Wire Supabase Auth magic link
- [ ] Wrap protected routes in middleware (`src/middleware.ts`)
- [ ] Single allowed email: yours. Reject all others (Supabase user metadata check, or `auth.users` filter)
- [ ] Sign-in page at `/auth/login`

### Phase 9 — Update the Claude skill (30 min)

- [ ] Edit `.claude/skills/coach/SKILL.md` — replace every `python -m coach.X` with `bun run coach:X`
- [ ] Update `references/pace-zones.md` — mention TS module locations not Python
- [ ] Update `CLAUDE.md` (project root) — same
- [ ] Test: open new Claude Code session in the project, run `/coach-review`, verify it can read state via the new commands

### Phase 10 — Deploy to Vercel (1 hr)

- [ ] Connect Vercel to git repo
- [ ] Set environment variables in Vercel dashboard (all `SUPABASE_*` and `STRAVA_*`)
- [ ] Deploy. Verify: dashboard loads at `<your-app>.vercel.app`, magic link works, charts render
- [ ] Update Strava app's "Authorization Callback Domain" to include the Vercel URL
- [ ] Re-run OAuth flow against production (saves tokens to Supabase, not local file)
- [ ] Trigger first cron manually via Vercel dashboard to verify sync works

### Phase 11 — Sunset Python (30 min)

- [ ] Move `coach/`, `prepare.py`, `app.py`, `lib/` → `_legacy/`
- [ ] Update `README.md` to mention legacy is preserved but not maintained
- [ ] Keep `coach.db.bak` for 30 days as final rollback option
- [ ] Delete `.venv/` (free disk)

## Critical risks + mitigations

| Risk | Likelihood | Mitigation |
|-|-|-|
| Coaching continuity broken during migration | High | Keep Python working in parallel until Phase 9 passes. Don't delete Python until Phase 11. |
| Data loss in pgloader migration | Low | Keep `coach.db` untouched; pgloader copies, doesn't move. Verify counts post-migration. |
| Skill commands stop working mid-migration | Medium | Phase 4 tests the read path before any Python is removed. Phase 9 explicit cutover. |
| Strava token re-auth required on prod | Certain | Re-run OAuth against deployed app. Tokens in Supabase, not local file. |
| Drizzle schema drift from SQLite | Medium | Use `pgloader` for data + Drizzle for schema; don't try to use Drizzle to import. Schema first, data second. |
| Vercel cron free tier (1/day) insufficient | Low | Webhooks handle real-time. Cron is just safety net — daily is fine. |
| TRIMP / CTL math drift in TS port | Medium | Cross-validate: load 30 days into both, compare CTL/ATL within 0.1. Same formula, same constants. |
| Bun runtime quirks on Vercel (still beta) | Low | Fall back to Node runtime if Bun causes issues. One-line vercel.json change. |
| Recharts performance on 8 years of daily data | Medium | Downsample to weekly for the long-range fitness chart (already done in current dashboard). |
| Race week 20 lock not enforced in TS | Critical | Port the `_check_lock` logic with the same hard-fail behavior. Add a unit test. |

## What stays unchanged

- The 20-week plan template content (paces, sessions, prescriptions)
- The hard rules (race week lock, completed-session immutability, coach_log audit)
- The Claude skill structure (SKILL.md + references + examples) — only the embedded commands change
- The athlete profile + goals (CLAUDE.md content)
- The TRIMP formula + HRmax/HRrest constants

## Cost estimate

- **Supabase free tier:** 500 MB Postgres, 50K MAU. We use ~50 MB and 1 user. **Free.**
- **Vercel Hobby (free):** 100 GB bandwidth, 1 cron/day. Fits. **Free.**
- **Strava API:** Free.
- **Bun:** Free.
- **Total monthly: $0** until traffic or storage grows 100x.

If you eventually want sub-daily cron (e.g. every 6h fallback), Vercel Pro is $20/mo. Probably never needed.

## Effort summary

| Phase | Time | Cumulative |
|-|-|-|
| 0. Decisions + accounts | 1 hr | 1 hr |
| 1. Schema migration | 2 hr | 3 hr |
| 2. Data migration | 2 hr | 5 hr |
| 3. Next.js scaffold | 2 hr | 7 hr |
| 4. Port engine (read) | 4 hr | 11 hr |
| 5. Port engine (write) | 4 hr | 15 hr |
| 6. Strava sync routes | 3 hr | 18 hr |
| 7. UI pages | 4 hr | 22 hr |
| 8. Auth | 1 hr | 23 hr |
| 9. Update skill | 30 min | 23.5 hr |
| 10. Deploy | 1 hr | 24.5 hr |
| 11. Sunset Python | 30 min | 25 hr |

**Realistic calendar: 4-6 sessions of 4-6 hours each.** Not a one-weekend project.

## Decision points before building

1. **Path A (full rewrite) vs Path C (read-only web + Python writes)?** Affects scope by ~10 hours.
2. **New repo or in-place?** New repo is cleaner; in-place keeps git history.
3. **Supabase magic link vs Vercel Password Protection?** Magic link is more secure; password is faster. Either is fine for 1 user.
4. **Drizzle ORM vs raw `@supabase/supabase-js`?** Drizzle gives types + migrations; Supabase JS is simpler but you write SQL or use the query builder. Drizzle is the better long-term choice.
5. **Keep the legacy Streamlit retrospective dashboard, or merge it into the Next.js `/history` page?** Merging is cleaner; keeping Streamlit costs nothing but it's a dead end.

## Open questions to discuss before Phase 0

- Do you have a domain you want to attach (or Vercel subdomain is fine)?
- Are you OK with the daily cron schedule (06:00 UTC) or want a different time?
- Want me to set up a GitHub repo + CI checks before starting, or skip CI for personal use?
- Pace target re-anchoring: now's the time to fix that "constants in code" issue. Move to a `pace_targets` Postgres table with effective dates, so the week-12 TT calibration just inserts a row?
