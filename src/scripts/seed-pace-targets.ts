/**
 * Seed initial pace targets row (effective today).
 * Values lifted from the original coach/plan.py constants, anchored to 2021 fitness.
 */
import { config } from "dotenv";
import postgres from "postgres";

config({ path: ".env.local" });

const url = process.env.DATABASE_URL_DIRECT ?? process.env.DATABASE_URL;
if (!url) throw new Error("DATABASE_URL_DIRECT not set");

const sql = postgres(url, { prepare: false, max: 1 });

const today = new Date().toISOString().slice(0, 10);

try {
  await sql`
    INSERT INTO pace_targets
      (user_id, effective_from, easy_pace, long_pace, threshold_pace,
       tenk_race_pace, vo2_pace_400, lap_pace, source_note)
    VALUES
      (NULL, ${today}, 5.20, 5.30, 4.20, 4.00, 3.55, 2.55,
       'initial seed: anchored to 2021 best (10K @ 3:53/km, 5K PR 17:30)')
  `;
  console.log("✓ pace_targets seeded");
  const rows = await sql`SELECT * FROM pace_targets ORDER BY effective_from DESC LIMIT 5`;
  console.log(rows);
} finally {
  await sql.end();
}
