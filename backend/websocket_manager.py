from fastapi import WebSocket

active_connections = {}


async def connect(websocket: WebSocket, task_id: str):
    await websocket.accept()
    active_connections[task_id] = websocket


async def send_progress(task_id: str, progress: int, message: str):
    websocket = active_connections.get(task_id)

    if websocket:
        await websocket.send_json({
            "progress": progress,
            "message": message
        })


def disconnect(task_id: str):
    active_connections.pop(task_id, None)
    