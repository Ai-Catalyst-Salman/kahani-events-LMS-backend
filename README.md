# Kahani Events Training Platform — Backend

## Quick Start

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your Supabase values
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

---

## Project Structure

```
app/
  main.py               FastAPI entry point, CORS config
  api/
    auth.py             POST /login, GET /me
    courses.py          GET /courses, GET /courses/{id}
    progress.py         POST /progress/complete
    quizzes.py          GET /quizzes/{id}
    admin.py            GET /admin/overview
  core/
    config.py           Env var loading (pydantic-settings)
    supabase_client.py  Singleton Supabase service-role client
    auth.py             get_current_user + require_admin dependencies
    rate_limit.py       In-memory login rate limiter
  schemas/
    auth.py             LoginRequest, MeResponse
    courses.py          CourseOut, CourseDetailOut, VideoOut
    progress.py         ProgressCompleteRequest, ProgressCompleteResponse
    quizzes.py          QuizOut
    admin.py            AdminOverviewResponse
tests/
  security/
    conftest.py         Mocked Supabase fixtures
    test_security.py    7 security test cases
supabase/
  migrations/
    001_initial_schema.sql
    002_rls_policies.sql
```

---

## Environment Variables

See `.env.example`:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only secret key (never expose to frontend) |
| `FRONTEND_ORIGIN` | Allowed CORS origin (default: `http://localhost:5173`) |

---

## Running Security Tests

```bash
pytest tests/security
```

The test suite mocks the Supabase client — no live Supabase connection is needed.

### Test cases covered

| # | Endpoint | Scenario | Expected |
|---|---|---|---|
| 1 | `GET /admin/overview` | No auth header | `401` |
| 2 | `GET /admin/overview` | Valid non-admin token | `403` |
| 3 | `GET /quizzes/{id}` | Unauthenticated | `401` |
| 4 | `GET /quizzes/{id}` | Authenticated, no progress | `403` |
| 5 | `GET /quizzes/{id}` | Authenticated, with progress | `200` |
| 6 | `POST /progress/complete` | Missing/invalid body | `422` |
| 7 | `POST /login` | 6th failed attempt in window | `429` |

---

## API Reference

### Auth
- `POST /login` — `{ email, password }` → session tokens
- `GET /me` — returns `{ id, email, role }` (requires `Authorization: Bearer <token>`)

### Courses (public)
- `GET /courses` — list all courses
- `GET /courses/{id}` — course + videos

### Progress
- `POST /progress/complete` — `{ video_id }` — mark video done (auth required)

### Quizzes
- `GET /quizzes/{id}` — 401/403/404/200 per access rules (auth required)

### Admin
- `GET /admin/overview` — `{ total_courses, total_videos, total_completions }` (admin only)
