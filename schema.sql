-- OA Reminder System — Supabase Postgres schema
-- Run this once in the Supabase SQL editor (Project → SQL Editor → New query).

-- pgcrypto gives us gen_random_uuid(); Supabase projects have it available by default,
-- but this makes the schema self-contained/idempotent to re-run on a fresh project.
create extension if not exists pgcrypto;

create table if not exists assessments (
    id                   uuid primary key default gen_random_uuid(),

    company              text not null,
    title                text not null,               -- assessment name, e.g. "Embedded Systems OA"
    assessment_time      timestamptz not null,         -- always stored in UTC; app converts to/from Asia/Kolkata
    link                 text,
    notes                text,

    -- per-OA toggles for which reminders are wanted; default all on
    remind_24h           boolean not null default true,
    remind_6h            boolean not null default true,
    remind_2h            boolean not null default true,

    -- null = not sent yet; a timestamp = when it was sent (doubles as an audit trail)
    reminder_24_sent_at  timestamptz,
    reminder_6_sent_at   timestamptz,
    reminder_2_sent_at   timestamptz,

    completed            boolean not null default false,
    completed_at         timestamptz,

    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);

-- The scheduler's hot query filters/sorts on assessment_time for non-completed rows;
-- this partial index keeps that cheap even as completed/past history grows.
create index if not exists idx_assessments_pending
    on assessments (assessment_time)
    where completed = false;

-- General time index for the dashboard's upcoming/past listing queries.
create index if not exists idx_assessments_time
    on assessments (assessment_time);

-- Keep updated_at fresh on every row change — used by the "assessment time changed"
-- reset logic and generally useful as an audit signal.
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_assessments_updated_at on assessments;
create trigger trg_assessments_updated_at
    before update on assessments
    for each row
    execute function set_updated_at();

comment on table assessments is 'Online assessments (OAs) tracked for reminder notifications.';
comment on column assessments.assessment_time is 'Stored in UTC (timestamptz). App is responsible for converting to/from Asia/Kolkata for display and input.';
comment on column assessments.reminder_24_sent_at is 'Null until the 24h-before reminder has been sent (or marked moot); never reset except by the time-change logic.';
comment on column assessments.reminder_6_sent_at is 'Null until the 6h-before reminder has been sent (or marked moot).';
comment on column assessments.reminder_2_sent_at is 'Null until the 2h-before reminder has been sent (or marked moot).';

-- Row Level Security: enabled for defense-in-depth, but this app has no per-user
-- policies for v1 — the backend is the only writer and connects using the
-- Supabase service_role key, which bypasses RLS by design. No policies are
-- created here on purpose; see the plan's "Auth" notes for the reasoning.
alter table assessments enable row level security;
