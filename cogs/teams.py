"""Cog de times: !time <nome>, !favoritos."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import COMPETITIONS
from services.football_service import FootballService
from services.standings_service import StandingsService
from utils.helpers import base_embed, fmt_local_datetime, truncate
from datetime import datetime


log = logging.getLogger("futebol24hrs.cogs.teams")


def _fmt_event(ev: dict) -> str:
    home = ev.get("home", "?")
    away = ev.get("away", "?")
    sh = ev.get("home_score")
    sa = ev.get("away_score")
    try:
        utc = ev.get("utc_date")
        dt = datetime.fromisoformat(utc.replace("Z", "+00:00")) if utc else None
    except (ValueError, AttributeError):
        dt = None
    when = fmt_local_datetime(dt) if dt else "—"
    if sh is not None and sa is not None:
        return f"`{when}` {home} {sh} x {sa} {away}"
    return f"`{when}` {home} x {away}"


class TeamsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        football = getattr(bot, "football_service", None)
        if football is None:
            football = FootballService(bot.db)
            bot.football_service = football
        self.football = football
        self.standings: StandingsService = getattr(bot, "standings_service", None) or \
            StandingsService(bot.db, football)

    async def _build_team_embed(self, name: str) -> discord.Embed:
        team = await self.football.sdb_search_team(name)
        if not team:
            return base_embed(f"Time: {name}", "Time nao encontrado em TheSportsDB.")
        team_id = team.get("idTeam")
        team_name = team.get("strTeam") or name
        country = team.get("strCountry") or ""
        league = team.get("strLeague") or ""

        nxt = await self.football.sdb_team_next_events(team_id) if team_id else []
        last = await self.football.sdb_team_past_events(team_id) if team_id else []

        embed = base_embed(f"⚽ {team_name}", f"{country} • {league}".strip(" •"))
        if team.get("strBadge"):
            embed.set_thumbnail(url=team["strBadge"])

        nxt_text = "\n".join(_fmt_event(e) for e in nxt[:5]) or "—"
        last_text = "\n".join(_fmt_event(e) for e in last[:5]) or "—"
        embed.add_field(name="📅 Proximos jogos", value=truncate(nxt_text, 1024), inline=False)
        embed.add_field(name="📊 Ultimos resultados", value=truncate(last_text, 1024), inline=False)

        for key in COMPETITIONS:
            row = await self.standings.find_team_position(key, team_name)
            if row:
                pos = row.get("position")
                pts = row.get("points")
                embed.add_field(
                    name=f"🏆 Posicao em {COMPETITIONS[key]['name']}",
                    value=f"{pos}º lugar • {pts} pontos • J:{row.get('played')} "
                          f"V:{row.get('won')} E:{row.get('draw')} D:{row.get('lost')}",
                    inline=False,
                )
                break

        return embed

    @commands.command(name="time", aliases=["team"], help="Info do time: !time Flamengo")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def time_(self, ctx: commands.Context, *, nome: Optional[str] = None) -> None:
        if not nome:
            await ctx.send("Uso: `!time <nome do time>`")
            return
        await ctx.typing()
        embed = await self._build_team_embed(nome)
        await ctx.send(embed=embed)

    @app_commands.command(name="time", description="Informacoes de um time")
    @app_commands.describe(nome="Nome do time (ex: Flamengo)")
    async def slash_time(self, interaction: discord.Interaction, nome: str) -> None:
        await interaction.response.defer(thinking=True)
        embed = await self._build_team_embed(nome)
        await interaction.followup.send(embed=embed)

    # ---------------- favoritos ----------------
    @commands.group(name="favoritos", invoke_without_command=True,
                    help="Gerencia times favoritos: !favoritos add|remove|list <time>")
    async def favoritos(self, ctx: commands.Context) -> None:
        await ctx.invoke(self.fav_list)

    @favoritos.command(name="add")
    async def fav_add(self, ctx: commands.Context, *, nome: str) -> None:
        if not ctx.guild:
            await ctx.send("Use em um servidor.")
            return
        await self.bot.db.add_favorite(ctx.guild.id, nome)
        await ctx.send(f"⭐ {nome} adicionado aos favoritos.")

    @favoritos.command(name="remove", aliases=["rm"])
    async def fav_remove(self, ctx: commands.Context, *, nome: str) -> None:
        if not ctx.guild:
            return
        await self.bot.db.remove_favorite(ctx.guild.id, nome)
        await ctx.send(f"❌ {nome} removido dos favoritos.")

    @favoritos.command(name="list", aliases=["ls"])
    async def fav_list(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return
        items = await self.bot.db.list_favorites(ctx.guild.id)
        if not items:
            await ctx.send("Nenhum time favorito configurado. Use `!favoritos add <time>`.")
            return
        await ctx.send(embed=base_embed("⭐ Times favoritos", "\n".join(f"• {t.title()}" for t in items)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamsCog(bot))
