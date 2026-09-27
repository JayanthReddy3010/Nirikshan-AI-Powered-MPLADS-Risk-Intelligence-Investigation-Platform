from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.database import Base


class Work(Base):
    __tablename__ = "works"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(String(255), unique=True, nullable=False, index=True)
    state = Column(Text, nullable=True, index=True)
    mp_name = Column(Text, nullable=True, index=True)
    constituency = Column(Text, nullable=True, index=True)
    work = Column(Text, nullable=True)
    ida = Column(Text, nullable=True)

    transactions = relationship(
        "WorkTransaction",
        back_populates="work",
        cascade="all, delete-orphan",
        foreign_keys="WorkTransaction.work_id",
    )

    def __repr__(self) -> str:
        return f"<Work(id={self.id}, work_id='{self.work_id}')>"
