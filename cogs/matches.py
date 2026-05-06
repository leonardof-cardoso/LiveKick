"""Cog de partidas: !jogos, !aovivo, !proximos, !ondeassistir.

Tambem registra equivalentes em slash commands.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import COMPETITIONS, settings
from services.football_service import FootballService
from services.broadcast_service import BroadcastService
from utils.helpers import (
    base_embed,
    fmt_local_time,
    fmt_local_datetime,
    normalize_competition,
    status_label,
    truncate,
)


log = logging.getLogger("futebol24hrs.cogs.matches")

MAX_PER_EMBED = 12


def _fmt_match_line(m: dict) -> str:
    home = m.get("home", "?")
    away = m.get("away", "?")
    status = (m.get("status") or "").upper()
    label = status_label(status)
    score_h = m.get("home_score")
    score_a = m.get("away_score")
    has_score = score_h is not None and score_a is not None

    if status in {"IN_PLAY", "PAUSED", "LIVE", "1H", "2H", "HT"}:
        minute = m.get("minute") or label
        score = f"{score_h or 0} x {score_a or 0}"
        return f"🔴 **{home} {score} {away}** • `{minute}`"
    if status in {"FINISHED", "FT", "AET", "PEN"}:
        return f"⏹️ {home} {score_h} x {score_a} {away} • `Encerrado`"
    if has_score:
        return f"• {home} {score_h} x {score_a} {away} • `{label}`"
    try:
        utc = m.get("utc_date")
        dt = datetime.fromisoformat(utc.replace("Z", "+00:00")) if utc else None
    except (ValueError, AttributeError):
        dt = None
    when = fmt_local_time(dt) if dt else label
    return f"🕒 `{when}` {home} x {away}"


class MatchesCog(commands.Cog):
    """Comandos de partidas."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.football = FootballService(bot.db)
        self.broadcast = BroadcastService(self.football)
        bot.football_service = self.football
        bot.broadcast_service = self.broadcast

    async def cog_unload(self) -> None:
        await self.football.close()

    # ---------------- helpers comuns ----------------
    async def _send_grouped(self, ctx_or_inter, title: str, matches: list[dict], empty_msg: str):
        if not matches:
            embed = base_embed(title, empty_msg)
            await self._reply(ctx_or_inter, embed=embed)
            return

        groups: dict[str, list[dict]] = {}
        for m in matches:
            comp = m.get("competition") or "Outros"
            groups.setdefault(comp, []).append(m)

        embed = base_embed(title)
        for comp, items in groups.items():
            chunk = items[:MAX_PER_EMBED]
            lines = "\n".join(_fmt_match_line(m) for m in chunk)
            embed.add_field(name=truncate(comp, 256), value=truncate(lines, 1024) or "—", inline=False)
        await self._reply(ctx_or_inter, embed=embed)

    @staticmethod
    async def _reply(ctx_or_inter, *, embed: discord.Embed):
        if isinstance(ctx_or_inter, discord.Interaction):
            if ctx_or_inter.response.is_done():
                await ctx_or_inter.followup.send(embed=embed)
            else:
                await ctx_or_inter.response.send_message(embed=embed)
        else:
            await ctx_or_inter.send(embed=embed)

    # -------------------------- !jogos --------------------------
    @commands.command(name="jogos", help="Mostra os jogos do dia.")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def jogos(self, ctx: commands.Context) -> None:
        await ctx.typing()
        matches = await self.football.matches_today()
        await self._send_grouped(ctx, "⚽ Jogos de hoje", matches,
                                 "Nenhum jogo programado para hoje nas competicoes monitoradas.")

    @app_commands.command(name="jogos", description="Jogos de hoje das principais competicoes")
    async def slash_jogos(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        matches = await self.football.matches_today()
        await self._send_grouped(interaction, "⚽ Jogos de hoje", matches,
                                 "Nenhum jogo programado para hoje.")

    # ------------------------- !ao vivo -------------------------
    @commands.command(name="aovivo", aliases=["ao_vivo", "live"], help="Apenas jogos ao vivo.")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def aovivo(self, ctx: commands.Context) -> None:
        await ctx.typing()
        matches = await self.football.live_matches()
        await self._send_grouped(ctx, "🔴 Jogos AO VIVO", matches, "Nenhum jogo ao vivo no momento.")

    @app_commands.command(name="aovivo", description="Jogos ao vivo agora")
    async def slash_aovivo(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        matches = await self.football.live_matches()
        await self._send_grouped(interaction, "🔴 Jogos AO VIVO", matches, "Nenhum jogo ao vivo no momento.")

    # ------------------------- !proximos ------------------------
    @commands.command(name="proximos", help="Proximos jogos (ate 7 dias).")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def proximos(self, ctx: commands.Context) -> None:
        await ctx.typing()
        matches = await self.football.upcoming_matches(days=7)
        title = "📅 Proximos jogos (7 dias)"
        await self._send_grouped(ctx, title, matches[:30], "Sem jogos agendados nos proximos 7 dias.")

    @app_commands.command(name="proximos", description="Proximos jogos (7 dias)")
    async def slash_proximos(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        matches = await self.football.upcoming_matches(days=7)
        await self._send_grouped(interaction, "📅 Proximos jogos (7 dias)",
                                 matches[:30], "Sem jogos agendados.")

    # ----------------------- !ondeassistir ----------------------
    @commands.command(name="ondeassistir", aliases=["onde", "tv"],
                      help="Onde assistir: !ondeassistir <time1> x <time2>")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def ondeassistir(self, ctx: commands.Context, *, jogo: Optional[str] = None) -> None:
        await ctx.typing()
        if not jogo or " x " not in jogo.lower():
            await ctx.send("Uso: `!ondeassistir Flamengo x Palmeiras`")
            return
        parts = [p.strip() for p in jogo.lower().replace(" X ", " x ").split(" x ", 1)]
        if len(parts) != 2:
            await ctx.send("Uso: `!ondeassistir Flamengo x Palmeiras`")
            return
        home, away = parts
        info = await self.broadcast.lookup(home, away)
        embed = base_embed(f"📺 {home.title()} x {away.title()}", f"**Transmissao:** {info}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MatchesCog(bot))
