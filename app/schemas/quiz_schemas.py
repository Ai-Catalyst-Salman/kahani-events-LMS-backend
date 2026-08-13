"""
app/schemas/quiz_schemas.py
---------------------------
Schemas for AI quiz generation.
"""

from pydantic import BaseModel
from typing import List, Literal, Optional

class QuizQuestion(BaseModel):
    question: str
    question_type: Literal["MCQ", "True/False", "Fill-in-the-blank"]
    options: List[str]
    correct_answer: str
    explanation: Optional[str] = None

class QuizGenerationResult(BaseModel):
    questions: List[QuizQuestion]

class AIQuestionSchema(BaseModel):
    question: str
    question_type: Literal["mcq", "true_false", "fill_in_blank"]
    options: List[str]
    correct_answer: str
    explanation: str

class AIQuizGenerateRequest(BaseModel):
    transcript: str
