"""Helpers compartilhados: logging, formatadores, util de tempo."""
from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Optional

import discord

from config import LOG_DIR, settings, COMPETITION_ALIASES, COMPETITIONS


def setup_logging(level: str = "INFO") -> None:
    """Configura logger raiz com rotacao e baixo overhead."""
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    try:
        log_path = Path(LOG_DIR) / "bot.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception:
        pass

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def normalize_competition(value: Optional[str]) -> Optional[str]:
    """Aceita variacoes (brasileirão, ucl, sula...) e retorna chave canonica."""
    if not value:
        return None
    key = value.strip().lower().replace(" ", "-")
    if key in COMPETITIONS:
        return key
    return COMPETITION_ALIASES.get(key)


def fmt_local_time(dt_utc: Optional[datetime]) -> str:
    """Converte datetime UTC -> string local HH:MM (Brasilia por padrao)."""
    if not dt_utc:
        return "--:--"
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        local = dt_utc.astimezone(ZoneInfo(settings.TIMEZONE))
    except Exception:
        local = dt_utc.astimezone(timezone(timedelta(hours=-3)))
    return local.strftime("%H:%M")


def fmt_local_datetime(dt_utc: Optional[datetime]) -> str:
    if not dt_utc:
        return "--/-- --:--"
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        local = dt_utc.astimezone(ZoneInfo(settings.TIMEZONE))
    except Exception:
        local = dt_utc.astimezone(timezone(timedelta(hours=-3)))
    return local.strftime("%d/%m %H:%M")


def status_label(status: Optional[str]) -> str:
    if not status:
        return "Agendado"
    s = status.upper()
    if s in {"IN_PLAY", "LIVE", "1H", "2H"}:
        return "AO VIVO"
    if s in {"PAUSED", "HT"}:
        return "Intervalo"
    if s in {"FINISHED", "FT", "AET", "PEN"}:
        return "Encerrado"
    if s in {"SCHEDULED", "TIMED", "NS"}:
        return "Agendado"
    if s in {"POSTPONED", "PST"}:
        return "Adiado"
    if s in {"CANCELED", "CANCELLED"}:
        return "Cancelado"
    return s.title()


def base_embed(title: str, description: str = "", *, color: Optional[int] = None) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description or "",
        color=color if color is not None else settings.EMBED_COLOR,
    )
    embed.set_footer(text="Futebol24hrs • dados gratuitos: Football-Data / TheSportsDB")
    return embed


def chunked(it: Iterable, n: int):
    """Divide iteravel em pedacos de tamanho n (gerador)."""
    bucket = []
    for x in it:
        bucket.append(x)
        if len(bucket) >= n:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


def truncate(s: str, max_len: int = 1024) -> str:
    if not s:
        return ""
    return s if len(s) <= max_len else s[: max_len - 1] + "…"
