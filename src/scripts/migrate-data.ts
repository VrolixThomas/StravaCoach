/**
 * Copy data from coach.db (SQLite) → Supabase Postgres.
 * Preserves primary keys (activities.id, plan_weeks.week_num, sequenced ids).
 * Resets serial sequences afterward.
 *
 * Usage: bun run src/scripts/migrate-data.ts
 */
import { config } from "dotenv";
import { Database } from "bun:sqlite";
import postgres from "postgres";
import { resolve } from "node:path";

config({ path: ".env.local" });

const SQLITE_PATH = resolve("coach.db");
const url = process.env.DATABASE_URL_DIRECT ?? process.env.DATABASE_URL;
if (!url) throw new Error("DATABASE_URL_DIRECT not set");

const sqlite = new Database(SQLITE_PATH, { readonly: true });
const sql = postgres(url, { prepare: false, max: 1 });

// Helper: SQLite int booleans → real booleans
const b = (v: unknown) => (v == null ? null : Boolean(v));

// Helper: SQLite ISO timestamp string → Date for Postgres
const ts = (v: unknown) => (v == null ? null : new Date(v as string));

// Helper: SQLite ISO date string → date string for Postgres
const d = (v: unknown) => (v == null || v === "" ? null : String(v));

type RowMigrator<T> = {
  table: string;
  fetch: () => T[];
  insert: (rows: T[]) => Promise<unknown>;
  resetSeq?: () => Promise<unknown>;
};

const migrators: RowMigrator<any>[] = [
  {
    table: "activities",
    fetch: () => sqlite.query("SELECT * FROM activities ORDER BY id").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({
        id: r.id,
        user_id: null,
        start_dt: ts(r.start_dt),
        type: r.type,
        name: r.name,
        distance_m: r.distance_m,
        moving_s: r.moving_s,
        elapsed_s: r.elapsed_s,
        avg_hr: r.avg_hr,
        max_hr: r.max_hr,
        avg_speed: r.avg_speed,
        gap_speed: r.gap_speed,
        total_ascent: r.total_ascent,
        cadence: r.cadence,
        calories: r.calories,
        perceived_exertion: r.perceived_exertion,
        suffer_score: r.suffer_score,
        has_heartrate: b(r.has_heartrate),
        raw_json: r.raw_json ? JSON.parse(r.raw_json) : null,
        fetched_at: ts(r.fetched_at) ?? new Date(),
      }));
      // Bulk insert in chunks of 500
      for (let i = 0; i < mapped.length; i += 500) {
        const chunk = mapped.slice(i, i + 500);
        await sql`INSERT INTO activities ${sql(chunk)}`;
      }
    },
  },
  {
    table: "plan_weeks",
    fetch: () => sqlite.query("SELECT * FROM plan_weeks ORDER BY week_num").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({
        week_num: r.week_num,
        user_id: null,
        start_date: d(r.start_date),
        phase: r.phase,
        target_km: r.target_km,
        target_long_km: r.target_long_km,
        notes: r.notes,
      }));
      await sql`INSERT INTO plan_weeks ${sql(mapped)}`;
    },
  },
  {
    table: "plan_sessions",
    fetch: () => sqlite.query("SELECT * FROM plan_sessions ORDER BY id").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({
        id: r.id,
        user_id: null,
        week_num: r.week_num,
        date: d(r.date),
        day_of_week: r.day_of_week,
        session_type: r.session_type,
        prescription: r.prescription,
        target_distance_km: r.target_distance_km,
        target_duration_s: r.target_duration_s,
        target_pace_min_km: r.target_pace_min_km,
        matched_activity_id: r.matched_activity_id,
        status: r.status,
        completion_note: r.completion_note,
      }));
      for (let i = 0; i < mapped.length; i += 500) {
        await sql`INSERT INTO plan_sessions ${sql(mapped.slice(i, i + 500))}`;
      }
    },
    resetSeq: () => sql`SELECT setval(pg_get_serial_sequence('plan_sessions', 'id'),
      (SELECT COALESCE(MAX(id), 0) FROM plan_sessions))`,
  },
  {
    table: "daily_load",
    fetch: () => sqlite.query("SELECT * FROM daily_load ORDER BY date").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({
        date: d(r.date),
        user_id: null,
        trimp: r.trimp ?? 0,
        km: r.km ?? 0,
        moving_s: r.moving_s ?? 0,
        ctl: r.ctl,
        atl: r.atl,
        tsb: r.tsb,
      }));
      for (let i = 0; i < mapped.length; i += 500) {
        await sql`INSERT INTO daily_load ${sql(mapped.slice(i, i + 500))}`;
      }
    },
  },
  {
    table: "daily_checkin",
    fetch: () => sqlite.query("SELECT * FROM daily_checkin ORDER BY date").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({
        date: d(r.date),
        user_id: null,
        legs_rating: r.legs_rating,
        sleep_h: r.sleep_h,
        soreness: r.soreness,
        rhr: r.rhr,
        notes: r.notes,
      }));
      await sql`INSERT INTO daily_checkin ${sql(mapped)}`;
    },
  },
  {
    table: "coach_log",
    fetch: () => sqlite.query("SELECT * FROM coach_log ORDER BY id").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({
        id: r.id,
        user_id: null,
        ts: ts(r.ts) ?? new Date(),
        date: d(r.date),
        reason: r.reason,
        action: r.action,
      }));
      await sql`INSERT INTO coach_log ${sql(mapped)}`;
    },
    resetSeq: () => sql`SELECT setval(pg_get_serial_sequence('coach_log', 'id'),
      (SELECT COALESCE(MAX(id), 0) FROM coach_log))`,
  },
  {
    table: "proposed_adjustments",
    fetch: () => sqlite.query("SELECT * FROM proposed_adjustments ORDER BY id").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({
        id: r.id,
        user_id: null,
        proposed_at: ts(r.proposed_at) ?? new Date(),
        op: r.op,
        target_date: d(r.target_date),
        target_session_id: r.target_session_id,
        payload_json: r.payload_json ? JSON.parse(r.payload_json) : {},
        reason: r.reason,
        status: r.status,
        decided_at: ts(r.decided_at),
      }));
      await sql`INSERT INTO proposed_adjustments ${sql(mapped)}`;
    },
    resetSeq: () => sql`SELECT setval(pg_get_serial_sequence('proposed_adjustments', 'id'),
      (SELECT COALESCE(MAX(id), 0) FROM proposed_adjustments))`,
  },
  {
    table: "sync_state",
    fetch: () => sqlite.query("SELECT * FROM sync_state").all() as any[],
    insert: async (rows) => {
      if (!rows.length) return;
      const mapped = rows.map((r) => ({ key: r.key, user_id: null, value: r.value }));
      await sql`INSERT INTO sync_state ${sql(mapped)}`;
    },
  },
];

try {
  for (const m of migrators) {
    const rows = m.fetch();
    process.stdout.write(`  ${m.table.padEnd(22)} ${String(rows.length).padStart(5)} rows ... `);
    await m.insert(rows);
    if (m.resetSeq) await m.resetSeq();
    console.log("ok");
  }
  console.log("\n✓ all data migrated");

  // Verify counts
  console.log("\nVerification (Postgres counts):");
  for (const m of migrators) {
    const [{ count }] = await sql`SELECT COUNT(*)::int AS count FROM ${sql(m.table)}`;
    console.log(`  ${m.table.padEnd(22)} ${String(count).padStart(5)}`);
  }
} catch (e) {
  console.error("\n✗ migration failed:", (e as Error).message);
  process.exit(1);
} finally {
  sqlite.close();
  await sql.end();
}
