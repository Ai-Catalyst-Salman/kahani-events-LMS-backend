"""
app/core/auth.py
----------------
FastAPI dependency: get_current_user

Usage:
    from app.core.auth import get_current_user, require_admin
    
    @router.get("/protected")
    async def protected(user=Depends(get_current_user)):
        ...

    @router.get("/admin-only")
    async def admin_only(user=Depends(require_admin)):
        ...

Security model — Two-path role resolution:
─────────────────────────────────────────
  FAST PATH  (no extra DB hit):
    After running migration 003_jwt_role_claims.sql, Supabase embeds the
    user's role into the JWT via raw_app_meta_data. We read it directly
    from user.app_metadata so every authenticated request costs exactly
    one Supabase token-verify call — no extra DB round-trip.

  FALLBACK PATH (DB query):
    If the JWT was issued before the migration or the claim is absent,
    we query user_roles as before. This keeps backward compatibility and
    ensures correctness even if metadata sync lags.

The dependency:
  1. Extracts the Bearer token from the Authorization header.
  2. Verifies it with Supabase (authoritative — validates signature + expiry).
  3. Reads role from JWT app_metadata (fast path) or user_roles table (fallback).
  4. Returns a dict { id, email, role } attached to the request context.

Raises:
    401 — missing/invalid/expired token
    403 — authenticated but wrong role (via require_admin)
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.supabase_client import supabase

bearer_scheme = HTTPBearer(auto_error=False)

# Allowed roles — keep in sync with the DB CHECK constraint.
VALID_ROLES = {"admin", "learner"}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Verify JWT and return {id, email, role}. Raises 401 on failure.

    Role resolution (in order):
      1. JWT app_metadata.role  → fast path, no DB hit
      2. JWT user_metadata.role → legacy fallback
      3. user_roles DB table    → authoritative fallback
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # ── Step 1: Verify token with Supabase ────────────────────────────────────
    # We do NOT decode the JWT manually — Supabase validates signature + expiry.
    try:
        response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if response is None or response.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = response.user

    # ── Step 2: Read role from JWT claims (fast path) ─────────────────────────
    # Migration 003_jwt_role_claims.sql syncs role → raw_app_meta_data so
    # every token already carries the role without a DB round-trip.
    role: str | None = None

    app_meta = getattr(user, "app_metadata", None) or {}
    user_meta = getattr(user, "user_metadata", None) or {}

    jwt_role = app_meta.get("role") or user_meta.get("role")
    if jwt_role and jwt_role in VALID_ROLES:
        role = jwt_role  # Fast path: role was embedded in the JWT ✅

    # ── Step 3: Fallback — query user_roles table ─────────────────────────────
    # Needed if: JWT pre-dates the migration, or metadata sync hasn't fired yet.
    if role is None:
        try:
            role_response = (
                supabase.table("user_roles")
                .select("role")
                .eq("user_id", user.id)
                .single()
                .execute()
            )
            if role_response.data:
                db_role = role_response.data.get("role", "learner")
                role = db_role if db_role in VALID_ROLES else "learner"
            else:
                role = "learner"  # No row → safe default
        except Exception:
            role = "learner"  # DB error → deny elevated access safely

    return {"id": user.id, "email": user.email, "role": role}


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Guard: raises 403 if the authenticated user is not an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
