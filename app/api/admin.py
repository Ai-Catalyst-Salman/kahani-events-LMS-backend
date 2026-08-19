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
    UserCreateRequest,
    UserUpdateRequest,
    UserRoleUpdateRequest,
    UserRoleUpdateResponse,
    QuestionCreateRequest,
    QuestionUpdateRequest,
    QuestionOut,
    WatchHistoryResponse,
    WatchedVideo,
    TopPerformer,
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


@router.get("/dashboard/top-performers", response_model=list[TopPerformer])
async def get_top_performers(admin_user: dict = Depends(require_admin)):
    """Return top performers based on completed modules/videos with their completion percentage."""
    # Fetch total platform videos to calculate percentage
    videos_resp = supabase.table("videos").select("id", count="exact").execute()
    total_videos = videos_resp.count or 0

    progress_resp = supabase.table("progress").select("user_id").eq("completed", True).execute()
    progress_data = progress_resp.data or []

    counts = {}
    for row in progress_data:
        uid = row["user_id"]
        counts[uid] = counts.get(uid, 0) + 1

    sorted_users = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
    result = []
    
    if sorted_users:
        users_resp = supabase.auth.admin.list_users()
        email_map = {u.id: u.email for u in users_resp} if users_resp else {}
        
        for uid, count in sorted_users:
            email = email_map.get(uid, "Unknown User")
            name = email.split("@")[0]
            
            percentage = 0
            if total_videos > 0:
                percentage = round((count / total_videos) * 100)
                
            result.append(TopPerformer(
                user_id=uid, 
                name=name, 
                completed_modules=count,
                completion_percentage=percentage
            ))
            
    return result


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
        .insert({
            "title": body.title, 
            "description": body.description,
            "department": body.department
        })
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
            "transcript": body.transcript,
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


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateRequest,
    admin_user: dict = Depends(require_admin),
):
    """Create a new user using Supabase Admin API."""
    try:
        # 1. Create auth user
        new_user = supabase.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True
        })
        user_id = new_user.user.id
        
        # 2. Update their role (handle_new_user trigger creates them as 'learner')
        if body.role == "admin":
            supabase.table("user_roles").update({"role": body.role}).eq("user_id", user_id).execute()
        
        return UserOut(
            id=user_id,
            email=body.email,
            role=body.role,
            created_at=new_user.user.created_at
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/users/{user_id}/credentials", response_model=dict)
async def update_user_credentials(
    user_id: str,
    body: UserUpdateRequest,
    admin_user: dict = Depends(require_admin),
):
    """Update a user's email or password."""
    updates = {}
    if body.email:
        updates["email"] = body.email
    if body.password:
        updates["password"] = body.password
        
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    try:
        supabase.auth.admin.update_user_by_id(user_id, updates)
        return {"message": "User updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    admin_user: dict = Depends(require_admin),
):
    """Delete a user from the system."""
    if user_id == admin_user["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
        
    try:
        supabase.auth.admin.delete_user(user_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{user_id}/watched-videos", response_model=WatchHistoryResponse)
async def get_user_watch_history(
    user_id: str,
    admin_user: dict = Depends(require_admin),
):
    """Get the dynamic watch history for a specific user using Supabase PostgreSQL."""
    # 1. Fetch user email for the modal header
    user_name = "Unknown User"
    try:
        # Service role needed to read auth.users
        auth_resp = supabase.auth.admin.get_user_by_id(user_id)
        if auth_resp and auth_resp.user:
            user_name = auth_resp.user.email.split("@")[0]
    except Exception:
        raise HTTPException(status_code=404, detail="User not found.")

    # 2. Fetch completed video progress for this user
    progress_resp = (
        supabase.table("progress")
        .select("video_id")
        .eq("user_id", user_id)
        .eq("completed", True)
        .execute()
    )
    progress_data = progress_resp.data or []
    
    if not progress_data:
        return WatchHistoryResponse(
            success=True,
            user_name=user_name,
            total_watched=0,
            watched_videos=[]
        )

    watched_video_ids = [p["video_id"] for p in progress_data]

    # 3. Fetch matched videos along with course (module) title
    videos_resp = (
        supabase.table("videos")
        .select("id, title, courses(title)")
        .in_("id", watched_video_ids)
        .execute()
    )
    videos = videos_resp.data or []

    # 4. Format the response
    watched_videos_list = []
    for v in videos:
        course_data = v.get("courses")
        module_name = course_data.get("title", "General") if isinstance(course_data, dict) else "General"
        
        watched_videos_list.append(WatchedVideo(
            video_id=v["id"],
            title=v.get("title", "Untitled Video"),
            module_name=module_name,
            duration="Watched"  # We don't have duration in schema, fallback to text
        ))

    return WatchHistoryResponse(
        success=True,
        user_name=user_name,
        total_watched=len(watched_videos_list),
        watched_videos=watched_videos_list
    )


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
            "question_type": body.question_type,
            "correct_answer": body.correct_answer,
            "explanation": body.explanation,
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
            "question_type": body.question_type,
            "correct_answer": body.correct_answer,
            "explanation": body.explanation,
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
