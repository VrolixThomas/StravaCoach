/**
 * Database client setup. Two flavors:
 *  - `db` (Drizzle + postgres-js) for direct SQL/queries from server code
 *  - `supabase` for Supabase-specific features (auth, realtime, storage)
 *
 * Use `db` for the engine (writes, complex queries).
 * Use `supabase` from server components for auth context.
 */
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import { createClient } from "@supabase/supabase-js";
import * as schema from "./schema";

const DATABASE_URL = process.env.DATABASE_URL;
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!DATABASE_URL) {
  throw new Error(
    "DATABASE_URL is not set. Add it to .env.local (use Supabase pooler URL on port 6543 for serverless)."
  );
}

// Postgres client. Pooler (port 6543) for serverless functions.
// In long-lived processes (CLI, dev server), reuse the connection.
const queryClient = postgres(DATABASE_URL, {
  prepare: false, // required for pgbouncer
  max: 10,
});

export const db = drizzle(queryClient, { schema });

export const supabase =
  SUPABASE_URL && SUPABASE_ANON_KEY
    ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
    : null;
