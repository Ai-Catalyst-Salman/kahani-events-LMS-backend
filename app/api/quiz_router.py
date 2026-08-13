import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from moviepy import VideoFileClip
from app.services.ai_quiz_service import transcribe_audio, generate_quiz_from_transcript
from app.core.supabase_client import supabase

router = APIRouter()

@router.post("/upload-and-generate-quiz")
async def upload_and_generate_quiz(
    video_id: str = Form(...),
    file: UploadFile = File(...)
):
    temp_video_path = f"temp_{uuid.uuid4()}.mp4"
    temp_audio_path = f"temp_{uuid.uuid4()}.mp3"
    
    try:
        # Save video file
        with open(temp_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Extract audio using moviepy
        video = VideoFileClip(temp_video_path)
        video.audio.write_audiofile(temp_audio_path, logger=None)
        video.close()
        
        # Transcribe audio using Groq Whisper API
        transcript = await transcribe_audio(temp_audio_path)
        
        # Generate Quiz using Gemini
        quiz_result = await generate_quiz_from_transcript(transcript)
        
        # Insert generated questions into Supabase
        for q in quiz_result.questions:
            # Standardize options and correct index for DB
            correct_idx = 0
            if q.correct_answer in q.options:
                correct_idx = q.options.index(q.correct_answer)
            else:
                if len(q.options) == 0:
                    q.options = [q.correct_answer]
                elif q.correct_answer not in q.options:
                    q.options.append(q.correct_answer)
                    correct_idx = len(q.options) - 1
                    
            supabase.table("video_questions").insert({
                "video_id": video_id,
                "question": q.question,
                "options": q.options,
                "correct_option_index": correct_idx
            }).execute()
            
        return {
            "status": "success", 
            "message": "Quiz generated successfully", 
            "transcript": transcript,
            "questions_count": len(quiz_result.questions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # Cleanup temporary files
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
