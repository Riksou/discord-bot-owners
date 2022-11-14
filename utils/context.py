import discord
from discord.ext import commands


class MusicContext(commands.Context):

    async def info(self, message: str) -> discord.Message:
        return await self.send(embed=discord.Embed(description=message, color=self.bot.color))

    async def success(self, message: str) -> discord.Message:
        return await self.send(embed=discord.Embed(description=message, color=self.bot.green))

    async def error(self, message: str) -> discord.Message:
        return await self.send(embed=discord.Embed(description=message, color=self.bot.red))
