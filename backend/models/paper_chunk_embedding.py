from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func

from database import Base


class PaperChunkEmbedding(Base):
    __tablename__ = "paper_chunk_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(Integer, nullable=False)
    page = Column(Integer, nullable=False)
    section = Column(String, nullable=False, default="Document")
    model_name = Column(String, nullable=False, index=True)
    content_hash = Column(String, nullable=False, index=True)
    embedding = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
