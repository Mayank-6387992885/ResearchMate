from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base


class PaperEmbedding(Base):
    __tablename__ = "paper_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    model_name = Column(String(120), nullable=False)
    content_hash = Column(String(64), nullable=False)
    embedding = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
