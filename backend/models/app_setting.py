from sqlalchemy import Column, String

from database import Base


class AppSetting(Base):
    __tablename__ = "application_settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(16), nullable=False)
