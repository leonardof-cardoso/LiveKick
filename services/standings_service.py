"""Servico de classificacoes (delegacao para FootballService + cache).

Football-Data fornece tabelas para Brasileirao e Champions. Para
Libertadores/Sul-Americana o Football-Data nao tem standings na free tier;
nesses casos retornamos lista vazia e o cog informa indisponibilidade.
"""
from __future__ import annotations

import logging
from typing import Optional

from config import COMPETITIONS, settings
from database.db import Database
from services.football_service import FootballService


log = logging.getLogger("futebol24hrs.standings")


class StandingsService:
    def __init__(self, db: Database, football: FootballService) -> None:
        self.db = db
        self.football = football

    async def get(self, comp_key: str) -> list[dict]:
        cfg = COMPETITIONS.get(comp_key)
        if not cfg:
            return []
        cache_key = f"standings:{comp_key}"
        cached = await self.db.cache_get(cache_key)
        if cached is not None:
            return cached

        rows: list[dict] = []
        if cfg.get("fd_code") and settings.FOOTBALL_API_KEY:
            try:
                rows = await self.football.fd_standings(cfg["fd_code"])
            except Exception:
                log.exception("Falha ao buscar standings %s", comp_key)
                rows = []

        await self.db.cache_set(cache_key, rows, settings.CACHE_TTL_STANDINGS)
        return rows

    async def find_team_position(self, comp_key: str, team_name: str) -> Optional[dict]:
        rows = await self.get(comp_key)
        norm = team_name.lower()
        for row in rows:
            if norm in (row.get("team") or "").lower():
                return row
        return None
