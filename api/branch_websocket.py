"""Branch WebSocket API — real-time multi-user collaboration."""

import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.branch_narrative import manager

router = APIRouter(prefix="/ws/branch", tags=["branch-websocket"])
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for branch sessions."""

    def __init__(self):
        # session_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket):
        """Accept connection and add to session."""
        await websocket.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = set()
            self._connections[session_id].add(websocket)
            count = len(self._connections[session_id])
        logger.info(f"WebSocket connected to session {session_id[:8]} ({count} users)")
        return count

    async def disconnect(self, session_id: str, websocket: WebSocket):
        """Remove connection from session."""
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(websocket)
                count = len(self._connections[session_id])
                if count == 0:
                    del self._connections[session_id]
                logger.info(f"WebSocket disconnected from session {session_id[:8]} ({count} users)")

    async def broadcast(self, session_id: str, message: dict, exclude: WebSocket = None):
        """Broadcast message to all connections in session except sender."""
        async with self._lock:
            connections = self._connections.get(session_id, set()).copy()

        dead_connections = []
        for conn in connections:
            if conn == exclude:
                continue
            try:
                await conn.send_json(message)
            except Exception:
                dead_connections.append(conn)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for conn in dead_connections:
                    self._connections.get(session_id, set()).discard(conn)

    async def get_user_count(self, session_id: str) -> int:
        """Get number of connected users in session."""
        async with self._lock:
            return len(self._connections.get(session_id, set()))


connection_manager = ConnectionManager()


@router.websocket("/{session_id}")
async def branch_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time branch collaboration.

    Protocol:
    - Client sends: {"action": "choose", "choice_index": 0}
    - Client sends: {"action": "goto", "node_id": "abc123"}
    - Client sends: {"action": "sync"} — request current state
    - Server broadcasts: {"type": "navigation", "node": {...}, "user_count": N}
    - Server broadcasts: {"type": "user_joined", "user_count": N}
    - Server broadcasts: {"type": "user_left", "user_count": N}
    """
    # Verify session exists
    try:
        manager.get_current_node(session_id)
    except KeyError:
        await websocket.close(code=4004, reason="Session not found")
        return

    user_count = await connection_manager.connect(session_id, websocket)

    # Broadcast user joined
    await connection_manager.broadcast(
        session_id,
        {"type": "user_joined", "user_count": user_count},
        exclude=websocket,
    )

    # Send initial state to new user
    try:
        node = manager.get_current_node(session_id)
        await websocket.send_json({
            "type": "sync",
            "node": node,
            "user_count": user_count,
        })
    except Exception as e:
        logger.error(f"Failed to send initial state: {e}")

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "choose":
                choice_index = data.get("choice_index", 0)
                try:
                    # Try existing branch first
                    node = manager.choose_branch(session_id, choice_index)
                    if node is None:
                        # Need LLM generation — not supported in WebSocket
                        await websocket.send_json({
                            "type": "error",
                            "message": "Choice requires LLM generation. Use HTTP endpoint.",
                        })
                        continue

                    # Broadcast navigation to all users
                    user_count = await connection_manager.get_user_count(session_id)
                    await connection_manager.broadcast(
                        session_id,
                        {"type": "navigation", "node": node, "user_count": user_count, "action": "choose"},
                    )
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif action == "goto":
                node_id = data.get("node_id")
                if not node_id:
                    await websocket.send_json({"type": "error", "message": "node_id required"})
                    continue
                try:
                    node = manager.goto_node(session_id, node_id)
                    user_count = await connection_manager.get_user_count(session_id)
                    await connection_manager.broadcast(
                        session_id,
                        {"type": "navigation", "node": node, "user_count": user_count, "action": "goto"},
                    )
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif action == "back":
                try:
                    node = manager.go_back(session_id)
                    user_count = await connection_manager.get_user_count(session_id)
                    await connection_manager.broadcast(
                        session_id,
                        {"type": "navigation", "node": node, "user_count": user_count, "action": "back"},
                    )
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif action == "sync":
                try:
                    node = manager.get_current_node(session_id)
                    user_count = await connection_manager.get_user_count(session_id)
                    await websocket.send_json({
                        "type": "sync",
                        "node": node,
                        "user_count": user_count,
                    })
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await connection_manager.disconnect(session_id, websocket)
        user_count = await connection_manager.get_user_count(session_id)
        await connection_manager.broadcast(
            session_id,
            {"type": "user_left", "user_count": user_count},
        )
