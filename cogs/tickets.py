import io

import chat_exporter
import discord
from discord import app_commands
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners


async def create_ticket(
    interaction: discord.Interaction, category: str, stars: str = None
) -> None:
    guild_data = await interaction.client.mongo.fetch_guild_data()
    if category in guild_data["tickets"]:
        current_ticket_id = guild_data["tickets"][category].get(
            str(interaction.user.id)
        )
        if current_ticket_id is not None:
            return await interaction.response.send_message(
                f"You already have a ticket opened in this category, <#{current_ticket_id}>.",
                ephemeral=True,
            )

    if stars is not None and stars not in {"1", "2", "3"}:
        return await interaction.response.send_message(
            "The number of requested stars must be either 1, 2 or 3.", ephemeral=True
        )

    await interaction.response.send_message(
        "Your ticket is being created...", ephemeral=True
    )

    tickets_category = interaction.guild.get_channel(
        interaction.client.config["category_id"]["tickets"]
    )

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(
            read_messages=False
        ),
        interaction.user: discord.PermissionOverwrite(read_messages=True),
    }
    ticket_name = f"-{interaction.user.name}-{interaction.user.discriminator}"

    if stars is not None:
        category_manager_role = interaction.guild.get_role(
            interaction.client.config["role_id"][f"{category.lower()}_developer"][
                "manager"
            ]
        )
        overwrites[category_manager_role] = discord.PermissionOverwrite(
            read_messages=True, manage_messages=True
        )
        ticket_name = (
            f"{interaction.client.config['tickets'][category][2]}" + ticket_name
        )
    else:
        ticket_name = f"support" + ticket_name

    ticket_channel = await interaction.guild.create_text_channel(
        ticket_name, overwrites=overwrites, category=tickets_category
    )

    await interaction.client.mongo.update_guild_data_document(
        {"$set": {f"tickets.{category}.{interaction.user.id}": ticket_channel.id}}
    )

    ticket_embed = discord.Embed(
        title=f"Ticket",
        description=f"Welcome {interaction.user.mention} to Discord Bot Owner's ticket system.\n\n"
        f"Please wait for {'a manager' if stars is not None else 'an administrator'} to handle your "
        f"ticket.",
        color=interaction.client.color,
        timestamp=discord.utils.utcnow(),
    )

    if stars is not None:
        ticket_embed.add_field(name="Category", value=category, inline=False)
        ticket_embed.add_field(name="Stars", value=stars, inline=False)

    ticket_embed.set_footer(
        text="Discord Bot Owners", icon_url=interaction.client.user.display_avatar
    )

    await ticket_channel.send(embed=ticket_embed)
    fake_ping = await ticket_channel.send(f"{interaction.user.mention}")
    await fake_ping.delete()

    await interaction.edit_original_response(
        content=f"Your ticket has been created, {ticket_channel.mention}."
    )


""" Tickets view. """


class TicketsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Support",
        emoji="❓",
        style=discord.ButtonStyle.blurple,
        custom_id="persisten:support",
    )
    async def support(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await create_ticket(interaction, "Support")


class Tickets(commands.Cog):
    """The cog to manage tickets."""

    def __init__(self, client: DiscordBotOwners):
        self.client = client

    async def cog_load(self) -> None:
        self.client.loop.create_task(self.after_ready())

    async def after_ready(self) -> None:
        await self.client.wait_until_ready()

        guild_data = await self.client.mongo.fetch_guild_data()
        if guild_data["tickets_message_id"] is None:
            return

        self.client.add_view(TicketsView(), message_id=guild_data["tickets_message_id"])

    async def send_tickets_view(self, channel, **kwargs) -> None:
        tickets_embed = discord.Embed(
            title="Create a ticket",
            description="Select the category you are willing to create a ticket about using the buttons below.",
            color=self.client.color,
        )

        msg = await channel.send(embed=tickets_embed, view=TicketsView(), **kwargs)
        await self.client.mongo.update_guild_data_document(
            {"$set": {"tickets_message_id": msg.id, "tickets_channel_id": channel.id}}
        )
        await self.client.reload_extension("cogs.tickets")

    """ Tickets commands. """

    @app_commands.command(name="close")
    @app_commands.default_permissions()
    async def close(self, interaction: discord.Interaction):
        """Close a ticket."""
        if (
            interaction.channel.category_id
            != self.client.config["category_id"]["tickets"]
        ):
            return await interaction.response.send_message(
                "This channel is not a ticket.", ephemeral=True
            )

        if (
            interaction.user.get_role(self.client.config["role_id"]["manager"]) is None
            and interaction.user.guild_permissions.administrator is False
        ):
            return await interaction.response.send_message(
                content="You can't do that.", ephemeral=True
            )

        await interaction.response.send_message("This ticket will soon be closed.")

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            )
        }
        await interaction.channel.edit(overwrites=overwrites)

        guild_data = await self.client.mongo.fetch_guild_data()

        user_id = None
        category = None
        for ticket_category, tickets in guild_data["tickets"].items():
            for usr_id, channel_id in tickets.items():
                if channel_id == interaction.channel.id:
                    user_id = int(usr_id)
                    category = ticket_category
                    break

            if user_id is not None:
                break

        if user_id is None:
            # Why are we here. Shouldn't be possible.
            return

        try:
            await self.client.mongo.update_guild_data_document(
                {"$unset": {f"tickets.{category}.{user_id}": ""}}
            )
        except KeyError:
            # It's a race condition if we're here.
            pass

        transcript = None
        try:
            raw_transcript = await chat_exporter.export(interaction.channel)
            transcript = discord.File(
                io.BytesIO(raw_transcript.encode()),
                filename=f"transcript-{interaction.channel.id}.html",
            )
        except Exception:
            pass

        await interaction.channel.delete()

        logs_channel = interaction.guild.get_channel(
            self.client.config["channel_id"]["ticket_logs"]
        )

        user = interaction.guild.get_member(user_id)
        user_msg = f"**User**: <@{user}>\n"
        if user is not None:
            user_msg = f"**User**: <@{user.id}> / {user.name}#{user.discriminator}\n"

        closer = interaction.user
        embed_log = discord.Embed(
            title="Ticket",
            description=f"{user_msg}"
            f"**Closed by**: {closer.mention} / {closer.name}#{closer.discriminator}\n"
            f"**Category**: {category}\n"
            f"**Transcript**: *see attachments*\n",
            color=self.client.color,
            timestamp=discord.utils.utcnow(),
        )

        if transcript is not None:
            await logs_channel.send(embed=embed_log, file=transcript)
        else:
            await logs_channel.send(embed=embed_log)


async def setup(client):
    await client.add_cog(Tickets(client))
