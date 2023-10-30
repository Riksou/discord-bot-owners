from __future__ import annotations

import json
import os
from typing import Optional, TYPE_CHECKING

import aiohttp
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from cogs.mongodb import MongoDB

os.environ["JISHAKU_HIDE"] = "true"

with open("config.json", "r") as fic:
    config = dict(json.load(fic))


class DiscordBotOwners(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            chunk_guilds_at_startup=True,
            case_insensitive=True,
            activity=discord.Game(f"Helping bot developers!"),
            owner_id=212844004889329664,
        )

        self.remove_command("help")

        self.config = config

        self.aiosession = None
        self.verified_promotions_webhook = None

        self.color = 0x5865F2
        self.green = 0x04D277
        self.red = 0xE24C4B

    @property
    def mongo(self) -> Optional[MongoDB]:
        return self.get_cog("MongoDB")

    """ Ready actions. """

    async def ready_actions(self) -> None:
        await self.wait_until_ready()

        print(f"Ready: {self.user} (ID: {self.user.id}).")

    """ Setup actions. """

    async def setup_hook(self) -> None:
        self.loop.create_task(self.ready_actions())

        self.aiosession = aiohttp.ClientSession(loop=self.loop)
        self.verified_promotions_webhook = discord.Webhook.from_url(
            self.config["verified_promotions_webhook_url"], session=self.aiosession
        )

        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")

        await self.load_extension("jishaku")

        await self.sync_guild()

    async def sync_guild(self) -> None:
        guild = discord.Object(id=self.config["guild_id"])
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


if __name__ == "__main__":
    bot = DiscordBotOwners()
    bot.run(config["bot_token"])
