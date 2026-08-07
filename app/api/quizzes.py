"""
app/api/quizzes.py
------------------
Quiz endpoints:
  GET /quizzes/video/{video_id}/questions
    → Return all questions for a video (auth required, video must be completed)
    401 — unauthenticated
    403 — user hasn't completed this video yet
    200 — list of {id, question, options} (NO correct_option_index exposed to learner)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.supabase_client import supabase
from app.schemas.quizzes import QuizOut

router = APIRouter()


class QuestionForLearner(BaseModel):
    """Safe question schema — never exposes the correct answer index to the client."""
    id: str
    question: str
    options: list[str]


class QuizSubmission(BaseModel):
    answers: dict  # {question_id: selected_index}


class QuizResult(BaseModel):
    score: int
    total: int
    passed: bool
    pass_threshold: int


@router.get("/video/{video_id}/questions", response_model=list[QuestionForLearner])
async def get_video_questions(
    video_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Return quiz questions for a video.
    The user must have completed (marked) this video first.
    Correct answer index is never sent to the client.
    """
    user_id = current_user["id"]

    # 1. Check the video exists and get it
    video_resp = (
        supabase.table("videos")
        .select("id, course_id")
        .eq("id", video_id)
        .single()
        .execute()
    )
    if not video_resp.data:
        raise HTTPException(status_code=404, detail="Video not found")

    # No longer requiring video to be 'completed' in DB before fetching questions,
    # as completing the video now happens when the quiz is passed.

    # 3. Fetch questions — strip correct_option_index
    questions_resp = (
        supabase.table("video_questions")
        .select("id, question, options")
        .eq("video_id", video_id)
        .order("created_at")
        .execute()
    )
    return questions_resp.data or []


@router.post("/video/{video_id}/submit", response_model=QuizResult)
async def submit_quiz(
    video_id: str,
    body: QuizSubmission,
    current_user: dict = Depends(get_current_user),
):
    """
    Submit quiz answers for a video. Returns score and pass/fail.
    Fetches correct answers server-side — client never sees them.
    """
    user_id = current_user["id"]

    # Video completion check removed. Users can submit the quiz directly.

    # 2. Fetch all questions with answers (server-side only)
    questions_resp = (
        supabase.table("video_questions")
        .select("id, correct_option_index")
        .eq("video_id", video_id)
        .execute()
    )
    questions = questions_resp.data or []
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this video")

    # 3. Grade answers
    total = len(questions)
    score = 0
    for q in questions:
        submitted = body.answers.get(q["id"])
        if submitted is not None and int(submitted) == q["correct_option_index"]:
            score += 1

    pass_threshold = max(1, round(total * 0.67))  # 67% to pass
    passed = score >= pass_threshold

    # 4. If passed, mark the video as completed in the progress table
    if passed:
        supabase.table("progress").upsert(
            {
                "user_id": user_id,
                "video_id": video_id,
                "completed": True,
            },
            on_conflict="user_id,video_id"
        ).execute()

    return QuizResult(score=score, total=total, passed=passed, pass_threshold=pass_threshold)


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    quiz_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Return quiz details if the user has completed ≥1 video in the quiz's course.
    """
    quiz_response = (
        supabase.table("quizzes")
        .select("id, title, course_id, created_at")
        .eq("id", quiz_id)
        .single()
        .execute()
    )
    if not quiz_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    quiz = quiz_response.data
    course_id = quiz["course_id"]
    user_id = current_user["id"]

    progress_response = (
        supabase.table("progress")
        .select("video_id, videos!inner(course_id)")
        .eq("user_id", user_id)
        .eq("videos.course_id", course_id)
        .eq("completed", True)
        .limit(1)
        .execute()
    )
    completed_count = len(progress_response.data) if progress_response.data else 0

    if completed_count == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete at least one video in this course before taking the quiz",
        )

    return QuizOut(**quiz)
