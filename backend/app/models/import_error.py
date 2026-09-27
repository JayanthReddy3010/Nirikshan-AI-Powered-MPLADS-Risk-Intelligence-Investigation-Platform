from sqlalchemy import Column, Integer, String, Text

from backend.app.database import Base


class ImportErrorRecord(Base):
    __tablename__ = "import_errors"

    id = Column(Integer, primary_key=True, index=True)
    source_row_number = Column(Integer, unique=True, nullable=False, index=True)
    reason = Column(String(255), nullable=False, index=True)
    details = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ImportErrorRecord(id={self.id}, source_row_number={self.source_row_number}, "
            f"reason='{self.reason}')>"
        )
