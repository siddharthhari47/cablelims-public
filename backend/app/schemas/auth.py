"""Response models for api/auth.py."""
from pydantic import BaseModel

from app.schemas.common import UserBrief


class DemoHintResponse(BaseModel):
    show_demo_hint: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserBrief


class MeResponse(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
