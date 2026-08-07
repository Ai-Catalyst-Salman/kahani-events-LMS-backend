"""
tests/security/test_security.py
--------------------------------
Security test suite covering all 7 cases from the spec (§6).

Run with:
    pytest tests/security

Cases:
  1. GET /admin/overview — no auth header → 401
  2. GET /admin/overview — valid non-admin token → 403
  3. GET /quizzes/{id}  — unauthenticated → 401
  4. GET /quizzes/{id}  — authenticated, no progress → 403
  5. GET /quizzes/{id}  — authenticated, with progress → 200
  6. POST /progress/complete — missing/invalid body → 422
  7. Login rate limit — 6th failed attempt → 429
"""

import pytest
from tests.security.conftest import (
    ADMIN_TOKEN,
    LEARNER_TOKEN,
    INVALID_TOKEN,
    QUIZ_ID,
)

# ── Reset rate-limit state between tests ──────────────────────────────────────
import app.core.rate_limit as rl


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Clear in-memory rate-limit state before every test."""
    rl._login_attempts.clear()
    yield
    rl._login_attempts.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Case 1: GET /admin/overview — no auth header → 401
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_admin_overview_no_auth(client_no_progress):
    response = await client_no_progress.get("/admin/overview")
    assert response.status_code == 401, (
        f"Expected 401 with no auth, got {response.status_code}: {response.text}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Case 2: GET /admin/overview — valid non-admin (learner) token → 403
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_admin_overview_wrong_role(client_no_progress):
    response = await client_no_progress.get(
        "/admin/overview",
        headers={"Authorization": f"Bearer {LEARNER_TOKEN}"},
    )
    assert response.status_code == 403, (
        f"Expected 403 for learner on admin route, got {response.status_code}: {response.text}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Case 3: GET /quizzes/{id} — unauthenticated → 401
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_quiz_unauthenticated(client_no_progress):
    response = await client_no_progress.get(f"/quizzes/{QUIZ_ID}")
    assert response.status_code == 401, (
        f"Expected 401 with no auth on quiz, got {response.status_code}: {response.text}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Case 4: GET /quizzes/{id} — authenticated, no completed progress → 403
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_quiz_locked_no_progress(client_no_progress):
    response = await client_no_progress.get(
        f"/quizzes/{QUIZ_ID}",
        headers={"Authorization": f"Bearer {LEARNER_TOKEN}"},
    )
    assert response.status_code == 403, (
        f"Expected 403 for quiz with no progress, got {response.status_code}: {response.text}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Case 5: GET /quizzes/{id} — authenticated, with completed progress → 200
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_quiz_unlocked_with_progress(client_with_progress):
    response = await client_with_progress.get(
        f"/quizzes/{QUIZ_ID}",
        headers={"Authorization": f"Bearer {LEARNER_TOKEN}"},
    )
    assert response.status_code == 200, (
        f"Expected 200 for quiz with progress, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["id"] == QUIZ_ID
    assert "title" in data
    assert "course_id" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Case 6: POST /progress/complete — missing/invalid body → 422
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_progress_missing_body(client_with_progress):
    """Body entirely missing → 422."""
    response = await client_with_progress.post(
        "/progress/complete",
        headers={"Authorization": f"Bearer {LEARNER_TOKEN}"},
    )
    assert response.status_code == 422, (
        f"Expected 422 for missing body, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_progress_invalid_body_field(client_with_progress):
    """Body has wrong field name → 422."""
    response = await client_with_progress.post(
        "/progress/complete",
        json={"wrong_field": "some-value"},
        headers={"Authorization": f"Bearer {LEARNER_TOKEN}"},
    )
    assert response.status_code == 422, (
        f"Expected 422 for invalid body fields, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_progress_empty_body(client_with_progress):
    """Empty JSON object → 422 (video_id required)."""
    response = await client_with_progress.post(
        "/progress/complete",
        json={},
        headers={"Authorization": f"Bearer {LEARNER_TOKEN}"},
    )
    assert response.status_code == 422, (
        f"Expected 422 for empty body, got {response.status_code}: {response.text}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Case 7: Login rate limit — 6th failed attempt within the window → 429
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_login_rate_limit(client_no_progress):
    """
    5 failed attempts should all return 401 (wrong credentials).
    The 6th attempt must return 429 with a Retry-After header.
    """
    bad_payload = {"email": "nobody@example.com", "password": "wrong"}

    for attempt in range(1, 6):
        r = await client_no_progress.post("/login", json=bad_payload)
        assert r.status_code == 401, (
            f"Attempt {attempt}: expected 401, got {r.status_code}"
        )

    # 6th attempt — should be rate-limited
    r = await client_no_progress.post("/login", json=bad_payload)
    assert r.status_code == 429, (
        f"6th attempt: expected 429, got {r.status_code}: {r.text}"
    )
    assert "Retry-After" in r.headers, "429 response must include Retry-After header"
