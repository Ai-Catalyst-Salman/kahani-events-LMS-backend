"""
app/schemas/auth.py
-------------------
Pydantic v2 models for auth-related request/response bodies.
"""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MeResponse(BaseModel):
    id: str
    email: str
    role: str
