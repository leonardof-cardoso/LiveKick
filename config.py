"""Configuracoes globais do bot, lidas de variaveis de ambiente / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
LOG_DIR = BASE_DIR / "logs"
CACHE_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

try:
    from dotenv import load_dotenv
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
except Exception:
    pass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")
    TIMEZONE: str = os.getenv("TIMEZONE", "America/Sao_Paulo")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "cache" / "futebol24.db"))

    FOOTBALL_API_KEY: str = os.getenv("FOOTBALL_API_KEY", "")
    FOOTBALL_API_BASE: str = os.getenv("FOOTBALL_API_BASE", "https://api.football-data.org/v4")
    SPORTSDB_BASE: str = os.getenv("SPORTSDB_BASE", "https://www.thesportsdb.com/api/v1/json/3")

    HTTP_TIMEOUT: float = float(os.getenv("HTTP_TIMEOUT", "10"))
    HTTP_RETRIES: int = _int("HTTP_RETRIES", 2)

    LIVE_INTERVAL_MIN: int = _int("LIVE_INTERVAL_MIN", 2)
    NEWS_INTERVAL_MIN: int = _int("NEWS_INTERVAL_MIN", 15)
    STANDINGS_INTERVAL_MIN: int = _int("STANDINGS_INTERVAL_MIN", 60)

    CACHE_TTL_LIVE: int = _int("CACHE_TTL_LIVE", 90)
    CACHE_TTL_FIXTURES: int = _int("CACHE_TTL_FIXTURES", 600)
    CACHE_TTL_STANDINGS: int = _int("CACHE_TTL_STANDINGS", 3600)
    CACHE_TTL_NEWS: int = _int("CACHE_TTL_NEWS", 600)

    EMBED_COLOR: int = int(os.getenv("EMBED_COLOR", "0x00A859"), 16)


COMPETITIONS = {
    "brasileirao": {
        "name": "Brasileirao Serie A",
        "fd_code": "BSA",
        "sportsdb_id": "4351",
        "emoji": "🇧🇷",
    },
    "libertadores": {
        "name": "CONMEBOL Libertadores",
        "fd_code": None,
        "sportsdb_id": "4480",
        "emoji": "🏆",
    },
    "sulamericana": {
        "name": "CONMEBOL Sul-Americana",
        "fd_code": None,
        "sportsdb_id": "4481",
        "emoji": "🥈",
    },
    "champions": {
        "name": "UEFA Champions League",
        "fd_code": "CL",
        "sportsdb_id": "4480",
        "emoji": "⭐",
    },
}

COMPETITION_ALIASES = {
    "brasileirao": "brasileirao",
    "brasileirão": "brasileirao",
    "br": "brasileirao",
    "serie-a": "brasileirao",
    "serie_a": "brasileirao",
    "libertadores": "libertadores",
    "liberta": "libertadores",
    "sulamericana": "sulamericana",
    "sul-americana": "sulamericana",
    "sula": "sulamericana",
    "champions": "champions",
    "ucl": "champions",
    "champions-league": "champions",
}

NEWS_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=futebol+brasileir%C3%A3o&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=libertadores&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=champions+league&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://ge.globo.com/rss/futebol.xml",
]


settings = Settings()
