from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class BattleRoom:
    id: int
    guild_id: int
    channel_id: int
    challenger_id: int
    opponent_id: int
    fmt_key: str          # e.g., "ou", "ubers"
    ranked: bool = False
    started: bool = False
    message_id: Optional[int] = None  # public challenge message id (if you store it)

class BattleManager:
    def __init__(self):
        self._next_id: int = 1
        self._rooms: Dict[int, BattleRoom] = {}
        self._user_to_room: Dict[int, int] = {}

    def add(
        self,
        *,
        guild_id: int,
        channel_id: int,
        challenger_id: int,
        opponent_id: int,
        ranked: bool,
        fmt_key: str,
    ) -> BattleRoom:
        rid = self._next_id
        self._next_id += 1
        room = BattleRoom(
            id=rid,
            guild_id=guild_id or 0,
            channel_id=channel_id or 0,
            challenger_id=challenger_id,
            opponent_id=opponent_id,
            ranked=ranked,
            fmt_key=fmt_key,
        )
        self._rooms[rid] = room
        self._user_to_room[challenger_id] = rid
        self._user_to_room[opponent_id] = rid
        return room

    def get(self, rid: int) -> Optional[BattleRoom]:
        return self._rooms.get(rid)

    def for_user(self, user_id: int) -> Optional[BattleRoom]:
        rid = self._user_to_room.get(user_id)
        return self._rooms.get(rid) if rid else None

    def mark_started(self, room: BattleRoom, started: bool = True) -> None:
        room.started = started

    def set_message_id(self, room: BattleRoom, message_id: int) -> None:
        room.message_id = message_id

    def remove(self, room: BattleRoom) -> None:
        self._rooms.pop(room.id, None)
        self._user_to_room.pop(room.challenger_id, None)
        self._user_to_room.pop(room.opponent_id, None)

    def render_public(self, room: BattleRoom) -> str:
        status = "⏳ Waiting for both to accept…" if not room.started else "✅ Battle started!"
        return f"Room **#{room.id}** — {status}"

_manager: Optional[BattleManager] = None

def get_manager() -> BattleManager:
    global _manager
    if _manager is None:
        _manager = BattleManager()
    return _manager