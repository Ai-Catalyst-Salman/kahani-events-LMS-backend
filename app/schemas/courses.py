"""
app/schemas/courses.py
----------------------
Pydantic v2 models for courses and videos.
"""

from pydantic import BaseModel
from datetime import datetime


class VideoOut(BaseModel):
    id: str
    course_id: str
    title: str
    video_url: str
    transcript: str | None = None
    created_at: datetime


class CourseOut(BaseModel):
    id: str
    title: str
    description: str | None
    department: str | None = None
    progression_mode: str | None = "open"
    created_at: datetime


class CourseDetailOut(BaseModel):
    id: str
    title: str
    description: str | None
    department: str | None = None
    progression_mode: str | None = "open"
    created_at: datetime
    videos: list[VideoOut]
