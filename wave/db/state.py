"""Player state persistence mixin."""

from typing import Any, Dict, Optional


class StateMixin:
    """Player playback state persistence and retrieval."""

    def save_player_state(
        self,
        current_track_id: Optional[str] = None,
        queue_index: int = 0,
        time_pos: float = 0.0,
        volume: float = 80.0,
        autoplay: bool = True,
        repeat_mode: str = "OFF",
        shuffle: bool = False
    ) -> None:
        """Persist player playback state into singleton row id=1."""
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO player_state (id, current_track_id, current_queue_index, time_pos, volume, autoplay, repeat_mode, shuffle, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    current_track_id = excluded.current_track_id,
                    current_queue_index = excluded.current_queue_index,
                    time_pos = excluded.time_pos,
                    volume = excluded.volume,
                    autoplay = excluded.autoplay,
                    repeat_mode = excluded.repeat_mode,
                    shuffle = excluded.shuffle,
                    updated_at = CURRENT_TIMESTAMP;
            """, (current_track_id, queue_index, float(time_pos), float(volume), 1 if autoplay else 0, str(repeat_mode), 1 if shuffle else 0))

    def get_player_state(self) -> Dict[str, Any]:
        """Retrieve last saved player state. Returns sensible defaults if not set."""
        with self._connection() as conn:
            cursor = conn.cursor()
            ps_cols = self._get_columns(cursor, "player_state")
            if "autoplay" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN autoplay INTEGER DEFAULT 1;")
            if "repeat_mode" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN repeat_mode TEXT DEFAULT 'OFF';")
            if "shuffle" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN shuffle INTEGER DEFAULT 0;")
            cursor.execute("""
                SELECT current_track_id, current_queue_index, time_pos, volume, autoplay, repeat_mode, shuffle, updated_at
                FROM player_state WHERE id = 1;
            """)
            row = cursor.fetchone()
            if row:
                auto_val = True
                rep_val = "OFF"
                shuf_val = False
                try:
                    if "autoplay" in row.keys() and row["autoplay"] is not None:
                        auto_val = bool(row["autoplay"])
                except Exception:
                    pass
                try:
                    if "repeat_mode" in row.keys() and row["repeat_mode"]:
                        rep_val = str(row["repeat_mode"])
                except Exception:
                    pass
                try:
                    if "shuffle" in row.keys() and row["shuffle"] is not None:
                        shuf_val = bool(row["shuffle"])
                except Exception:
                    pass
                return {
                    "current_track_id": row["current_track_id"],
                    "queue_index": int(row["current_queue_index"] or 0),
                    "time_pos": float(row["time_pos"] or 0.0),
                    "volume": float(row["volume"] if row["volume"] is not None else 80.0),
                    "autoplay": auto_val,
                    "repeat_mode": rep_val,
                    "shuffle": shuf_val,
                    "updated_at": str(row["updated_at"]) if row["updated_at"] else None
                }
            return {
                "current_track_id": None,
                "queue_index": 0,
                "time_pos": 0.0,
                "volume": 80.0,
                "autoplay": True,
                "repeat_mode": "OFF",
                "shuffle": False,
                "updated_at": None
            }
