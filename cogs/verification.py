import discord
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners

""" Verification views. """


class AcceptedBotOwnerVerificationSelect(discord.ui.Select):

    def __init__(self, client: DiscordBotOwners, member: discord.Member, message: discord.Message):
        self.member = member
        self.message = message

        guild = client.get_guild(client.config["guild_id"])
        roles = [guild.get_role(d) for d in client.config["role_id"]["bot_owner_roles"]]

        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles]
        super().__init__(placeholder="Select a role...", options=options)

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        verified_bot_developer_role = interaction.guild.get_role(
            interaction.client.config["role_id"]["verified_bot_developer"]
        )

        await self.member.add_roles(role, verified_bot_developer_role)

        await interaction.client.mongo.update_guild_member_document(
            self.member.id, {"$set": {"verification_pending": False}}
        )
        await interaction.client.mongo.update_guild_data_document(
            {"$unset": {f"pending_verification_message_ids.{self.message.id}": ""}}
        )

        await interaction.response.send_message(
            f"You accepted the verification for {self.member.mention}.", ephemeral=True
        )


class DeniedBotOwnerVerificationModal(discord.ui.Modal, title="Deny Verification"):

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        max_length=1024
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = self.message.embeds[0]

        embed.set_field_at(5, name="Status", value="Denied.")
        embed.add_field(name="Reason", value=self.reason.value)
        embed.colour = interaction.client.red
        await self.message.edit(embed=embed, view=None)

        guild_data = await interaction.client.mongo.fetch_guild_data()

        user_id = guild_data["pending_verification_message_ids"][str(self.message.id)]
        member = interaction.guild.get_member(user_id)

        await interaction.client.mongo.update_guild_member_document(user_id, {"$set": {"verification_pending": False}})
        await interaction.client.mongo.update_guild_data_document(
            {"$unset": {f"pending_verification_message_ids.{interaction.message.id}": ""}}
        )

        await interaction.response.send_message(
            f"You have denied the verification request of <@{user_id}>.", ephemeral=True
        )

        if member is not None:
            denied_embed = discord.Embed(
                title="Verification Denied",
                description="Your verification to enter Discord Bot Owners has been denied.",
                color=interaction.client.color,
                timestamp=discord.utils.utcnow()
            )

            denied_embed.add_field(name="Reason", value=self.reason.value)

            try:
                await member.send(embed=denied_embed)
            except discord.HTTPException:
                pass


class PendingVerificationView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="persisten:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_data = await interaction.client.mongo.fetch_guild_data()

        user_id = guild_data["pending_verification_message_ids"][str(interaction.message.id)]
        member = interaction.guild.get_member(user_id)

        embed = interaction.message.embeds[0]

        if member is None:
            embed.set_field_at(5, name="Status", value="User left.")
            await interaction.message.edit(embed=embed, view=None)
            return await interaction.response.send_message("The user left the server.")

        embed.set_field_at(5, name="Status", value="Accepted.")
        embed.colour = interaction.client.green
        await interaction.message.edit(embed=embed, view=None)

        view = discord.ui.View()
        view.add_item(AcceptedBotOwnerVerificationSelect(interaction.client, member, interaction.message))
        await interaction.response.send_message(view=view, ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, custom_id="persisten:deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(DeniedBotOwnerVerificationModal(interaction.message))


class BotOwnerModal(discord.ui.Modal, title="Apply as a Bot Owner"):

    application_id = discord.ui.TextInput(
        label="Bot ID",
        style=discord.TextStyle.short,
        max_length=1024
    )

    oauth_url = discord.ui.TextInput(
        label="OAuth URL",
        style=discord.TextStyle.short,
        max_length=1024
    )

    support_server_invite = discord.ui.TextInput(
        label="Support Server Invite URL",
        style=discord.TextStyle.short,
        max_length=1024
    )

    guild_count = discord.ui.TextInput(
        label="Guild Count",
        style=discord.TextStyle.short,
        max_length=1024
    )

    ownership_proof = discord.ui.TextInput(
        label="Proof of Ownership",
        style=discord.TextStyle.paragraph,
        placeholder="Show us a Discord Developer Portal screenshot with you owning the bot",
        max_length=1024
    )

    async def on_submit(self, interaction: discord.Interaction):
        verification_embed = discord.Embed(
            title="Bot Owner Verification Request",
            description=f"{interaction.user.mention} ({interaction.user}) is willing to enter the server.",
            color=interaction.client.color,
            timestamp=discord.utils.utcnow()
        )

        verification_embed.add_field(name="Application ID", value=self.application_id.value)
        verification_embed.add_field(name="Guild Count", value=self.guild_count.value)
        verification_embed.add_field(name="Support Server Invite", value=self.support_server_invite.value)
        verification_embed.add_field(name="OAuth URL", value=self.oauth_url.value, inline=False)
        verification_embed.add_field(name="Proof of Ownership", value=self.ownership_proof.value, inline=False)
        verification_embed.add_field(name="Status", value="Pending", inline=False)

        verification_embed.set_thumbnail(url=interaction.user.avatar.url)

        verification_requests_channel = interaction.guild.get_channel(
            interaction.client.config["channel_id"]["verification_requests"]
        )
        pending_verification_message_id = await verification_requests_channel.send(
            embed=verification_embed, view=PendingVerificationView()
        )

        await interaction.client.mongo.update_guild_member_document(
            interaction.user.id, {"$set": {"verification_pending": True}}
        )
        await interaction.client.mongo.update_guild_data_document(
            {"$set": {f"pending_verification_message_ids.{pending_verification_message_id.id}": interaction.user.id}}
        )

        await interaction.response.send_message(
            "Thanks for your request, please wait while we review your application.", ephemeral=True
        )


class VerificationView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Bot Owner", style=discord.ButtonStyle.blurple, custom_id="persisten:bot_owner")
    async def bot_owner(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_member = await interaction.client.mongo.fetch_guild_member(interaction.user.id)
        if guild_member["verification_pending"] is True:
            return await interaction.response.send_message(
                "Your verification request is already pending.", ephemeral=True
            )

        await interaction.response.send_modal(BotOwnerModal())

    @discord.ui.button(label="Library Developer", style=discord.ButtonStyle.blurple, custom_id="persisten:lib_dev")
    async def library_developer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("This option is currently being worked on.", ephemeral=True)


class Verification(commands.Cog):
    """The cog to manage the verification system."""

    def __init__(self, client: DiscordBotOwners):
        self.client = client

    async def cog_load(self) -> None:
        self.client.loop.create_task(self.after_ready())

    async def after_ready(self) -> None:
        await self.client.wait_until_ready()

        guild_data = await self.client.mongo.fetch_guild_data()
        if guild_data["verification_message_id"] is None:
            return

        self.client.add_view(VerificationView(), message_id=guild_data["verification_message_id"])

        for message_id in guild_data["pending_verification_message_ids"].keys():
            self.client.add_view(PendingVerificationView(), message_id=int(message_id))

    async def send_verification_view(self, channel, **kwargs) -> None:
        verification_embed = discord.Embed(
            title="Verification",
            description="Select a way of verifying yourself to enter Discord Bot Owners.\n\n"
                        "Remember that you need to own a verified Discord bot if you want to apply as a Discord bot "
                        "owner.",
            color=self.client.color
        )

        msg = await channel.send(embed=verification_embed, view=VerificationView(), **kwargs)
        await self.client.mongo.update_guild_data_document(
            {"$set": {"verification_message_id": msg.id, "verification_channel_id": channel.id}}
        )
        await self.client.reload_extension("cogs.verification")


async def setup(client):
    await client.add_cog(Verification(client))
