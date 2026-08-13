"""
app/main.py
-----------
FastAPI application entry point.

Security layers:
  1. SecurityHeadersMiddleware  — adds HTTP security headers to every response
  2. CORSMiddleware             — restricts cross-origin access to the frontend only
  3. JWT auth dependency        — verifies Supabase tokens on protected routes
  4. Role guard (require_admin) — enforces admin-only access

CORS configuration:
  Development: allow only http://localhost:5173 (Vite default).
  Production:  set the FRONTEND_ORIGIN environment variable to your deployed
               frontend URL, e.g. https://training.kahaniEvents.com
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.api import auth, courses, progress, quizzes, admin


# ── Security Headers Middleware ───────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds HTTP security headers to every response.

    Headers applied:
      X-Content-Type-Options    — prevents MIME-type sniffing attacks
      X-Frame-Options           — blocks clickjacking via <iframe>
      X-XSS-Protection          — enables browser XSS filter (legacy browsers)
      Referrer-Policy           — controls referrer info sent to other origins
      Permissions-Policy        — disables unused browser features
      Strict-Transport-Security — enforces HTTPS (enable in production)
      Content-Security-Policy   — restricts resource loading origins
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Block rendering in <frame>/<iframe> — prevents clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS protection (Chrome/IE)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Only send referrer to same origin
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable unused browser APIs
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # HSTS — enforces HTTPS for 1 year (safe to enable in production)
        # Uncomment below when deployed behind HTTPS:
        # response.headers["Strict-Transport-Security"] = (
        #     "max-age=31536000; includeSubDomains; preload"
        # )

        # Content Security Policy — tight allowlist
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            f"connect-src 'self' {settings.frontend_origin} https://*.supabase.co; "
            "font-src 'self' https://fonts.gstatic.com; "
            "frame-ancestors 'none';"
        )

        return response


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Kahani Events API",
    version="1.0.0",
    description="Internal training platform API for Kahani Events.",
    docs_url=None,
    redoc_url=None,
)

# ── Middleware (order matters — first added = outermost wrapper) ──────────────
# Security headers must wrap everything including CORS responses
app.add_middleware(SecurityHeadersMiddleware)

# CORS — only the configured frontend origin is allowed
# Do NOT add "*" — that defeats auth header checks
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "kahani-events-lms-frontend.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,     tags=["Auth"])
app.include_router(courses.router,  prefix="/courses",  tags=["Courses"])
app.include_router(progress.router, prefix="/progress", tags=["Progress"])
app.include_router(quizzes.router,  prefix="/quizzes",  tags=["Quizzes"])
app.include_router(admin.router,    prefix="/admin",    tags=["Admin"])


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "Kahani Events Training Platform API v1"}
