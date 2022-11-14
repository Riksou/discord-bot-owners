import math
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners


def get_exp_needed(current_level: int) -> int:
    return int(math.log(4 * current_level) ** 5 * 10)


class Leveling(commands.Cog):
    """The cog to manage the leveling system."""

    EXP_CHOICES = [1, 2, 3]
    EXP_WEIGHTS = [0.70, 0.15, 0.15]

    def __init__(self, client: DiscordBotOwners):
        self.client = client

    async def _update_exp(self, member: discord.Member, exp_won: int) -> None:
        guild_member = await self.client.mongo.fetch_guild_member(member.id)

        current_level = guild_member["level"]
        current_exp = guild_member["exp"]
        exp_needed = get_exp_needed(current_level)

        if exp_needed <= (current_exp + exp_won):
            new_level = current_level + 1
            await self.client.mongo.update_guild_member_document(
                member.id, {"$set": {"exp": exp_won, "level": new_level}}
            )

            if new_level == 5:
                promotions_role = member.guild.get_role(self.client.config["role_id"]["promotions"])
                await member.add_roles(promotions_role)
        else:
            await self.client.mongo.update_guild_member_document(member.id, {"$inc": {"exp": exp_won}})

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return

        if message.author.id == self.client.user.id:
            return

        exp_amount = random.choices(self.EXP_CHOICES, self.EXP_WEIGHTS)[0]
        await self._update_exp(message.author, exp_amount)

    @app_commands.command(name="level")
    async def level(self, interaction: discord.Interaction, user: Optional[discord.User]):
        """Check your current level and exp or someone else's stats."""
        if user is None:
            user = interaction.user

        guild_member = await self.client.mongo.fetch_guild_member(user.id)
        level = guild_member["level"]
        current_exp = guild_member["exp"]
        exp_needed = get_exp_needed(level)

        level_embed = discord.Embed(
            title=f"{user}",
            description=f"{user.mention} is currently level **{level}** (**{current_exp}**/**{exp_needed}**).",
            color=self.client.color,
            timestamp=discord.utils.utcnow()
        )

        await interaction.response.send_message(embed=level_embed)


async def setup(client):
    await client.add_cog(Leveling(client))
