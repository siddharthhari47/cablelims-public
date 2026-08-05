"""Response models for api/meta.py."""
from typing import Optional

from pydantic import BaseModel


class StandardOut(BaseModel):
    standard_id: str
    name: str
    edition: Optional[str] = None
    amendment: Optional[str] = None
    scope_summary: Optional[str] = None


class AssistantOut(BaseModel):
    id: str
    full_name: str
    username: str
