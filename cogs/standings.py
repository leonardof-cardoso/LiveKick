"""Cog de classificacao: !tabela <competicao>."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import COMPETITIONS, settings
from services.football_service import FootballService
from services.standings_service import StandingsService
from utils.helpers import base_embed, normalize_competition, truncate


log = logging.getLogger("futebol24hrs.cogs.standings")


def _format_table(rows: list[dict]) -> str:
    if not rows:
        return "Tabela indisponivel para esta competicao."
    head = "`Pos  Time                    P  J   V  E  D   SG`"
    body = []
    for r in rows[:20]:
        team = (r.get("team") or "?")[:22].ljust(22)
        pos = str(r.get("position") or "?").rjust(2)
        pts = str(r.get("points") or 0).rjust(2)
        played = str(r.get("played") or 0).rjust(2)
        won = str(r.get("won") or 0).rjust(2)
        draw = str(r.get("draw") or 0).rjust(2)
        lost = str(r.get("lost") or 0).rjust(2)
        gd = str(r.get("gd") if r.get("gd") is not None else 0).rjust(3)
        body.append(f"`{pos}.  {team} {pts}  {played}  {won} {draw} {lost}  {gd}`")
    return head + "\n" + "\n".join(body)


class StandingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        football = getattr(bot, "football_service", None)
        if football is None:
            football = FootballService(bot.db)
            bot.football_service = football
        self.standings = StandingsService(bot.db, football)
        bot.standings_service = self.standings

        bot.scheduler.add_job(
            self._refresh,
            "interval",
            minutes=max(15, settings.STANDINGS_INTERVAL_MIN),
            id="standings_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    async def _refresh(self) -> None:
        for key, cfg in COMPETITIONS.items():
            if not cfg.get("fd_code"):
                continue
            try:
                await self.standings.get(key)
            except Exception:
                log.exception("Falha refresh standings %s", key)

    def _build_embed(self, comp_key: str, rows: list[dict]) -> discord.Embed:
        cfg = COMPETITIONS.get(comp_key) or {}
        title = f"{cfg.get('emoji', '')} Classificacao — {cfg.get('name', comp_key)}"
        if not rows:
            return base_embed(title, "Tabela indisponivel para esta competicao "
                                     "(pode requerer FOOTBALL_API_KEY ou nao ser fornecida pela fonte gratuita).")
        return base_embed(title, _format_table(rows))

    @commands.command(name="tabela", aliases=["classificacao", "standings"],
                      help="!tabela brasileirao | champions")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def tabela(self, ctx: commands.Context, *, competicao: Optional[str] = None) -> None:
        await ctx.typing()
        key = normalize_competition(competicao) or "brasileirao"
        rows = await self.standings.get(key)
        await ctx.send(embed=self._build_embed(key, rows))

    @app_commands.command(name="tabela", description="Classificacao das competicoes")
    @app_commands.describe(competicao="brasileirao | champions | libertadores | sulamericana")
    @app_commands.choices(competicao=[
        app_commands.Choice(name="Brasileirao", value="brasileirao"),
        app_commands.Choice(name="Champions League", value="champions"),
        app_commands.Choice(name="Libertadores", value="libertadores"),
        app_commands.Choice(name="Sul-Americana", value="sulamericana"),
    ])
    async def slash_tabela(self, interaction: discord.Interaction,
                           competicao: app_commands.Choice[str]) -> None:
        await interaction.response.defer(thinking=True)
        rows = await self.standings.get(competicao.value)
        await interaction.followup.send(embed=self._build_embed(competicao.value, rows))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StandingsCog(bot))
