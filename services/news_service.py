"""Servico de noticias via RSS (Google News e GE).

Usa feedparser, mantido leve e sem dependencias adicionais. Resultados
sao cacheados no SQLite para evitar requests excessivos.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Iterable, Optional

import httpx

from config import NEWS_RSS_FEEDS, settings
from database.db import Database


log = logging.getLogger("futebol24hrs.news")

_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return _HTML_TAG.sub("", text).strip()


class NewsService:
    def __init__(self, db: Database, football_service) -> None:
        self.db = db
        self.football = football_service  # reuse de cliente HTTP

    async def _fetch_feed(self, url: str) -> list[dict]:
        client = await self.football._ensure_client()
        try:
            resp = await client.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            log.warning("Falha ao baixar feed %s: %s", url, e)
            return []
        if resp.status_code >= 400:
            return []

        try:
            import feedparser
        except ImportError:
            log.error("feedparser nao instalado")
            return []

        parsed = feedparser.parse(resp.content)
        items: list[dict] = []
        for entry in parsed.entries[:15]:
            items.append({
                "title": _strip_html(getattr(entry, "title", "")),
                "link": getattr(entry, "link", ""),
                "published": getattr(entry, "published", ""),
                "source": getattr(getattr(entry, "source", {}), "title", "") or url,
                "summary": _strip_html(getattr(entry, "summary", ""))[:280],
            })
        return items

    async def latest(self, limit: int = 8, query: Optional[str] = None) -> list[dict]:
        cache_key = f"news:{query or 'all'}:{limit}"
        cached = await self.db.cache_get(cache_key)
        if cached is not None:
            return cached

        feeds: Iterable[str]
        if query:
            q = query.replace(" ", "+")
            feeds = [
                f"https://news.google.com/rss/search?q={q}+futebol&hl=pt-BR&gl=BR&ceid=BR:pt-419",
            ]
        else:
            feeds = NEWS_RSS_FEEDS

        results = await asyncio.gather(*[self._fetch_feed(u) for u in feeds], return_exceptions=True)
        merged: list[dict] = []
        seen_links: set[str] = set()
        for r in results:
            if isinstance(r, Exception):
                continue
            for item in r:
                link = item.get("link") or ""
                if not link or link in seen_links or not item.get("title"):
                    continue
                seen_links.add(link)
                merged.append(item)

        merged = merged[:limit]
        await self.db.cache_set(cache_key, merged, settings.CACHE_TTL_NEWS)
        return merged
