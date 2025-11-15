import asyncio
from fastapi.websockets import WebSocket

active_connections: list[WebSocket] = []


async def broadcast_progress(progress: float):
    """Send progress update to all connected WebSocket clients"""
    if active_connections:
        disconnected = []
        for connection in active_connections:
            try:
                await connection.send_json({
                    "progress": progress,
                    "percentage": round(progress * 100, 1)
                })
            except Exception as e:
                print(f"Failed to send to client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            active_connections.remove(conn)