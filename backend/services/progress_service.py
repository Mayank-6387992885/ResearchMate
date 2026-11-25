import ctypes
import os
import time
from ctypes import wintypes
from typing import Any

from database import SessionLocal
from models.progress_task import ProgressTask


def process_is_running(process_id: int | None) -> bool:
    if process_id is None:
        return False

    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_exit_code.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = open_process(0x1000, False, process_id)
        if not handle:
            return ctypes.get_last_error() == 5

        try:
            exit_code = wintypes.DWORD()
            if not get_exit_code(handle, ctypes.byref(exit_code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return exit_code.value == 259
        finally:
            close_handle(handle)

    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def set_progress(
    task_id: str,
    progress: int,
    message: str,
    status: str = "processing",
    result: dict[str, Any] | None = None,
    user_id: int | None = None,
):
    progress = max(0, min(100, int(progress)))
    if status == "processing":
        progress = min(progress, 99)
    elif status == "completed":
        progress = 100

    timestamp = time.time()
    with SessionLocal() as db:
        existing_task = db.get(ProgressTask, task_id)
        task_result = result
        if task_result is None and existing_task is not None:
            task_result = existing_task.result
        db.merge(ProgressTask(
            task_id=task_id,
            progress=progress,
            message=message,
            status=status,
            updated_at=timestamp,
            started_at=(
                existing_task.started_at
                if existing_task is not None and existing_task.started_at is not None
                else timestamp
            ),
            owner_pid=os.getpid(),
            owner_user_id=(
                user_id
                if user_id is not None
                else existing_task.owner_user_id if existing_task is not None else None
            ),
            result=task_result,
        ))
        db.commit()
    print(f"[PROGRESS][{task_id[:8]}] {progress}% | {message}", flush=True)


def get_progress_state(task_id: str, user_id: int) -> dict[str, Any] | None:
    with SessionLocal() as db:
        task = db.get(ProgressTask, task_id)
        if task is None or getattr(task, "owner_user_id", None) != user_id:
            return None
        if getattr(task, "status", None) == "processing" and not process_is_running(
            getattr(task, "owner_pid", None)
        ):
            setattr(task, "status", "error")
            setattr(task, "message", "Backend stopped before this analysis completed.")
            setattr(task, "updated_at", time.time())
            db.commit()
        return task.to_dict()
