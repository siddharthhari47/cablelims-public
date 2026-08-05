"""Response models for api/admin.py."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
    is_active: bool
    is_demo: bool
    created_at: str


class AuditEventOut(BaseModel):
    id: str
    actor_name: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: str


class AuditListResponse(BaseModel):
    total: int
    events: List[AuditEventOut]
