"""WebSocket endpoint — pushes alerts to the live dashboard."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..deps import decode_user_from_ws
from ..engine.ws_hub import hub

router = APIRouter()


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    user = await decode_user_from_ws(websocket)
    if user is None:
        await websocket.close(code=4401)
        return

    await hub.connect(user.id, websocket)
    try:
        while True:
            # Keep the socket open; ignore inbound frames.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(user.id, websocket)
