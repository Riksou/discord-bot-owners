import math
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners


def get_exp_needed(current_level: int) -> int:
    return int(math.log(4 * current_level) ** 5 * 10)


class AutoRolesView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Announcements", style=discord.ButtonStyle.blurple, custom_id="persisten:announcements")
    async def announcements(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        announcements_role = interaction.guild.get_role(interaction.client.config["role_id"]["announcements"])

        if announcements_role in interaction.user.roles:
            await interaction.user.remove_roles(announcements_role)
            await interaction.response.send_message(
                "You will no longer be pinged when an announcement is posted.", ephemeral=True
            )
        else:
            await interaction.user.add_roles(announcements_role)
            await interaction.response.send_message(
                "You will now be pinged when an announcement is posted.", ephemeral=True
            )

    @discord.ui.button(label="Events", style=discord.ButtonStyle.blurple, custom_id="persisten:events")
    async def events(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        events_role = interaction.guild.get_role(interaction.client.config["role_id"]["events"])

        if events_role in interaction.user.roles:
            await interaction.user.remove_roles(events_role)
            await interaction.response.send_message(
                "You will no longer be pinged when an event is starting.", ephemeral=True
            )
        else:
            await interaction.user.add_roles(events_role)
            await interaction.response.send_message(
                "You will now be pinged when an event is starting.", ephemeral=True
            )

    @discord.ui.button(label="Polls", style=discord.ButtonStyle.blurple, custom_id="persisten:polls")
    async def polls(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        polls_role = interaction.guild.get_role(interaction.client.config["role_id"]["polls"])

        if polls_role in interaction.user.roles:
            await interaction.user.remove_roles(polls_role)
            await interaction.response.send_message(
                "You will no longer be pinged when a poll is posted.", ephemeral=True
            )
        else:
            await interaction.user.add_roles(polls_role)
            await interaction.response.send_message(
                "You will now be pinged when a poll is posted.", ephemeral=True
            )


class SuggestModal(discord.ui.Modal, title="Suggestion"):

    suggestion = discord.ui.TextInput(
        label="Suggestion",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        placeholder="Type your suggestion here..."
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        suggestion_embed = discord.Embed(
            title="Suggestion",
            description=self.suggestion.value,
            color=interaction.client.color,
            timestamp=discord.utils.utcnow()
        )

        suggestion_embed.set_footer(text=f"{interaction.user}", icon_url=interaction.user.avatar.url)

        suggestion_channel = interaction.guild.get_channel(interaction.client.config["channel_id"]["suggestions"])

        message = await suggestion_channel.send(embed=suggestion_embed)
        await message.add_reaction("<:check:1046183403877302364>")
        await message.add_reaction("<:cross:1046183402358964236>")

        await interaction.response.send_message("Your suggestion has been submitted.", ephemeral=True)


class General(commands.Cog):
    """The general cog, managing different features of the bot."""

    def __init__(self, client: DiscordBotOwners):
        self.client = client

    async def cog_load(self) -> None:
        self.client.loop.create_task(self.after_ready())

    async def after_ready(self) -> None:
        await self.client.wait_until_ready()

        guild_data = await self.client.mongo.fetch_guild_data()
        if guild_data["auto_roles_message_id"] is None:
            return

        self.client.add_view(AutoRolesView(), message_id=guild_data["auto_roles_message_id"])

    async def send_auto_roles_view(self, channel, **kwargs) -> None:
        auto_roles_embed = discord.Embed(
            title="Auto Roles",
            description="Select the roles you want to get by clicking the buttons below.",
            color=self.client.color
        )

        msg = await channel.send(embed=auto_roles_embed, view=AutoRolesView(), **kwargs)
        await self.client.mongo.update_guild_data_document(
            {"$set": {"auto_roles_message_id": msg.id, "auto_roles_channel_id": channel.id}}
        )
        await self.client.reload_extension("cogs.general")

    """ Leveling system. """

    EXP_CHOICES = [1, 2, 3]
    EXP_WEIGHTS = [0.70, 0.15, 0.15]

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

    """ Suggestions system. """

    @app_commands.command(name="suggest")
    async def suggest(self, interaction: discord.Interaction):
        """Suggest something for the server."""
        await interaction.response.send_modal(SuggestModal())


async def setup(client):
    await client.add_cog(General(client))
