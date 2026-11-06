from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class SmsVerification(Base):
    __tablename__ = "sms_verifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    challenge_hash = Column(String(64), nullable=False, unique=True, index=True)
    purpose = Column(String(16), nullable=False, index=True)
    phone_number = Column(String(16), nullable=False)
    phone_hash = Column(String(64), nullable=False, index=True)
    request_hash = Column(String(64), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
