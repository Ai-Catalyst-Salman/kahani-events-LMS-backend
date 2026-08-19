"""
app/schemas/admin.py
--------------------
Pydantic v2 models for admin endpoints — with full input validation.
"""

from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
import re


class AdminOverviewResponse(BaseModel):
    total_courses: int
    total_videos: int
    total_completions: int
    total_users: int

class TopPerformer(BaseModel):
    user_id: str
    name: str
    completed_modules: int
    completion_percentage: int = 0



# ── Course management ─────────────────────────────────────────────────────────

class CourseCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    department: str = "General"

    @field_validator("title")
    @classmethod
    def title_must_be_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty")
        if len(v) > 200:
            raise ValueError("Title cannot exceed 200 characters")
        return v

    @field_validator("description")
    @classmethod
    def description_strip(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) > 1000:
                raise ValueError("Description cannot exceed 1000 characters")
            return v or None
        return v


class CourseCreateResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    created_at: datetime


# ── Video management ──────────────────────────────────────────────────────────

class VideoCreateRequest(BaseModel):
    course_id: str
    title: str
    video_url: str
    transcript: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_must_be_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty")
        if len(v) > 200:
            raise ValueError("Title cannot exceed 200 characters")
        return v

    @field_validator("video_url")
    @classmethod
    def url_must_be_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Video URL cannot be empty")
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("Video URL must start with http:// or https://")
        if len(v) > 2048:
            raise ValueError("Video URL is too long")
        return v

    @field_validator("course_id")
    @classmethod
    def course_id_must_be_uuid(cls, v: str) -> str:
        v = v.strip()
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        if not uuid_pattern.match(v):
            raise ValueError("course_id must be a valid UUID")
        return v


class VideoCreateResponse(BaseModel):
    id: str
    course_id: str
    title: str
    video_url: str
    transcript: Optional[str] = None
    created_at: datetime


# ── User management ───────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: Optional[str] = None


class UserCreateRequest(BaseModel):
    email: str
    password: str
    role: str = "learner"

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("admin", "learner"):
            raise ValueError("role must be either 'admin' or 'learner'")
        return v


class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class UserRoleUpdateRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("admin", "learner"):
            raise ValueError("role must be either 'admin' or 'learner'")
        return v


class UserRoleUpdateResponse(BaseModel):
    user_id: str
    role: str

class WatchedVideo(BaseModel):
    video_id: str
    title: str
    module_name: str
    duration: str

class WatchHistoryResponse(BaseModel):
    success: bool
    user_name: str
    total_watched: int
    watched_videos: list[WatchedVideo]

# ── Questions management ──────────────────────────────────────────────────────

class QuestionCreateRequest(BaseModel):
    video_id: str
    question: str
    options: list[str]
    correct_option_index: int

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("Must provide at least 2 options")
        return [opt.strip() for opt in v if opt.strip()]

    @field_validator("correct_option_index")
    @classmethod
    def validate_correct_index(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Index must be >= 0")
        return v

class QuestionUpdateRequest(BaseModel):
    question: str
    options: list[str]
    correct_option_index: int

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("Must provide at least 2 options")
        return [opt.strip() for opt in v if opt.strip()]

    @field_validator("correct_option_index")
    @classmethod
    def validate_correct_index(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Index must be >= 0")
        return v

class QuestionOut(BaseModel):
    id: str
    video_id: str
    question: str
    options: list[str]
    correct_option_index: int
    question_type: Optional[str] = "mcq"
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    created_at: datetime
