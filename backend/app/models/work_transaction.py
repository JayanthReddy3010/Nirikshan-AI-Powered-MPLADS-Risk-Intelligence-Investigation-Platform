from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from backend.app.database import Base


class WorkTransaction(Base):
    __tablename__ = "work_transactions"

    id = Column(Integer, primary_key=True, index=True)
    source_row_number = Column(Integer, unique=True, nullable=False, index=True)
    work_id = Column(String(255), ForeignKey("works.work_id", ondelete="CASCADE"), nullable=False, index=True)
    expenditure_date = Column(Date, nullable=True, index=True)
    vendor_name = Column(Text, nullable=True, index=True)
    payment_status = Column(Text, nullable=True, index=True)
    fund_disbursed_amount = Column(Numeric(20, 2), nullable=True)

    work = relationship("Work", back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<WorkTransaction(id={self.id}, source_row_number={self.source_row_number}, "
            f"work_id='{self.work_id}', expenditure_date={self.expenditure_date}, "
            f"amount={self.fund_disbursed_amount})>"
        )
