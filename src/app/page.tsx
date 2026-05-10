/**
 * Stack-verification page. Once Supabase is configured, replace with the real
 * dashboard (today's session + readiness + recent activity).
 */
export const dynamic = "force-dynamic";

declare global {
  // eslint-disable-next-line no-var
  var Bun: { version: string } | undefined;
}

export default async function HomePage() {
  const dbConfigured = Boolean(process.env.DATABASE_URL);
  const supabaseConfigured = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  );

  let activityCount: number | string = "—";
  let dbError: string | null = null;

  if (dbConfigured) {
    try {
      const { db } = await import("@/lib/db/client");
      const { activities } = await import("@/lib/db/schema");
      const { sql } = await import("drizzle-orm");
      const rows = await db.select({ n: sql<number>`count(*)` }).from(activities);
      activityCount = Number(rows[0]?.n ?? 0);
    } catch (e) {
      dbError = (e as Error).message;
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Strava Coach</h1>
      <p className="text-[color:var(--color-muted)] mt-1">
        Bun + Next.js + Supabase + Tailwind v4. Migration in progress.
      </p>

      <section className="mt-10 grid gap-4">
        <Card
          label="Runtime"
          status="ok"
          detail={typeof globalThis.Bun !== "undefined" ? `Bun ${globalThis.Bun.version}` : `Node ${process.version}`}
        />
        <Card
          label="DATABASE_URL"
          status={dbConfigured ? "ok" : "missing"}
          detail={dbConfigured ? "configured" : "set in .env.local"}
        />
        <Card
          label="Supabase keys"
          status={supabaseConfigured ? "ok" : "missing"}
          detail={
            supabaseConfigured
              ? "configured"
              : "NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY"
          }
        />
        <Card
          label="Activity count"
          status={dbError ? "error" : dbConfigured ? "ok" : "pending"}
          detail={dbError ?? String(activityCount)}
        />
      </section>

      <p className="text-[color:var(--color-muted)] mt-10 text-sm">
        See <code>MIGRATION_PLAN.md</code> for current phase + next steps.
      </p>
    </main>
  );
}

function Card({
  label,
  status,
  detail,
}: {
  label: string;
  status: "ok" | "missing" | "error" | "pending";
  detail: string;
}) {
  const color = {
    ok: "var(--color-good)",
    missing: "var(--color-warn)",
    error: "var(--color-bad)",
    pending: "var(--color-muted)",
  }[status];
  return (
    <div className="rounded-xl border border-[color:var(--color-line)] bg-[color:var(--color-panel)] px-5 py-4">
      <div className="flex items-center justify-between">
        <span className="text-sm uppercase tracking-wider text-[color:var(--color-muted)]">
          {label}
        </span>
        <span
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color }}
        >
          {status}
        </span>
      </div>
      <div className="mt-1 font-mono text-sm">{detail}</div>
    </div>
  );
}
