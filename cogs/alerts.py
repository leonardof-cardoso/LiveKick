"""Cog de alertas automaticos.

Polling em intervalo configuravel:
  - inicio do jogo (status muda para LIVE/IN_PLAY)
  - gols (mudanca no placar)
  - intervalo (HT/PAUSED)
  - fim do jogo (FT/FINISHED)

Alertas sao deduplicados via tabela `sent_alerts`, e enviados apenas
para guilds que configuraram um canal com `!setalerts #canal`.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from config import settings
from services.football_service import FootballService
from utils.helpers import base_embed


log = logging.getLogger("futebol24hrs.cogs.alerts")


LIVE_STATUSES = {"IN_PLAY", "LIVE", "1H", "2H"}
HT_STATUSES = {"PAUSED", "HT"}
FT_STATUSES = {"FINISHED", "FT", "AET", "PEN"}


class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        football = getattr(bot, "football_service", None)
        if football is None:
            football = FootballService(bot.db)
            bot.football_service = football
        self.football = football

        # Snapshot em memoria do estado anterior dos jogos para detectar mudancas.
        # Mantemos somente o necessario para nao crescer indefinidamente.
        self._last_state: dict[str, dict] = {}

        bot.scheduler.add_job(
            self._tick,
            "interval",
            minutes=max(1, settings.LIVE_INTERVAL_MIN),
            id="alerts_tick",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        bot.scheduler.add_job(
            self._cleanup,
            "interval",
            hours=12,
            id="alerts_cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    async def _cleanup(self) -> None:
        try:
            removed = await self.bot.db.cleanup_alerts()
            cache = await self.bot.db.cache_purge_expired()
            if removed or cache:
                log.info("Limpeza: %d alertas, %d itens de cache.", removed, cache)
        except Exception:
            log.exception("Erro em cleanup")

        # Limita memoria do snapshot (apenas IDs ativos)
        if len(self._last_state) > 500:
            self._last_state.clear()

    async def _tick(self) -> None:
        """Polling principal: gera alertas com base nas mudancas de estado."""
        try:
            channels = await self.bot.db.all_alert_channels()
        except Exception:
            log.exception("Falha ao carregar canais de alerta")
            return
        if not channels:
            return

        try:
            matches = await self.football.all_matches()
        except Exception:
            log.exception("Falha ao buscar partidas no tick de alertas")
            return

        events: list[tuple[str, str, discord.Embed]] = []  # (match_id, key, embed)
        for m in matches:
            mid = m.get("id")
            if not mid:
                continue
            status = (m.get("status") or "").upper()
            score = (m.get("home_score"), m.get("away_score"))
            prev = self._last_state.get(mid)
            self._last_state[mid] = {"status": status, "score": score}

            home = m.get("home", "?")
            away = m.get("away", "?")
            comp = m.get("competition", "")
            base_title = f"{home} x {away}"

            if prev is None:
                # primeiro avistamento: somente alertamos se ja vivo agora
                if status in LIVE_STATUSES:
                    events.append((str(mid), "kickoff", base_embed(
                        f"🟢 Jogo iniciado: {base_title}",
                        f"{comp}\nPlacar: {score[0] or 0} x {score[1] or 0}")))
                continue

            prev_status = prev.get("status") or ""
            prev_score = prev.get("score") or (None, None)

            # Inicio
            if prev_status not in LIVE_STATUSES and status in LIVE_STATUSES:
                events.append((str(mid), "kickoff", base_embed(
                    f"🟢 Jogo iniciado: {base_title}", f"{comp}")))

            # Gol (qualquer alteracao no placar enquanto em jogo)
            if status in LIVE_STATUSES and prev_status in LIVE_STATUSES and score != prev_score:
                if score[0] is not None and score[1] is not None:
                    key = f"goal:{score[0]}-{score[1]}"
                    events.append((str(mid), key, base_embed(
                        f"⚽ GOL! {base_title}",
                        f"{comp}\nPlacar atual: **{score[0]} x {score[1]}**")))

            # Intervalo
            if prev_status not in HT_STATUSES and status in HT_STATUSES:
                events.append((str(mid), "halftime", base_embed(
                    f"⏸️ Intervalo: {base_title}",
                    f"{comp}\nPlacar: {score[0] or 0} x {score[1] or 0}")))

            # Fim
            if prev_status not in FT_STATUSES and status in FT_STATUSES:
                events.append((str(mid), "fulltime", base_embed(
                    f"⏹️ Fim de jogo: {base_title}",
                    f"{comp}\nResultado final: **{score[0] or 0} x {score[1] or 0}**")))

        if not events:
            return

        for match_id, key, embed in events:
            try:
                if await self.bot.db.alert_already_sent(match_id, key):
                    continue
            except Exception:
                log.exception("Falha alert_already_sent")
                continue

            for guild_id, channel_id in channels:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        channel = None
                if not channel or not isinstance(channel, discord.abc.Messageable):
                    continue
                try:
                    await channel.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException) as e:
                    log.warning("Falha ao enviar alerta no canal %s: %s", channel_id, e)
            try:
                await self.bot.db.mark_alert_sent(match_id, key)
            except Exception:
                log.exception("Falha mark_alert_sent")

    # -------- comandos de configuracao --------
    @commands.command(name="setalerts", aliases=["setalertas"],
                      help="Define o canal para alertas. Uso: !setalerts #canal")
    @commands.has_permissions(manage_guild=True)
    async def set_alerts(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        if not ctx.guild:
            await ctx.send("Use em um servidor.")
            return
        ch = channel or ctx.channel
        if not isinstance(ch, discord.TextChannel):
            await ctx.send("Selecione um canal de texto valido.")
            return
        await self.bot.db.set_alerts_channel(ctx.guild.id, ch.id)
        await ctx.send(f"✅ Canal de alertas definido: {ch.mention}")

    @commands.command(name="alerts", help="Mostra o canal de alertas atual.")
    async def alerts_status(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return
        cid = await self.bot.db.get_alerts_channel(ctx.guild.id)
        if not cid:
            await ctx.send("Nenhum canal configurado. Use `!setalerts #canal`.")
            return
        ch = self.bot.get_channel(cid)
        await ctx.send(f"📣 Alertas em: {ch.mention if ch else f'<#{cid}>'}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertsCog(bot))
