"""Servico de transmissoes (onde assistir).

TheSportsDB expoe `strTVStation` em alguns eventos. Tambem mantemos um
mapa local com canais comuns no Brasil como fallback informativo.
"""
from __future__ import annotations

import logging
from typing import Optional

from services.football_service import FootballService


log = logging.getLogger("futebol24hrs.broadcast")


DEFAULT_BROADCASTS = {
    "brasileirao": "Globo / SporTV / Premiere / Amazon Prime",
    "libertadores": "SBT / ESPN / Paramount+",
    "sulamericana": "ESPN / Paramount+",
    "champions": "TNT Sports / HBO Max / SBT (final)",
}


class BroadcastService:
    def __init__(self, football: FootballService) -> None:
        self.football = football

    async def lookup(self, home: str, away: str, comp_key: Optional[str] = None) -> str:
        """Tenta achar transmissao para o jogo home x away."""
        try:
            team = await self.football.sdb_search_team(home)
        except Exception:
            log.exception("Falha sdb_search_team")
            team = None

        if team:
            tid = team.get("idTeam")
            if tid:
                try:
                    nxt = await self.football.sdb_team_next_events(tid)
                except Exception:
                    nxt = []
                a_norm = away.lower()
                for ev in nxt or []:
                    other = (ev.get("away") or "").lower()
                    if a_norm and a_norm in other:
                        if ev.get("broadcast"):
                            return str(ev["broadcast"])
                        break

        if comp_key and comp_key in DEFAULT_BROADCASTS:
            return DEFAULT_BROADCASTS[comp_key] + " (referencia)"
        return "Transmissao nao encontrada"
