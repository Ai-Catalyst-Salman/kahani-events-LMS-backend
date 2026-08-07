"""
app/schemas/quizzes.py
----------------------
Pydantic v2 models for quizzes.
"""

from pydantic import BaseModel
from datetime import datetime


class QuizOut(BaseModel):
    id: str
    title: str
    course_id: str
    created_at: datetime
