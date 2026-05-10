/**
 * Apply a SQL migration file directly via postgres.js.
 * Used when drizzle-kit push prompts interactively (avoids the prompt).
 *
 * Usage: bun run src/scripts/apply-migration.ts migrations/0000_xxx.sql
 */
import { config } from "dotenv";
import postgres from "postgres";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

config({ path: ".env.local" });

const file = process.argv[2];
if (!file) {
  console.error("Usage: bun run src/scripts/apply-migration.ts <path-to-sql>");
  process.exit(1);
}

const url = process.env.DATABASE_URL_DIRECT ?? process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL_DIRECT or DATABASE_URL not set");
  process.exit(1);
}

const sql = postgres(url, { prepare: false, max: 1 });
const content = readFileSync(resolve(file), "utf8");

// Split on `--> statement-breakpoint` (Drizzle convention) and run each chunk
const statements = content
  .split(/-->\s*statement-breakpoint/g)
  .map((s) => s.trim())
  .filter((s) => s.length > 0);

console.log(`Applying ${statements.length} statements from ${file}`);

let i = 0;
try {
  for (const stmt of statements) {
    i++;
    process.stdout.write(`  [${i}/${statements.length}] `);
    await sql.unsafe(stmt);
    console.log("ok");
  }
  console.log("✓ migration applied");
} catch (e) {
  console.error(`\n✗ statement ${i} failed:`);
  console.error(statements[i - 1]);
  console.error("\nError:", (e as Error).message);
  process.exit(1);
} finally {
  await sql.end();
}
