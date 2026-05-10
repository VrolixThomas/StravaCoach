/**
 * Drop all coach tables in the public schema. Use only during early migration
 * dev when there's no real Postgres data yet.
 */
import { config } from "dotenv";
import postgres from "postgres";

config({ path: ".env.local" });

const url = process.env.DATABASE_URL_DIRECT ?? process.env.DATABASE_URL;
if (!url) throw new Error("DATABASE_URL_DIRECT not set");

const sql = postgres(url, { prepare: false, max: 1 });

const tables = [
  "proposed_adjustments",
  "coach_log",
  "daily_checkin",
  "daily_load",
  "plan_sessions",
  "plan_weeks",
  "activities",
  "strava_tokens",
  "pace_targets",
  "sync_state",
];

try {
  for (const t of tables) {
    process.stdout.write(`drop ${t} ... `);
    await sql.unsafe(`DROP TABLE IF EXISTS ${t} CASCADE`);
    console.log("ok");
  }
  console.log("✓ all tables dropped");
} finally {
  await sql.end();
}
