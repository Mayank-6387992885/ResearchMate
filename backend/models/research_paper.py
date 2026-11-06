from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from database import Base


class ResearchPaper(Base):
    __tablename__ = "research_papers"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(1000), nullable=False)
    summary = Column(Text, nullable=False)
    pages = Column(Integer, nullable=False, default=0)
    is_saved = Column(Boolean, nullable=False, default=False)
    category = Column(String(40), nullable=False, default="Uncategorized")
    classification = Column(JSON, nullable=False, default=dict)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
