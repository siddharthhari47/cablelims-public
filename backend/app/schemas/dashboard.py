"""Response models for api/dashboard.py."""
from typing import List, Optional

from pydantic import BaseModel


class RecentActivityItem(BaseModel):
    actor: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    timestamp: str


class DashboardResponse(BaseModel):
    total_samples: int
    pending: int
    in_progress: int
    scientist_review: int
    completed: int
    repeat_tests: int
    certificates_issued: int
    recent_activity: List[RecentActivityItem]
