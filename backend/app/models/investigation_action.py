from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.database import Base


class InvestigationAction(Base):
    __tablename__ = "investigation_actions"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(String(255), ForeignKey("works.work_id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    officer_name = Column(Text, nullable=True)

    work = relationship("Work")

    def __repr__(self) -> str:
        return f"<InvestigationAction(id={self.id}, work_id='{self.work_id}', action='{self.action}')>"
