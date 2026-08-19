"""
app/api/courses.py
------------------
Course endpoints (public read — no auth required):
  GET /courses        → list of {id, title, description}
  GET /courses/{id}   → course detail + its videos
"""

from fastapi import APIRouter, HTTPException, status

from app.core.supabase_client import supabase
from app.schemas.courses import CourseOut, CourseDetailOut, VideoOut

router = APIRouter()


@router.get("", response_model=list[CourseOut])
async def list_courses():
    """Return all courses ordered by creation date."""
    response = (
        supabase.table("courses")
        .select("id, title, description, department, created_at")
        .order("created_at")
        .execute()
    )
    return response.data or []


@router.get("/{course_id}", response_model=CourseDetailOut)
async def get_course(course_id: str):
    """Return a single course with its associated videos."""
    course_response = (
        supabase.table("courses")
        .select("id, title, description, department, created_at")
        .eq("id", course_id)
        .single()
        .execute()
    )

    if not course_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    videos_response = (
        supabase.table("videos")
        .select("id, course_id, title, video_url, transcript, created_at")
        .eq("course_id", course_id)
        .order("created_at")
        .execute()
    )

    return CourseDetailOut(
        **course_response.data,
        videos=[VideoOut(**v) for v in (videos_response.data or [])],
    )
