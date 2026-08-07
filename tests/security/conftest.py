"""
tests/security/conftest.py
--------------------------
Shared fixtures for the security test suite.

The Supabase auth client is mocked at the dependency level so that tests
run without a live Supabase project. This lets us test the FastAPI
application's access-control logic in isolation.

Two tokens are pre-defined:
  ADMIN_TOKEN   — resolves to a user with role='admin'
  LEARNER_TOKEN — resolves to a user with role='learner'
  INVALID_TOKEN — will be rejected as invalid

The mocked supabase client is also used to drive the database queries
(user_roles lookups, progress checks) so every scenario can be set up
with pure in-process fixtures.
"""

import os

# ── Set dummy env vars BEFORE importing the app so pydantic-settings ──────────
# ── can instantiate Settings(). The real Supabase client is mocked out ────────
# ── in every test fixture so these dummy values are never used in calls. ──────
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app


# ── Sentinel tokens used in tests ────────────────────────────────────────────
ADMIN_TOKEN = "test-admin-token"
LEARNER_TOKEN = "test-learner-token"
INVALID_TOKEN = "definitely-invalid"

ADMIN_USER_ID = "admin-user-uuid-1234"
LEARNER_USER_ID = "learner-user-uuid-5678"

COURSE_ID = "course-uuid-abcd"
VIDEO_ID = "video-uuid-efgh"
QUIZ_ID = "quiz-uuid-ijkl"


def _make_user_mock(user_id: str, email: str):
    """Build a minimal Supabase user-like object."""
    user = MagicMock()
    user.id = user_id
    user.email = email
    return user


def _make_auth_response(user_mock):
    """Wrap a user mock in a response-like object."""
    resp = MagicMock()
    resp.user = user_mock
    return resp


def _make_supabase_mock(token_to_user: dict, role_map: dict, progress_data: list):
    """
    Build a MagicMock for the supabase client used throughout the app.

    token_to_user: {token: user_mock}
    role_map:      {user_id: role_str}
    progress_data: list of progress rows to return for progress queries
    """
    mock = MagicMock()

    # auth.get_user — returns user based on token
    def get_user(token):
        user = token_to_user.get(token)
        if user is None:
            raise Exception("Invalid token")
        return _make_auth_response(user)

    mock.auth.get_user.side_effect = get_user

    # auth.sign_in_with_password — used in login tests
    def sign_in(credentials):
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        if email == "admin@test.com" and password == "correct":
            session = MagicMock()
            session.access_token = ADMIN_TOKEN
            session.refresh_token = "refresh-token"
            resp = MagicMock()
            resp.session = session
            resp.user = _make_user_mock(ADMIN_USER_ID, email)
            return resp
        raise Exception("Invalid login credentials")

    mock.auth.sign_in_with_password.side_effect = sign_in

    # table() chain builder
    def _make_chain(data=None, count=None):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.single.return_value = chain
        chain.upsert.return_value = chain
        result = MagicMock()
        result.data = data
        result.count = count if count is not None else (len(data) if data else 0)
        chain.execute.return_value = result
        return chain

    def table(name):
        if name == "user_roles":
            chain = MagicMock()
            chain.select.return_value = chain
            # Store current user_id for the eq() call
            _state = {"user_id": None}

            def eq(col, val):
                if col == "user_id":
                    _state["user_id"] = val
                return chain

            chain.eq.side_effect = eq
            chain.single.return_value = chain

            def execute():
                uid = _state["user_id"]
                role = role_map.get(uid, "learner")
                result = MagicMock()
                result.data = {"role": role}
                return result

            chain.execute.side_effect = execute
            return chain

        if name == "quizzes":
            chain = MagicMock()
            chain.select.return_value = chain
            _state = {"quiz_id": None}

            def eq(col, val):
                if col == "id":
                    _state["quiz_id"] = val
                return chain

            chain.eq.side_effect = eq
            chain.single.return_value = chain

            def execute():
                qid = _state["quiz_id"]
                if qid == QUIZ_ID:
                    result = MagicMock()
                    result.data = {
                        "id": QUIZ_ID,
                        "title": "Test Quiz",
                        "course_id": COURSE_ID,
                        "created_at": "2024-01-01T00:00:00+00:00",
                    }
                    return result
                result = MagicMock()
                result.data = None
                return result

            chain.execute.side_effect = execute
            return chain

        if name == "progress":
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain

            def execute():
                result = MagicMock()
                result.data = progress_data
                result.count = len(progress_data)
                return result

            chain.execute.side_effect = execute
            return chain

        # Default fallback — empty chain
        return _make_chain(data=[], count=0)

    mock.table.side_effect = table
    return mock


# ── Shared user mocks ─────────────────────────────────────────────────────────
ADMIN_USER = _make_user_mock(ADMIN_USER_ID, "admin@test.com")
LEARNER_USER = _make_user_mock(LEARNER_USER_ID, "learner@test.com")

TOKEN_MAP = {
    ADMIN_TOKEN: ADMIN_USER,
    LEARNER_TOKEN: LEARNER_USER,
}
ROLE_MAP = {
    ADMIN_USER_ID: "admin",
    LEARNER_USER_ID: "learner",
}


@pytest_asyncio.fixture
async def client_no_progress():
    """HTTP client where the learner has NO completed videos."""
    mock_supabase = _make_supabase_mock(TOKEN_MAP, ROLE_MAP, progress_data=[])
    with patch("app.core.auth.supabase", mock_supabase), \
         patch("app.api.admin.supabase", mock_supabase), \
         patch("app.api.quizzes.supabase", mock_supabase), \
         patch("app.api.progress.supabase", mock_supabase), \
         patch("app.api.courses.supabase", mock_supabase), \
         patch("app.api.auth.supabase", mock_supabase):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


@pytest_asyncio.fixture
async def client_with_progress():
    """HTTP client where the learner HAS ≥1 completed video."""
    progress_row = {"video_id": VIDEO_ID, "videos": {"course_id": COURSE_ID}}
    mock_supabase = _make_supabase_mock(TOKEN_MAP, ROLE_MAP, progress_data=[progress_row])
    with patch("app.core.auth.supabase", mock_supabase), \
         patch("app.api.admin.supabase", mock_supabase), \
         patch("app.api.quizzes.supabase", mock_supabase), \
         patch("app.api.progress.supabase", mock_supabase), \
         patch("app.api.courses.supabase", mock_supabase), \
         patch("app.api.auth.supabase", mock_supabase):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
