"""
Futebol24hrs - Bot Discord para Futebol Brasileiro e Europeu.

Entrypoint principal: cria a instancia do bot, carrega as cogs,
inicializa o banco SQLite e o agendador APScheduler.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import signal

import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from database.db import Database
from utils.helpers import setup_logging


log = logging.getLogger("futebol24hrs")


class Futebol24Bot(commands.Bot):
    """Bot principal. Mantem instancias compartilhadas (db, scheduler, http)."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = False

        super().__init__(
            command_prefix=settings.COMMAND_PREFIX,
            intents=intents,
            help_command=commands.DefaultHelpCommand(no_category="Comandos"),
            case_insensitive=True,
        )

        self.db: Database = Database(settings.DB_PATH)
        self.scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

    async def setup_hook(self) -> None:
        """Hook executado uma vez antes do bot conectar."""
        log.info("Inicializando banco de dados...")
        await self.db.init()

        log.info("Carregando cogs...")
        for cog_name in (
            "cogs.matches",
            "cogs.news",
            "cogs.standings",
            "cogs.teams",
            "cogs.alerts",
        ):
            try:
                await self.load_extension(cog_name)
                log.info("Cog carregada: %s", cog_name)
            except Exception:
                log.exception("Falha ao carregar cog %s", cog_name)

        if not self.scheduler.running:
            self.scheduler.start()
            log.info("Scheduler iniciado.")

        try:
            synced = await self.tree.sync()
            log.info("Slash commands sincronizados: %d", len(synced))
        except Exception:
            log.exception("Falha ao sincronizar slash commands")

    async def on_ready(self) -> None:
        log.info("Bot conectado como %s (id=%s)", self.user, getattr(self.user, "id", "?"))
        await self.change_presence(
            activity=discord.Game(name=f"{settings.COMMAND_PREFIX}jogos | futebol 24h")
        )

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Uso incorreto. Veja `{settings.COMMAND_PREFIX}help {ctx.command}`.")
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Calma! Tente novamente em {error.retry_after:.0f}s.")
            return
        log.exception("Erro no comando %s: %s", ctx.command, error)
        try:
            await ctx.send("Ocorreu um erro processando o comando. Os logs foram registrados.")
        except discord.DiscordException:
            pass

    async def close(self) -> None:
        log.info("Encerrando bot...")
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        except Exception:
            log.exception("Erro ao parar scheduler")
        try:
            await self.db.close()
        except Exception:
            log.exception("Erro ao fechar banco")
        await super().close()


async def _run() -> None:
    setup_logging(settings.LOG_LEVEL)

    if not settings.DISCORD_TOKEN:
        log.error("DISCORD_TOKEN nao configurado. Defina no arquivo .env.")
        sys.exit(1)

    bot = Futebol24Bot()

    loop = asyncio.get_running_loop()

    def _graceful_stop(*_args) -> None:
        log.info("Sinal de termino recebido.")
        loop.create_task(bot.close())

    if os.name != "nt":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _graceful_stop)
            except NotImplementedError:
                pass

    backoff = 5
    while True:
        try:
            await bot.start(settings.DISCORD_TOKEN, reconnect=True)
            break
        except (discord.LoginFailure,) as e:
            log.error("Token invalido: %s", e)
            return
        except (discord.HTTPException, discord.GatewayNotFound, ConnectionError, OSError) as e:
            log.error("Erro de conexao com Discord (%s). Tentando novamente em %ds...", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)
        except Exception:
            log.exception("Erro inesperado no loop principal. Reiniciando em %ds...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
