-- ============================================================
-- 003_jwt_role_claims.sql
-- Kahani Events Training Platform — JWT Custom Claims
--
-- Run this in Supabase SQL Editor AFTER 001 and 002.
--
-- PURPOSE:
--   This function automatically adds the user's role to their
--   Supabase JWT token via the "app_metadata" field.
--   The backend reads the role from the JWT claims first (fast path),
--   and only falls back to a DB query if the claim is missing.
--
-- HOW IT WORKS:
--   Supabase calls auth.uid() to issue tokens. By setting
--   raw_app_meta_data on the auth.users record, Supabase embeds
--   that data inside the JWT payload automatically.
--
-- RESULT:
--   Every token contains: { ..., "app_metadata": { "role": "admin" } }
--   The backend reads this instead of querying user_roles on every request.
-- ============================================================

-- ── Function: sync role into JWT app_metadata ─────────────────────────────────
CREATE OR REPLACE FUNCTION public.sync_role_to_jwt()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  -- Write the role from user_roles into auth.users.raw_app_meta_data
  -- Supabase automatically includes raw_app_meta_data in the JWT.
  UPDATE auth.users
  SET raw_app_meta_data = 
    COALESCE(raw_app_meta_data, '{}'::jsonb) || 
    jsonb_build_object('role', NEW.role)
  WHERE id = NEW.user_id;
  
  RETURN NEW;
END;
$$;

-- ── Trigger: fire whenever role is inserted or updated ────────────────────────
DROP TRIGGER IF EXISTS on_user_role_change ON public.user_roles;
CREATE TRIGGER on_user_role_change
  AFTER INSERT OR UPDATE OF role ON public.user_roles
  FOR EACH ROW EXECUTE FUNCTION public.sync_role_to_jwt();

-- ── Backfill: sync roles for all existing users ───────────────────────────────
-- This updates the JWT metadata for users who already have a role row.
UPDATE auth.users u
SET raw_app_meta_data = 
  COALESCE(u.raw_app_meta_data, '{}'::jsonb) ||
  jsonb_build_object('role', r.role)
FROM public.user_roles r
WHERE r.user_id = u.id;

-- ── Verify the backfill worked ────────────────────────────────────────────────
-- Run this SELECT to confirm: you should see role inside raw_app_meta_data
SELECT 
  u.email,
  r.role AS role_table,
  u.raw_app_meta_data->>'role' AS role_in_jwt
FROM auth.users u
JOIN public.user_roles r ON r.user_id = u.id;
