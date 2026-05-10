import type { Config } from "drizzle-kit";

// Load .env.local explicitly — drizzle-kit doesn't pick it up automatically.
// Bun reads .env.local at the process boundary if --env-file is used.
import { config } from "dotenv";
config({ path: ".env.local" });

const url = process.env.DATABASE_URL_DIRECT ?? process.env.DATABASE_URL ?? "";
if (!url) {
  throw new Error("DATABASE_URL_DIRECT or DATABASE_URL must be set in .env.local");
}

export default {
  schema: "./src/lib/db/schema.ts",
  out: "./migrations",
  dialect: "postgresql",
  dbCredentials: { url },
  strict: true,
  verbose: true,
} satisfies Config;
