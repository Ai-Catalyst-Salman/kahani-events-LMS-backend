"""
app/schemas/progress.py
-----------------------
Pydantic v2 models for progress tracking.
"""

from pydantic import BaseModel


class ProgressCompleteRequest(BaseModel):
    video_id: str


class ProgressCompleteResponse(BaseModel):
    message: str
    video_id: str
