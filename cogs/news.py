"""Cog de noticias: !noticias [busca]."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import settings
from services.news_service import NewsService
from utils.helpers import base_embed, truncate


log = logging.getLogger("futebol24hrs.cogs.news")


class NewsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        football = getattr(bot, "football_service", None)
        if football is None:
            from services.football_service import FootballService
            football = FootballService(bot.db)
            bot.football_service = football
        self.news = NewsService(bot.db, football)
        bot.news_service = self.news

        bot.scheduler.add_job(
            self._refresh_news,
            "interval",
            minutes=max(5, settings.NEWS_INTERVAL_MIN),
            id="news_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    async def _refresh_news(self) -> None:
        try:
            await self.news.latest(limit=10)
        except Exception:
            log.exception("Falha ao atualizar cache de noticias")

    def _build_embed(self, items: list[dict], query: Optional[str]) -> discord.Embed:
        title = "📰 Noticias de futebol"
        if query:
            title += f" — {query}"
        if not items:
            return base_embed(title, "Nenhuma noticia disponivel agora.")
        embed = base_embed(title)
        for item in items[:8]:
            name = truncate(item.get("title") or "(sem titulo)", 250)
            link = item.get("link") or ""
            source = truncate(item.get("source") or "", 100)
            value = f"[Abrir noticia]({link})\n*{source}*"
            embed.add_field(name=name, value=truncate(value, 1024), inline=False)
        return embed

    @commands.command(name="noticias", aliases=["news"], help="Noticias recentes do futebol.")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def noticias(self, ctx: commands.Context, *, busca: Optional[str] = None) -> None:
        await ctx.typing()
        items = await self.news.latest(limit=8, query=busca)
        await ctx.send(embed=self._build_embed(items, busca))

    @app_commands.command(name="noticias", description="Noticias recentes do futebol")
    @app_commands.describe(busca="Filtro opcional (ex: flamengo)")
    async def slash_noticias(self, interaction: discord.Interaction, busca: Optional[str] = None) -> None:
        await interaction.response.defer(thinking=True)
        items = await self.news.latest(limit=8, query=busca)
        await interaction.followup.send(embed=self._build_embed(items, busca))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NewsCog(bot))
