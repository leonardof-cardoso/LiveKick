"""Schema SQL e dataclasses leves usadas pelo bot.

Mantemos o esquema em um unico modulo para minimizar overhead de import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id      INTEGER PRIMARY KEY,
    alerts_channel INTEGER,
    timezone      TEXT
);

CREATE TABLE IF NOT EXISTS favorite_teams (
    guild_id      INTEGER NOT NULL,
    team_name     TEXT    NOT NULL,
    added_at      INTEGER NOT NULL,
    PRIMARY KEY (guild_id, team_name)
);

CREATE TABLE IF NOT EXISTS sent_alerts (
    match_id      TEXT    NOT NULL,
    event_key     TEXT    NOT NULL,
    sent_at       INTEGER NOT NULL,
    PRIMARY KEY (match_id, event_key)
);

CREATE TABLE IF NOT EXISTS api_cache (
    cache_key     TEXT    PRIMARY KEY,
    payload       TEXT    NOT NULL,
    expires_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_expiry ON api_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_alerts_sent_at ON sent_alerts(sent_at);
"""


@dataclass(slots=True)
class GuildConfig:
    guild_id: int
    alerts_channel: Optional[int] = None
    timezone: Optional[str] = None


@dataclass(slots=True)
class FavoriteTeam:
    guild_id: int
    team_name: str
    added_at: int
