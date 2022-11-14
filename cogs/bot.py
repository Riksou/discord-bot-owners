import discord
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners
from utils.context import MusicContext
from utils.exceptions import MusicError


class Bot(commands.Cog):

    def __init__(self, client: DiscordBotOwners) -> None:
        self.client = client

    """ Error handler. """

    @commands.Cog.listener()
    async def on_command_error(self, ctx: MusicContext, error: commands.CommandError):
        error = getattr(error, "original", error)

        if isinstance(error, (commands.CommandNotFound, discord.HTTPException, commands.CheckFailure)):
            return

        if isinstance(error, (commands.MissingRequiredArgument, commands.ArgumentParsingError, commands.BadArgument)):
            usage = f"{ctx.clean_prefix}{ctx.command.name} {ctx.command.usage}"
            await ctx.send(f"Incorrect usage. `{usage}`")

        elif isinstance(error, MusicError):
            await ctx.error(error.message)

        else:
            raise error


async def setup(client):
    await client.add_cog(Bot(client))
