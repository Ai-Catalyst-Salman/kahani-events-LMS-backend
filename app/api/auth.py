"""
app/api/auth.py
---------------
Auth endpoints:
  POST /login  — email+password login, rate-limited per IP
  GET  /me     — returns {id, email, role} for the authenticated user
"""

from fastapi import APIRouter, HTTPException, Request, status, Depends

from app.core.auth import get_current_user
from app.core.rate_limit import check_rate_limit, record_failed_attempt, reset_rate_limit
from app.core.supabase_client import supabase
from app.schemas.auth import LoginRequest, MeResponse

router = APIRouter()


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """
    Authenticate with email and password.
    Rate-limited: 5 failed attempts per IP per 60 seconds → 429.
    On success, returns the Supabase session (access_token, refresh_token, user).
    The frontend stores the session in the Supabase client SDK's localStorage.
    """
    client_ip = request.client.host

    allowed, retry_after = check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        response = supabase.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception as exc:
        # Supabase raises on invalid credentials
        record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc

    if response is None or response.session is None:
        record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Successful login — reset the failure counter for this IP.
    reset_rate_limit(client_ip)

    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "user": {
            "id": response.user.id,
            "email": response.user.email,
        },
    }


@router.get("/me", response_model=MeResponse)
async def me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's id, email, and role."""
    return MeResponse(
        id=current_user["id"],
        email=current_user["email"],
        role=current_user["role"],
    )
