"""
app/api/progress.py
-------------------
Progress endpoints:
  POST /progress/complete — mark a video as completed (auth required)
    Body: { "video_id": "<uuid>" }
    Upserts into the progress table (safe to call multiple times).
    422 if body is missing or malformed (handled automatically by Pydantic).
    401 if unauthenticated.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.supabase_client import supabase
from app.schemas.progress import ProgressCompleteRequest, ProgressCompleteResponse

router = APIRouter()


@router.post("/complete", response_model=ProgressCompleteResponse)
async def complete_video(
    body: ProgressCompleteRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Mark a video as completed for the authenticated user.
    Uses upsert so re-calling the same video_id is idempotent.
    """
    user_id = current_user["id"]
    video_id = body.video_id

    # Verify the video exists to give a clear error rather than a DB constraint error.
    video_response = (
        supabase.table("videos")
        .select("id")
        .eq("id", video_id)
        .single()
        .execute()
    )

    if not video_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    # Upsert progress — safe to call multiple times for the same video.
    supabase.table("progress").upsert(
        {
            "user_id": user_id,
            "video_id": video_id,
            "completed": True,
        },
        on_conflict="user_id,video_id"
    ).execute()

    return ProgressCompleteResponse(
        message="Video marked as completed",
        video_id=video_id,
    )

@router.get("")
async def get_progress(current_user: dict = Depends(get_current_user)):
    """
    Get all completed video IDs for the current user.
    """
    user_id = current_user["id"]
    response = (
        supabase.table("progress")
        .select("video_id")
        .eq("user_id", user_id)
        .eq("completed", True)
        .execute()
    )
    return response.data or []
