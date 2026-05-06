"""Wrapper async simples para SQLite usando aiosqlite.

Toda a aplicacao compartilha a mesma conexao (WAL ligado), o que reduz
significativamente o consumo de RAM e evita criacao repetida de cursores.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterable, Optional

import aiosqlite

from database.models import SCHEMA


log = logging.getLogger("futebol24hrs.db")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA temp_store=MEMORY")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        log.info("Banco SQLite pronto em %s", self.path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("DB nao inicializado")
        return self._conn

    # ------------------------------------------------------------------ cache
    async def cache_get(self, key: str) -> Optional[Any]:
        now = int(time.time())
        async with self.conn.execute(
            "SELECT payload, expires_at FROM api_cache WHERE cache_key=?",
            (key,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        payload, expires = row
        if expires < now:
            await self.conn.execute("DELETE FROM api_cache WHERE cache_key=?", (key,))
            await self.conn.commit()
            return None
        try:
            return json.loads(payload)
        except (TypeError, ValueError):
            return None

    async def cache_set(self, key: str, value: Any, ttl: int) -> None:
        expires = int(time.time()) + max(1, int(ttl))
        try:
            payload = json.dumps(value, default=str)
        except (TypeError, ValueError):
            log.debug("Valor nao serializavel para cache key=%s", key)
            return
        await self.conn.execute(
            "INSERT INTO api_cache(cache_key, payload, expires_at) VALUES(?,?,?) "
            "ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at",
            (key, payload, expires),
        )
        await self.conn.commit()

    async def cache_purge_expired(self) -> int:
        now = int(time.time())
        async with self.conn.execute(
            "DELETE FROM api_cache WHERE expires_at < ?", (now,)
        ) as cur:
            count = cur.rowcount
        await self.conn.commit()
        return count or 0

    # ----------------------------------------------------------- guild config
    async def set_alerts_channel(self, guild_id: int, channel_id: int) -> None:
        await self.conn.execute(
            "INSERT INTO guild_config(guild_id, alerts_channel) VALUES(?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET alerts_channel=excluded.alerts_channel",
            (guild_id, channel_id),
        )
        await self.conn.commit()

    async def get_alerts_channel(self, guild_id: int) -> Optional[int]:
        async with self.conn.execute(
            "SELECT alerts_channel FROM guild_config WHERE guild_id=?",
            (guild_id,),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row and row[0] else None

    async def all_alert_channels(self) -> Iterable[tuple[int, int]]:
        async with self.conn.execute(
            "SELECT guild_id, alerts_channel FROM guild_config WHERE alerts_channel IS NOT NULL"
        ) as cur:
            return list(await cur.fetchall())

    # -------------------------------------------------------- favorite teams
    async def add_favorite(self, guild_id: int, team: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO favorite_teams(guild_id, team_name, added_at) VALUES(?,?,?)",
            (guild_id, team.lower(), int(time.time())),
        )
        await self.conn.commit()

    async def remove_favorite(self, guild_id: int, team: str) -> None:
        await self.conn.execute(
            "DELETE FROM favorite_teams WHERE guild_id=? AND team_name=?",
            (guild_id, team.lower()),
        )
        await self.conn.commit()

    async def list_favorites(self, guild_id: int) -> list[str]:
        async with self.conn.execute(
            "SELECT team_name FROM favorite_teams WHERE guild_id=? ORDER BY added_at",
            (guild_id,),
        ) as cur:
            return [r[0] for r in await cur.fetchall()]

    # --------------------------------------------------------- sent alerts
    async def alert_already_sent(self, match_id: str, event_key: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM sent_alerts WHERE match_id=? AND event_key=?",
            (match_id, event_key),
        ) as cur:
            return (await cur.fetchone()) is not None

    async def mark_alert_sent(self, match_id: str, event_key: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO sent_alerts(match_id, event_key, sent_at) VALUES(?,?,?)",
            (match_id, event_key, int(time.time())),
        )
        await self.conn.commit()

    async def cleanup_alerts(self, older_than_seconds: int = 7 * 24 * 3600) -> int:
        cutoff = int(time.time()) - older_than_seconds
        async with self.conn.execute(
            "DELETE FROM sent_alerts WHERE sent_at < ?", (cutoff,)
        ) as cur:
            count = cur.rowcount
        await self.conn.commit()
        return count or 0
