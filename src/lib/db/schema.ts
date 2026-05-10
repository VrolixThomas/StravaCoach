/**
 * Drizzle schema — Postgres port of coach/db.py SQLite schema.
 *
 * Mapping notes:
 * - SQLite TEXT (ISO timestamp) → Postgres timestamp with time zone
 * - SQLite INTEGER PRIMARY KEY AUTOINCREMENT → Postgres bigserial
 * - SQLite INTEGER booleans (0/1) → Postgres boolean
 * - Added `user_id uuid` columns (nullable for v1, required when multi-user)
 * - New `pace_targets` table replaces hardcoded constants in coach/plan.py
 */
import {
  pgTable,
  bigserial,
  text,
  doublePrecision,
  integer,
  timestamp,
  boolean,
  uuid,
  index,
  jsonb,
  date,
} from "drizzle-orm/pg-core";

// ──────────────────────────────────────────────────────────────────
// activities — mirrors Strava
// ──────────────────────────────────────────────────────────────────
export const activities = pgTable(
  "activities",
  {
    id: integer("id").primaryKey(), // Strava activity ID, NOT serial
    userId: uuid("user_id"),
    startDt: timestamp("start_dt", { withTimezone: true }).notNull(),
    type: text("type"),
    name: text("name"),
    distanceM: doublePrecision("distance_m"),
    movingS: integer("moving_s"),
    elapsedS: integer("elapsed_s"),
    avgHr: doublePrecision("avg_hr"),
    maxHr: doublePrecision("max_hr"),
    avgSpeed: doublePrecision("avg_speed"),
    gapSpeed: doublePrecision("gap_speed"),
    totalAscent: doublePrecision("total_ascent"),
    cadence: doublePrecision("cadence"),
    calories: doublePrecision("calories"),
    perceivedExertion: doublePrecision("perceived_exertion"),
    sufferScore: doublePrecision("suffer_score"),
    hasHeartrate: boolean("has_heartrate").default(false),
    rawJson: jsonb("raw_json"),
    fetchedAt: timestamp("fetched_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    startDtIdx: index("idx_activities_dt").on(t.startDt),
    typeIdx: index("idx_activities_type").on(t.type),
    userIdx: index("idx_activities_user").on(t.userId),
  })
);

// ──────────────────────────────────────────────────────────────────
// daily_load — TRIMP / CTL / ATL / TSB curves
// ──────────────────────────────────────────────────────────────────
export const dailyLoad = pgTable("daily_load", {
  date: date("date").primaryKey(),
  userId: uuid("user_id"),
  trimp: doublePrecision("trimp").default(0),
  km: doublePrecision("km").default(0),
  movingS: integer("moving_s").default(0),
  ctl: doublePrecision("ctl"),
  atl: doublePrecision("atl"),
  tsb: doublePrecision("tsb"),
});

// ──────────────────────────────────────────────────────────────────
// plan_weeks — phases of the training plan
// ──────────────────────────────────────────────────────────────────
export const planWeeks = pgTable("plan_weeks", {
  weekNum: integer("week_num").primaryKey(),
  userId: uuid("user_id"),
  startDate: date("start_date").notNull(),
  phase: text("phase").notNull(),
  targetKm: doublePrecision("target_km"),
  targetLongKm: doublePrecision("target_long_km"),
  notes: text("notes"),
});

// ──────────────────────────────────────────────────────────────────
// plan_sessions — every prescribed session
// ──────────────────────────────────────────────────────────────────
export const planSessions = pgTable(
  "plan_sessions",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    userId: uuid("user_id"),
    weekNum: integer("week_num")
      .notNull()
      .references(() => planWeeks.weekNum),
    date: date("date").notNull(),
    dayOfWeek: integer("day_of_week").notNull(),
    sessionType: text("session_type").notNull(),
    prescription: text("prescription").notNull(),
    targetDistanceKm: doublePrecision("target_distance_km"),
    targetDurationS: integer("target_duration_s"),
    targetPaceMinKm: doublePrecision("target_pace_min_km"),
    matchedActivityId: integer("matched_activity_id").references(() => activities.id),
    status: text("status").default("planned"), // planned|completed|skipped|modified
    completionNote: text("completion_note"),
  },
  (t) => ({
    dateIdx: index("idx_plan_sessions_date").on(t.date),
    statusIdx: index("idx_plan_sessions_status").on(t.status),
    userIdx: index("idx_plan_sessions_user").on(t.userId),
  })
);

