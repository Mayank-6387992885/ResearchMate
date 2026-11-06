from sqlalchemy import Boolean, Column, DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.sql import func

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=True)
    google_sub = Column(String(255), nullable=True, unique=True)
    github_id = Column(String(255), nullable=True, unique=True)
    linkedin_sub = Column(String(255), nullable=True, unique=True)
    phone_number = Column(String(16), nullable=True, unique=True, index=True)
    phone_verified = Column(Boolean, nullable=False, default=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    username = Column(String(30), nullable=True, unique=True)
    profile_data = Column(Text, nullable=False, default="{}")
    profile_image = Column(LargeBinary, nullable=True)
    profile_image_type = Column(String(32), nullable=True)
    notification_preferences = Column(Text, nullable=False, default="{}")
    privacy_settings = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
