import discord
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners


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


class AutoRoles(commands.Cog):
    """The cog to manage the auto roles system."""

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
        await self.client.reload_extension("cogs.auto_roles")


async def setup(client):
    await client.add_cog(AutoRoles(client))
