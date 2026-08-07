-- ============================================================
-- 001_initial_schema.sql
-- Kahani Events Training Platform — V1 Initial Schema
--
-- Run this in your Supabase SQL Editor before starting the app.
-- All primary keys use uuid; all timestamps use timestamptz.
-- ============================================================

-- user_roles: single source of truth for role.
-- Do NOT also store role in auth user_metadata — one source only.
-- Defaults to 'learner' on insert so new sign-ups are safe by default.
create table if not exists user_roles (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  role       text not null check (role in ('admin', 'learner')) default 'learner',
  created_at timestamptz default now()
);

create table if not exists courses (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  description text,
  created_at  timestamptz default now()
);

create table if not exists videos (
  id          uuid primary key default gen_random_uuid(),
  course_id   uuid not null references courses(id) on delete cascade,
  title       text not null,
  video_url   text not null,
  created_at  timestamptz default now()
);

create table if not exists quizzes (
  id          uuid primary key default gen_random_uuid(),
  course_id   uuid not null references courses(id) on delete cascade,
  title       text not null,
  created_at  timestamptz default now()
);

create table if not exists progress (
  user_id      uuid not null references auth.users(id) on delete cascade,
  video_id     uuid not null references videos(id) on delete cascade,
  completed    boolean default true,
  completed_at timestamptz default now(),
  primary key (user_id, video_id)
);

-- ── Auto-create user_roles row on new sign-up ────────────────────────────────
-- This trigger ensures every new Supabase auth user gets a 'learner' role row
-- automatically, so the app never has to handle the "no role row" case.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.user_roles (user_id, role)
  values (new.id, 'learner')
  on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
