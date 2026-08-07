"""
app/api/admin.py
----------------
Admin-only endpoints:
  GET    /admin/overview                   → aggregate stats
  GET    /admin/courses                    → list all courses with video counts
  POST   /admin/courses                    → create a course
  DELETE /admin/courses/{id}              → delete a course (cascades to videos)
  POST   /admin/videos                    → add a video to a course
  DELETE /admin/videos/{id}              → delete a video
  GET    /admin/users                     → list all users with roles
  PATCH  /admin/users/{user_id}/role     → change a user's role
  POST   /admin/questions                 → add a quiz question for a video
  GET    /admin/videos/{video_id}/questions → list questions for a video
  DELETE /admin/questions/{id}           → delete a question
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_admin
from app.core.supabase_client import supabase
from app.schemas.admin import (
    AdminOverviewResponse,
    CourseCreateRequest,
    CourseCreateResponse,
    VideoCreateRequest,
    VideoCreateResponse,
    UserOut,
    UserRoleUpdateRequest,
    UserRoleUpdateResponse,
    QuestionCreateRequest,
    QuestionUpdateRequest,
    QuestionOut,
)

router = APIRouter()


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/overview", response_model=AdminOverviewResponse)
async def admin_overview(admin_user: dict = Depends(require_admin)):
    """Return aggregate platform stats."""
    courses_resp = supabase.table("courses").select("id", count="exact").execute()
    videos_resp  = supabase.table("videos").select("id", count="exact").execute()
    progress_resp = supabase.table("progress").select("video_id", count="exact").execute()
    users_resp   = supabase.table("user_roles").select("user_id", count="exact").execute()

    return AdminOverviewResponse(
        total_courses=courses_resp.count or 0,
        total_videos=videos_resp.count or 0,
        total_completions=progress_resp.count or 0,
        total_users=users_resp.count or 0,
    )


# ── Courses ───────────────────────────────────────────────────────────────────

@router.get("/courses")
async def list_all_courses(admin_user: dict = Depends(require_admin)):
    """List all courses with their video counts."""
    courses_resp = (
        supabase.table("courses")
        .select("id, title, description, created_at, videos(id)")
        .order("created_at", desc=True)
        .execute()
    )
    courses = courses_resp.data or []
    # Flatten video count
    result = []
    for c in courses:
        videos = c.pop("videos", []) or []
        result.append({**c, "video_count": len(videos)})
    return result


@router.post("/courses", response_model=CourseCreateResponse, status_code=201)
async def create_course(
    body: CourseCreateRequest,
    admin_user: dict = Depends(require_admin),
):
    """Create a new course."""
    resp = (
        supabase.table("courses")
        .insert({"title": body.title, "description": body.description})
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create course")
    return resp.data[0]


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(
    course_id: str,
    admin_user: dict = Depends(require_admin),
):
    """Delete a course (cascades to its videos and progress)."""
    supabase.table("courses").delete().eq("id", course_id).execute()


# ── Videos ────────────────────────────────────────────────────────────────────

@router.post("/videos", response_model=VideoCreateResponse, status_code=201)
async def create_video(
    body: VideoCreateRequest,
    admin_user: dict = Depends(require_admin),
):
    """Add a video to a course."""
    # Verify the course exists
    course = (
        supabase.table("courses").select("id").eq("id", body.course_id).single().execute()
    )
    if not course.data:
        raise HTTPException(status_code=404, detail="Course not found")

    resp = (
        supabase.table("videos")
        .insert({
            "course_id": body.course_id,
            "title": body.title,
            "video_url": body.video_url,
        })
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create video")
    return resp.data[0]


@router.delete("/videos/{video_id}", status_code=204)
async def delete_video(
    video_id: str,
    admin_user: dict = Depends(require_admin),
):
    """Delete a video (cascades to progress rows)."""
    supabase.table("videos").delete().eq("id", video_id).execute()


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserOut])
async def list_users(admin_user: dict = Depends(require_admin)):
    """Return all users with their roles."""
    resp = (
        supabase.table("user_roles")
        .select("user_id, role, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    rows = resp.data or []

    # Fetch emails from auth.users via service role
    users_resp = supabase.auth.admin.list_users()
    email_map = {}
    if users_resp:
        for u in users_resp:
            email_map[u.id] = u.email

    result = []
    for row in rows:
        result.append(
            UserOut(
                id=row["user_id"],
                email=email_map.get(row["user_id"], "unknown@email.com"),
                role=row["role"],
                created_at=row.get("created_at"),
            )
        )
    return result


@router.patch("/users/{user_id}/role", response_model=UserRoleUpdateResponse)
async def update_user_role(
    user_id: str,
    body: UserRoleUpdateRequest,
    admin_user: dict = Depends(require_admin),
):
    """Change a user's role between 'admin' and 'learner'."""
    if body.role not in ("admin", "learner"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'learner'")

    # Prevent admin from demoting themselves
    if user_id == admin_user["id"] and body.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    resp = (
        supabase.table("user_roles")
        .update({"role": body.role})
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    return UserRoleUpdateResponse(user_id=user_id, role=body.role)


# ── Questions ─────────────────────────────────────────────────────────────────

@router.post("/questions", response_model=QuestionOut, status_code=201)
async def create_question(
    body: QuestionCreateRequest,
    admin_user: dict = Depends(require_admin),
):
    """Add a quiz question to a video."""
    if body.correct_option_index >= len(body.options):
        raise HTTPException(status_code=422, detail="Correct option index out of bounds")

    resp = (
        supabase.table("video_questions")
        .insert({
            "video_id": body.video_id,
            "question": body.question,
            "options": body.options,
            "correct_option_index": body.correct_option_index,
        })
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create question")
    return resp.data[0]


@router.get("/videos/{video_id}/questions", response_model=list[QuestionOut])
async def list_video_questions(
    video_id: str,
    admin_user: dict = Depends(require_admin),
):
    """Get all questions for a specific video."""
    resp = (
        supabase.table("video_questions")
        .select("*")
        .eq("video_id", video_id)
        .order("created_at")
        .execute()
    )
    return resp.data or []


@router.put("/questions/{question_id}", response_model=QuestionOut)
async def update_question(
    question_id: str,
    body: QuestionUpdateRequest,
    admin_user: dict = Depends(require_admin),
):
    """Update an existing quiz question."""
    if body.correct_option_index >= len(body.options):
        raise HTTPException(status_code=422, detail="Correct option index out of bounds")

    resp = (
        supabase.table("video_questions")
        .update({
            "question": body.question,
            "options": body.options,
            "correct_option_index": body.correct_option_index,
        })
        .eq("id", question_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Question not found")
    return resp.data[0]


@router.delete("/questions/{question_id}", status_code=204)
async def delete_question(
    question_id: str,
    admin_user: dict = Depends(require_admin),
):
    """Delete a question."""
    supabase.table("video_questions").delete().eq("id", question_id).execute()