// ──────────────────────────────────────────────────────────────────
// daily_checkin — subjective ratings
// ──────────────────────────────────────────────────────────────────
export const dailyCheckin = pgTable("daily_checkin", {
  date: date("date").primaryKey(),
  userId: uuid("user_id"),
  legsRating: integer("legs_rating"),
  sleepH: doublePrecision("sleep_h"),
  soreness: text("soreness"),
  rhr: integer("rhr"),
  notes: text("notes"),
});

// ──────────────────────────────────────────────────────────────────
// coach_log — audit trail; every adjustment writes here
// ──────────────────────────────────────────────────────────────────
export const coachLog = pgTable("coach_log", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  userId: uuid("user_id"),
  ts: timestamp("ts", { withTimezone: true }).notNull().defaultNow(),
  date: date("date"),
  reason: text("reason"),
  action: text("action"),
});

// ──────────────────────────────────────────────────────────────────
// proposed_adjustments — staging for plan changes
// ──────────────────────────────────────────────────────────────────
export const proposedAdjustments = pgTable(
  "proposed_adjustments",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    userId: uuid("user_id"),
    proposedAt: timestamp("proposed_at", { withTimezone: true }).notNull().defaultNow(),
    op: text("op").notNull(), // shift|replace|cancel|scale_week|add
    targetDate: date("target_date"),
    targetSessionId: integer("target_session_id"),
    payloadJson: jsonb("payload_json").notNull(),
    reason: text("reason").notNull(),
    status: text("status").default("pending"), // pending|applied|rejected
    decidedAt: timestamp("decided_at", { withTimezone: true }),
  },
  (t) => ({
    statusIdx: index("idx_proposed_status").on(t.status),
  })
);

// ──────────────────────────────────────────────────────────────────
// strava_tokens — OAuth state per user (replaces .strava_tokens.json)
// ──────────────────────────────────────────────────────────────────
export const stravaTokens = pgTable("strava_tokens", {
  userId: uuid("user_id").primaryKey(),
  athleteId: integer("athlete_id").notNull(),
  accessToken: text("access_token").notNull(),
  refreshToken: text("refresh_token").notNull(),
  expiresAt: integer("expires_at").notNull(), // epoch seconds
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// ──────────────────────────────────────────────────────────────────
// pace_targets — replaces hardcoded constants in coach/plan.py.
// Effective-dated rows; current targets = max(effective_from <= today)
// ──────────────────────────────────────────────────────────────────
export const paceTargets = pgTable(
  "pace_targets",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    userId: uuid("user_id"),
    effectiveFrom: date("effective_from").notNull(),
    easyPace: doublePrecision("easy_pace").notNull(), // min/km
    longPace: doublePrecision("long_pace").notNull(),
    thresholdPace: doublePrecision("threshold_pace").notNull(),
    tenkRacePace: doublePrecision("tenk_race_pace").notNull(),
    vo2Pace400: doublePrecision("vo2_pace_400").notNull(),
    lapPace: doublePrecision("lap_pace").notNull(),
    sourceNote: text("source_note"), // "initial seed", "post-week-12 TT", etc.
  },
  (t) => ({
    effectiveIdx: index("idx_pace_targets_effective").on(t.effectiveFrom),
  })
);

// ──────────────────────────────────────────────────────────────────
// sync_state — key/value for last_sync_after timestamp etc.
// ──────────────────────────────────────────────────────────────────
export const syncState = pgTable("sync_state", {
  key: text("key").primaryKey(),
  userId: uuid("user_id"),
  value: text("value"),
});
