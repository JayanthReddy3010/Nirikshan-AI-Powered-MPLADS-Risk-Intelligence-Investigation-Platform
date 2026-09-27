from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class InvestigationActionCreate(BaseModel):
    action: str
    comment: Optional[str] = None
    officer_name: Optional[str] = None


class InvestigationActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_id: str
    action: str
    comment: Optional[str] = None
    created_at: datetime
    officer_name: Optional[str] = None