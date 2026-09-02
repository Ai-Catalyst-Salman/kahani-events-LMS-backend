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


from app.schemas.quiz_schemas import AIQuizGenerateRequest
from app.services.ai_quiz_service import generate_mixed_quiz, evaluate_quiz_answers_with_ai

@router.post("/video/{video_id}/generate-and-save-quiz")
async def generate_and_save_quiz(
    video_id: str,
    request: AIQuizGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Generate questions using Gemini based on a transcript and save them to Supabase.
    """
    try:
        # Generate the questions
        questions = await generate_mixed_quiz(transcript=request.transcript)
        
        # Map for DB insert
        db_inserts = []
        for q in questions:
            # Maintain backward compatibility for submit_quiz by calculating correct_option_index
            correct_index = -1
            if q.question_type in ["mcq", "true_false"]:
                try:
                    correct_index = q.options.index(q.correct_answer)
                except ValueError:
                    correct_index = 0 # Fallback in case of weird mismatch
            
            db_inserts.append({
                "video_id": video_id,
                "question": q.question,
                "question_type": q.question_type,
                "options": q.options,
                "correct_option_index": correct_index,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation
            })
            
        # Bulk insert
        if db_inserts:
            supabase.table("video_questions").insert(db_inserts).execute()
            
        return {"message": "Quiz generated and saved successfully", "questions": db_inserts}
        
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate and save quiz: {str(e)}")

import time

# Simple in-memory rate limiting dictionary to prevent DoS via spamming AI endpoints
# Format: { user_id: last_request_timestamp }
_generate_rate_limit = {}
COOLDOWN_SECONDS = 30

class GenerateAssignQuizRequest(BaseModel):
    user_id: str

@router.post("/video/{video_id}/generate-and-assign-quiz")
async def generate_and_assign_quiz(
    video_id: str,
    request: GenerateAssignQuizRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Generate a unique mixed quiz on the fly and assign it to the user with an audit trail.
    """
    req_user_id = request.user_id or current_user["id"]
    
    # [SECURITY FIX: IDOR] Prevent users from generating quizzes for other users
    if req_user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform this action.")
        
    # [SECURITY FIX: DOS/Rate Limiting] Enforce a cooldown to prevent AI quota exhaustion
    now = time.time()
    last_req_time = _generate_rate_limit.get(req_user_id, 0)
    if now - last_req_time < COOLDOWN_SECONDS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Please wait {int(COOLDOWN_SECONDS - (now - last_req_time))} seconds before generating another quiz.")
    
    _generate_rate_limit[req_user_id] = now
    
    # 1. Fetch the video transcript from DB
    video_resp = supabase.table("videos").select("transcript").eq("id", video_id).single().execute()
    if not video_resp.data or not video_resp.data.get("transcript"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video or transcript not found")
        
    transcript = video_resp.data["transcript"]
    
    try:
        # 2. Call AI service to generate a unique quiz
        questions = await generate_mixed_quiz(transcript=transcript)
        json_questions = [q.model_dump() for q in questions]
        
        # 3. Dynamic Randomization
        import random
        
        # Shuffle the overall question pool
        random.shuffle(json_questions)
        
        # Determine dynamic length (between 5 and 8, or max available)
        total_available = len(json_questions)
        limit = random.randint(min(5, total_available), min(8, total_available)) if total_available > 0 else 0
        
        if limit > 0:
            json_questions = json_questions[:limit]
            
        # Shuffle multiple-choice options for each selected question
        for q in json_questions:
            if q.get("question_type") == "mcq" and q.get("options"):
                # The validation logic in submit-attempt matches string to string, 
                # so we only need to shuffle the options array itself.
                random.shuffle(q["options"])
        
        # 4. Insert into quiz_attempts
        attempt_resp = supabase.table("quiz_attempts").insert({
            "user_id": req_user_id,
            "video_id": video_id,
            "generated_questions": json_questions
        }).execute()
        
        if not attempt_resp.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save quiz attempt")
            
        # 5. Return to frontend
        return {
            "quiz_attempt_id": attempt_resp.data[0]["id"],
            "questions": json_questions
        }
    except Exception as e:
        # [SECURITY FIX: DATA LEAKAGE] Sanitize the error message so stack traces don't leak to the client
        print(f"Error in generate_and_assign_quiz: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while generating the quiz. Please try again.")

import difflib

def is_smart_match(user_ans: str, correct_ans: str) -> bool:
    """Smart comparison for quiz answers handling minor typos and plurals."""
    user_clean = user_ans.strip().lower()
    correct_clean = correct_ans.strip().lower()
    
    if user_clean == correct_clean:
        return True
        
    # Basic singular/plural check
    if user_clean + 's' == correct_clean or correct_clean + 's' == user_clean:
        return True
    if user_clean + 'es' == correct_clean or correct_clean + 'es' == user_clean:
        return True
        
    # Fuzzy matching for typos
    similarity = difflib.SequenceMatcher(None, user_clean, correct_clean).ratio()
    return similarity >= 0.85

class SubmitAttemptRequest(BaseModel):
    quiz_attempt_id: str
    student_answers: dict

@router.post("/submit-attempt")
async def submit_attempt(
    request: SubmitAttemptRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Evaluate student answers against the saved AI generated quiz attempt.
    """
    # 1. Fetch original quiz attempt
    attempt_resp = supabase.table("quiz_attempts").select("*").eq("id", request.quiz_attempt_id).single().execute()
    if not attempt_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz attempt not found")
        
    attempt = attempt_resp.data
    user_id = attempt["user_id"]
    generated_questions = attempt["generated_questions"]
    
    # Ensure current user owns this attempt (or is admin)
    if user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit this attempt")
    
    # 2. Evaluate answers
    total = len(generated_questions)
    qa_pairs = []
    
    for i, q in enumerate(generated_questions):
        student_ans = request.student_answers.get(str(i))
        q_type = q.get("question_type", "mcq")
        user_ans_str = ""
        
        if student_ans is not None:
            if q_type == "mcq":
                try:
                    idx = int(student_ans)
                    opts = q.get("options", [])
                    if 0 <= idx < len(opts):
                        user_ans_str = opts[idx]
                except (ValueError, TypeError):
                    pass
            elif q_type == "true_false":
                try:
                    idx = int(student_ans)
                    if idx == 0:
                        user_ans_str = "True"
                    elif idx == 1:
                        user_ans_str = "False"
                except (ValueError, TypeError):
                    pass
            else:
                user_ans_str = str(student_ans)
                
        correct_ans_str = str(q.get("correct_answer", ""))
        qa_pairs.append({
            "index": str(i),
            "question": q.get("question", ""),
            "correct_answer": correct_ans_str,
            "user_answer": user_ans_str
        })
        
    ai_evaluations = await evaluate_quiz_answers_with_ai(qa_pairs)
    
    score = 0
    results = []
    
    for i, q in enumerate(generated_questions):
        is_correct = bool(ai_evaluations.get(str(i), False))
        if is_correct:
            score += 1
            
        results.append({
            "question_index": i,
            "is_correct": is_correct,
            "correct_answer": q.get("correct_answer"),
            "explanation": q.get("explanation")
        })
        
    # 3. Save to quiz_scores
    score_resp = supabase.table("quiz_scores").insert({
        "quiz_attempt_id": request.quiz_attempt_id,
        "user_id": user_id,
        "score": score,
        "total_questions": total
    }).execute()
    
    if not score_resp.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save quiz score")
        
    pass_percentage = (score / total) * 100 if total > 0 else 0
    passed = pass_percentage >= 80
    
    # Calculate exactly how many questions are needed to hit 80%
    import math
    pass_threshold = math.ceil(total * 0.8)
    
    # 4. If passed, mark the video as completed
    if passed:
        supabase.table("progress").upsert(
            {
                "user_id": user_id,
                "video_id": attempt["video_id"],
                "completed": True,
            },
            on_conflict="user_id,video_id"
        ).execute()

    return {
        "score": score,
        "total": total,
        "passed": passed,
        "pass_threshold": pass_threshold,
        "results": results
    }
