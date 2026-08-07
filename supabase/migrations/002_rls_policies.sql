-- ============================================================
-- 002_rls_policies.sql
-- Kahani Events Training Platform — V1 RLS Policies
--
-- Run AFTER 001_initial_schema.sql.
--
-- V1 security model:
--   - RLS is ENABLED on all tables (required).
--   - Policies are permissive-by-default for authenticated users because
--     all writes/reads go through the backend service role key, which
--     bypasses RLS. Application-layer auth (JWT verification + role check)
--     is the primary access control in V1.
--   - RLS acts as a defence-in-depth safety net.
--   - V2 will tighten these to per-row ownership policies.
-- ============================================================

-- ── Enable RLS ────────────────────────────────────────────────────────────────
alter table user_roles  enable row level security;
alter table courses     enable row level security;
alter table videos      enable row level security;
alter table quizzes     enable row level security;
alter table progress    enable row level security;

-- ── user_roles ────────────────────────────────────────────────────────────────
-- Users can only read their own role row.
create policy "user_roles: users read own row"
  on user_roles for select
  using (auth.uid() = user_id);

-- ── courses (public read) ─────────────────────────────────────────────────────
create policy "courses: authenticated read"
  on courses for select
  using (auth.role() = 'authenticated');

-- ── videos (public read) ──────────────────────────────────────────────────────
create policy "videos: authenticated read"
  on videos for select
  using (auth.role() = 'authenticated');

-- ── quizzes (public read) ─────────────────────────────────────────────────────
create policy "quizzes: authenticated read"
  on quizzes for select
  using (auth.role() = 'authenticated');

-- ── progress ──────────────────────────────────────────────────────────────────
-- Users can read and write their own progress rows.
create policy "progress: users read own"
  on progress for select
  using (auth.uid() = user_id);

create policy "progress: users insert own"
  on progress for insert
  with check (auth.uid() = user_id);

create policy "progress: users update own"
  on progress for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
