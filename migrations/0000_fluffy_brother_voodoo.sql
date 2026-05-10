CREATE TABLE IF NOT EXISTS "activities" (
	"id" bigint PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"start_dt" timestamp with time zone NOT NULL,
	"type" text,
	"name" text,
	"distance_m" double precision,
	"moving_s" integer,
	"elapsed_s" integer,
	"avg_hr" double precision,
	"max_hr" double precision,
	"avg_speed" double precision,
	"gap_speed" double precision,
	"total_ascent" double precision,
	"cadence" double precision,
	"calories" double precision,
	"perceived_exertion" double precision,
	"suffer_score" double precision,
	"has_heartrate" boolean DEFAULT false,
	"raw_json" jsonb,
	"fetched_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "coach_log" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"ts" timestamp with time zone DEFAULT now() NOT NULL,
	"date" date,
	"reason" text,
	"action" text
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "daily_checkin" (
	"date" date PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"legs_rating" integer,
	"sleep_h" double precision,
	"soreness" text,
	"rhr" integer,
	"notes" text
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "daily_load" (
	"date" date PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"trimp" double precision DEFAULT 0,
	"km" double precision DEFAULT 0,
	"moving_s" integer DEFAULT 0,
	"ctl" double precision,
	"atl" double precision,
	"tsb" double precision
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "pace_targets" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"effective_from" date NOT NULL,
	"easy_pace" double precision NOT NULL,
	"long_pace" double precision NOT NULL,
	"threshold_pace" double precision NOT NULL,
	"tenk_race_pace" double precision NOT NULL,
	"vo2_pace_400" double precision NOT NULL,
	"lap_pace" double precision NOT NULL,
	"source_note" text
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "plan_sessions" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"week_num" integer NOT NULL,
	"date" date NOT NULL,
	"day_of_week" integer NOT NULL,
	"session_type" text NOT NULL,
	"prescription" text NOT NULL,
	"target_distance_km" double precision,
	"target_duration_s" integer,
	"target_pace_min_km" double precision,
	"matched_activity_id" bigint,
	"status" text DEFAULT 'planned',
	"completion_note" text
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "plan_weeks" (
	"week_num" integer PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"start_date" date NOT NULL,
	"phase" text NOT NULL,
	"target_km" double precision,
	"target_long_km" double precision,
	"notes" text
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "proposed_adjustments" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"proposed_at" timestamp with time zone DEFAULT now() NOT NULL,
	"op" text NOT NULL,
	"target_date" date,
	"target_session_id" bigint,
	"payload_json" jsonb NOT NULL,
	"reason" text NOT NULL,
	"status" text DEFAULT 'pending',
	"decided_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "strava_tokens" (
	"user_id" uuid PRIMARY KEY NOT NULL,
	"athlete_id" integer NOT NULL,
	"access_token" text NOT NULL,
	"refresh_token" text NOT NULL,
	"expires_at" integer NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "sync_state" (
	"key" text PRIMARY KEY NOT NULL,
	"user_id" uuid,
	"value" text
);
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "plan_sessions" ADD CONSTRAINT "plan_sessions_week_num_plan_weeks_week_num_fk" FOREIGN KEY ("week_num") REFERENCES "public"."plan_weeks"("week_num") ON DELETE no action ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "plan_sessions" ADD CONSTRAINT "plan_sessions_matched_activity_id_activities_id_fk" FOREIGN KEY ("matched_activity_id") REFERENCES "public"."activities"("id") ON DELETE no action ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_activities_dt" ON "activities" USING btree ("start_dt");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_activities_type" ON "activities" USING btree ("type");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_activities_user" ON "activities" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_pace_targets_effective" ON "pace_targets" USING btree ("effective_from");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_plan_sessions_date" ON "plan_sessions" USING btree ("date");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_plan_sessions_status" ON "plan_sessions" USING btree ("status");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_plan_sessions_user" ON "plan_sessions" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_proposed_status" ON "proposed_adjustments" USING btree ("status");