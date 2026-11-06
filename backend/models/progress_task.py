from typing import Any

from sqlalchemy import JSON, Column, Float, Integer, String, Text

from database import Base


class ProgressTask(Base):
    __tablename__ = "progress_tasks"

    task_id = Column(String(36), primary_key=True)
    progress = Column(Integer, nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, index=True)
    updated_at = Column(Float, nullable=False)
    started_at = Column(Float, nullable=True)
    owner_pid = Column(Integer, nullable=False)
    owner_user_id = Column(Integer, nullable=True, index=True)
    result = Column(JSON, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        task = {
            "task_id": self.task_id,
            "progress": self.progress,
            "message": self.message,
            "status": self.status,
            "updated_at": self.updated_at,
        }
        if self.started_at is not None:
            task["started_at"] = self.started_at
        if self.result is not None:
            task["result"] = self.result
        return task
