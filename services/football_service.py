"""Servico unificado para dados de futebol.

Consome duas fontes gratuitas:
  - Football-Data.org (requer API key gratuita) -> Brasileirao + Champions
  - TheSportsDB (sem chave)                     -> Libertadores, Sul-Americana, fallback

Cada metodo aplica cache em SQLite para reduzir requests/RAM. Todas as
chamadas HTTP usam um unico httpx.AsyncClient compartilhado e tratam
erros de rede silenciosamente (o sistema continua rodando se uma API cair).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx

from config import settings, COMPETITIONS
from database.db import Database


log = logging.getLogger("futebol24hrs.football")


class FootballService:
    """Cliente HTTP compartilhado + acesso a Football-Data e TheSportsDB."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- HTTP base
    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client and not self._client.is_closed:
            return self._client
        async with self._lock:
            if self._client and not self._client.is_closed:
                return self._client
            timeout = httpx.Timeout(settings.HTTP_TIMEOUT, connect=5.0)
            limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                headers={"User-Agent": "Futebol24hrs/1.0"},
                http2=False,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get_json(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        retries: Optional[int] = None,
    ) -> Optional[Any]:
        """GET com retry, backoff e tratamento de rate limit/timeout."""
        client = await self._ensure_client()
        attempts = (retries if retries is not None else settings.HTTP_RETRIES) + 1
        delay = 1.5
        for i in range(attempts):
            try:
                resp = await client.get(url, headers=headers, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                log.warning("HTTP erro tentativa %d/%d em %s: %s", i + 1, attempts, url, e)
                if i + 1 < attempts:
                    await asyncio.sleep(delay)
                    delay *= 2
                continue
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", "5"))
                log.warning("Rate limit em %s, aguardando %ss", url, wait)
                await asyncio.sleep(min(wait, 30))
                continue
            if resp.status_code >= 500:
                if i + 1 < attempts:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                return None
            if resp.status_code >= 400:
                log.warning("HTTP %s em %s", resp.status_code, url)
                return None
            try:
                return resp.json()
            except ValueError:
                return None
        return None

    # --------------------------------------------------------- Football-Data
    async def _fd_get(self, path: str, params: Optional[dict] = None) -> Optional[Any]:
        if not settings.FOOTBALL_API_KEY:
            return None
        return await self._get_json(
            f"{settings.FOOTBALL_API_BASE}{path}",
            headers={"X-Auth-Token": settings.FOOTBALL_API_KEY},
            params=params,
        )

    @staticmethod
    def _fd_match_to_dict(m: dict) -> dict:
        score = m.get("score") or {}
        full = score.get("fullTime") or {}
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        comp = m.get("competition") or {}
        return {
            "id": str(m.get("id")),
            "competition": comp.get("name") or comp.get("code") or "",
            "competition_code": comp.get("code") or "",
            "utc_date": m.get("utcDate"),
            "status": m.get("status"),
            "home": home.get("name") or home.get("shortName") or "?",
            "away": away.get("name") or away.get("shortName") or "?",
            "home_score": full.get("home"),
            "away_score": full.get("away"),
            "minute": m.get("minute"),
            "stage": m.get("stage"),
            "source": "football-data",
        }

    async def fd_matches(
        self,
        competition_code: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        data = await self._fd_get(f"/competitions/{competition_code}/matches", params=params)
        if not data:
            return []
        return [self._fd_match_to_dict(m) for m in data.get("matches", [])]

    async def fd_standings(self, competition_code: str) -> list[dict]:
        data = await self._fd_get(f"/competitions/{competition_code}/standings")
        if not data:
            return []
        out: list[dict] = []
        for tab in data.get("standings", []):
            if tab.get("type") != "TOTAL":
                continue
            for row in tab.get("table", []):
                team = row.get("team") or {}
                out.append({
                    "position": row.get("position"),
                    "team": team.get("name") or team.get("shortName") or "?",
                    "played": row.get("playedGames"),
                    "won": row.get("won"),
                    "draw": row.get("draw"),
                    "lost": row.get("lost"),
                    "gf": row.get("goalsFor"),
                    "ga": row.get("goalsAgainst"),
                    "gd": row.get("goalDifference"),
                    "points": row.get("points"),
                })
        return out

    # ---------------------------------------------------------- TheSportsDB
    @staticmethod
    def _sdb_event_to_dict(ev: dict) -> dict:
        date = ev.get("dateEvent") or ""
        time_ = ev.get("strTime") or "00:00:00"
        utc_date = None
        try:
            naive = datetime.strptime(f"{date} {time_[:5]}", "%Y-%m-%d %H:%M")
            utc_date = naive.replace(tzinfo=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass
        score_h = ev.get("intHomeScore")
        score_a = ev.get("intAwayScore")
        status = (ev.get("strStatus") or "").upper()
        if not status:
            status = "FINISHED" if score_h is not None and score_h != "" else "SCHEDULED"
        return {
            "id": str(ev.get("idEvent")),
            "competition": ev.get("strLeague") or "",
            "competition_code": ev.get("idLeague") or "",
            "utc_date": utc_date,
            "status": status,
            "home": ev.get("strHomeTeam") or "?",
            "away": ev.get("strAwayTeam") or "?",
            "home_score": int(score_h) if score_h not in (None, "") else None,
            "away_score": int(score_a) if score_a not in (None, "") else None,
            "minute": ev.get("strProgress"),
            "stage": ev.get("strRound"),
            "venue": ev.get("strVenue"),
            "broadcast": ev.get("strTVStation"),
            "source": "thesportsdb",
        }

    async def sdb_next_events(self, league_id: str) -> list[dict]:
        data = await self._get_json(f"{settings.SPORTSDB_BASE}/eventsnextleague.php", params={"id": league_id})
        if not data:
            return []
        return [self._sdb_event_to_dict(e) for e in (data.get("events") or [])]

    async def sdb_past_events(self, league_id: str) -> list[dict]:
        data = await self._get_json(f"{settings.SPORTSDB_BASE}/eventspastleague.php", params={"id": league_id})
        if not data:
            return []
        return [self._sdb_event_to_dict(e) for e in (data.get("events") or [])]

    async def sdb_search_team(self, name: str) -> Optional[dict]:
        data = await self._get_json(f"{settings.SPORTSDB_BASE}/searchteams.php", params={"t": name})
        if not data or not data.get("teams"):
            return None
        return data["teams"][0]

    async def sdb_team_next_events(self, team_id: str) -> list[dict]:
        data = await self._get_json(f"{settings.SPORTSDB_BASE}/eventsnext.php", params={"id": team_id})
        if not data:
            return []
        return [self._sdb_event_to_dict(e) for e in (data.get("events") or [])]

    async def sdb_team_past_events(self, team_id: str) -> list[dict]:
        data = await self._get_json(f"{settings.SPORTSDB_BASE}/eventslast.php", params={"id": team_id})
        if not data:
            return []
        return [self._sdb_event_to_dict(e) for e in (data.get("results") or [])]

    # ------------------------------------------------------- API alto-nivel
    async def matches_for_competition(self, comp_key: str) -> list[dict]:
        """Retorna jogos recentes/futuros para uma competicao com cache."""
        cfg = COMPETITIONS.get(comp_key)
        if not cfg:
            return []
        cache_key = f"matches:{comp_key}"
        cached = await self.db.cache_get(cache_key)
        if cached is not None:
            return cached

        results: list[dict] = []
        if cfg.get("fd_code") and settings.FOOTBALL_API_KEY:
            today = datetime.now(timezone.utc).date()
            df = (today - timedelta(days=2)).isoformat()
            dt = (today + timedelta(days=14)).isoformat()
            results = await self.fd_matches(cfg["fd_code"], df, dt)
        if not results and cfg.get("sportsdb_id"):
            nxt = await self.sdb_next_events(cfg["sportsdb_id"])
            past = await self.sdb_past_events(cfg["sportsdb_id"])
            results = (past or []) + (nxt or [])

        await self.db.cache_set(cache_key, results, settings.CACHE_TTL_FIXTURES)
        return results

    async def all_matches(self) -> list[dict]:
        out: list[dict] = []
        for key in COMPETITIONS:
            try:
                out.extend(await self.matches_for_competition(key))
            except Exception:
                log.exception("Falha ao buscar matches de %s", key)
        return out

    async def live_matches(self) -> list[dict]:
        """Filtra apenas partidas em andamento. Cache curto."""
        cache_key = "matches:live"
        cached = await self.db.cache_get(cache_key)
        if cached is not None:
            return cached

        all_m = await self.all_matches()
        live = [m for m in all_m if (m.get("status") or "").upper() in
                {"IN_PLAY", "PAUSED", "LIVE", "1H", "2H", "HT"}]
        await self.db.cache_set(cache_key, live, settings.CACHE_TTL_LIVE)
        return live

    async def matches_today(self) -> list[dict]:
        all_m = await self.all_matches()
        today = datetime.now(timezone.utc).date()
        out: list[dict] = []
        for m in all_m:
            utc_date = m.get("utc_date")
            if not utc_date:
                continue
            try:
                d = datetime.fromisoformat(utc_date.replace("Z", "+00:00")).date()
            except ValueError:
                continue
            if d == today:
                out.append(m)
        out.sort(key=lambda x: x.get("utc_date") or "")
        return out

    async def upcoming_matches(self, days: int = 7) -> list[dict]:
        all_m = await self.all_matches()
        now = datetime.now(timezone.utc)
        limit = now + timedelta(days=days)
        out: list[dict] = []
        for m in all_m:
            utc_date = m.get("utc_date")
            if not utc_date:
                continue
            try:
                dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
            except ValueError:
                continue
            if now <= dt <= limit and (m.get("status") or "").upper() in {"SCHEDULED", "TIMED", "NS", ""}:
                out.append(m)
        out.sort(key=lambda x: x.get("utc_date") or "")
        return out
