import asyncio
import datetime
import random
import string
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners

""" Verification views. """


async def accept_verification(interaction: discord.Interaction, member: discord.Member,
                              message: discord.Message) -> None:
    await interaction.client.mongo.update_guild_member_document(
        member.id, {"$set": {"verification_pending": False, "verification_cooldown": None}}
    )
    await interaction.client.mongo.update_guild_data_document(
        {"$unset": {f"pending_verification_message_ids.{message.id}": ""}}
    )

    embed = message.embeds[0]

    embed.set_field_at(len(embed.fields) - 1, name="Status", value="Accepted.")
    embed.colour = interaction.client.green
    await message.edit(embed=embed, view=None)

    await interaction.response.send_message(f"You accepted the verification for {member.mention}.", ephemeral=True)

    general_channel = interaction.guild.get_channel(interaction.client.config["channel_id"]["general"])
    await general_channel.send(f"Welcome {member.mention} to Discord Bot Owners!")

    accepted_embed = discord.Embed(
        title="Verification Accepted",
        description="Your verification to enter Discord Bot Owners has been accepted.",
        color=interaction.client.color,
        timestamp=discord.utils.utcnow()
    )

    try:
        await member.send(embed=accepted_embed)
    except discord.HTTPException:
        pass


async def is_on_cooldown(interaction: discord.Interaction) -> bool:
    guild_member = await interaction.client.mongo.fetch_guild_member(interaction.user.id)
    if guild_member["verification_pending"] is True:
        await interaction.response.send_message(
            "Your verification request is already pending.", ephemeral=True
        )
        return True

    now = datetime.datetime.now()
    cooldown = guild_member["verification_cooldown"]
    if cooldown is not None and cooldown > now:
        remaining = discord.utils.format_dt(cooldown, "R")
        await interaction.response.send_message(
            f"You are on cooldown for the verification system, please try again {remaining}.", ephemeral=True
        )
        return True

    return False


async def apply_verification_submit_actions(interaction: discord.Interaction,
                                            verification_embed: discord.Embed) -> None:
    verification_requests_channel = interaction.guild.get_channel(
        interaction.client.config["channel_id"]["verification_requests"]
    )
    pending_verification_message_id = await verification_requests_channel.send(
        embed=verification_embed, view=PendingVerificationView()
    )

    cooldown = datetime.datetime.now() + datetime.timedelta(hours=1)
    await interaction.client.mongo.update_guild_member_document(
        interaction.user.id,
        {"$set": {"verification_pending": True, "verification_cooldown": cooldown}}
    )
    await interaction.client.mongo.update_guild_data_document(
        {"$set": {f"pending_verification_message_ids.{pending_verification_message_id.id}": interaction.user.id}}
    )

    await interaction.response.send_message(
        "Thanks for your request, please wait while we review your application.", ephemeral=True
    )


class AcceptedBotOwnerVerificationSelect(discord.ui.Select):

    def __init__(self, client: DiscordBotOwners, member: discord.Member, message: discord.Message):
        self.member = member
        self.message = message

        guild = client.get_guild(client.config["guild_id"])
        roles = [guild.get_role(int(d)) for d in client.config["role_id"]["bot_owner_roles"]]

        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles]
        super().__init__(placeholder="Select a role...", options=options)

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        verified_bot_developer_role = interaction.guild.get_role(
            interaction.client.config["role_id"]["verified_bot_developer"]
        )
        verified_member = interaction.guild.get_role(interaction.client.config["role_id"]["verified_member"])

        await self.member.add_roles(role, verified_bot_developer_role, verified_member)

        await accept_verification(interaction, self.member, self.message)


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

        embed.set_field_at(len(embed.fields) - 1, name="Status", value="Denied.")
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
            embed.set_field_at(len(embed.fields) - 1, name="Status", value="User left.")
            await interaction.message.edit(embed=embed, view=None)
            await interaction.client.mongo.update_guild_member_document(
                member.id, {"$set": {"verification_pending": False}}
            )
            return await interaction.response.send_message("The user left the server.", ephemeral=True)

        if len(embed.fields) == 5:
            view = discord.ui.View()
            view.add_item(AcceptedBotOwnerVerificationSelect(interaction.client, member, interaction.message))
            await interaction.response.send_message(view=view, ephemeral=True)
        else:
            library_developer = interaction.guild.get_role(interaction.client.config["role_id"]["library_developer"])
            verified_member = interaction.guild.get_role(interaction.client.config["role_id"]["verified_member"])

            await interaction.user.add_roles(library_developer, verified_member)

            await accept_verification(interaction, member, interaction.message)

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

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Thank you for completing this modal, you now have 5 minutes to show a proof of you owning the bot. We "
            "highly recommend you to send a screenshot of the Discord Developer Portal showing you owning the bot.\n\n"
            "**Send the screenshot in the bot's DMs.**",
            ephemeral=True
        )

        def check(m: discord.Message):
            return interaction.user.id == m.author.id and m.guild is None and len(m.attachments) > 0

        try:
            msg: discord.Message = await interaction.client.wait_for("message", timeout=300.0, check=check)
        except asyncio.TimeoutError:
            return await interaction.followup.send(
                "You did not send any proof of you owning the bot, aborting the verification.", ephemeral=True
            )

        try:
            await interaction.user.send("The verification request has been sent.")
        except discord.HTTPException:
            pass

        verification_embed = discord.Embed(
            title="Bot Owner Verification Request",
            description=f"{interaction.user.mention} ({interaction.user}) is wanting to enter the server.",
            color=interaction.client.color,
            timestamp=discord.utils.utcnow()
        )

        verification_embed.add_field(name="Application ID", value=self.application_id.value)
        verification_embed.add_field(name="Guild Count", value=self.guild_count.value)
        verification_embed.add_field(name="Support Server Invite", value=self.support_server_invite.value)
        verification_embed.add_field(name="OAuth URL", value=self.oauth_url.value, inline=False)
        verification_embed.add_field(name="Status", value="Pending", inline=False)

        verification_embed.set_thumbnail(url=interaction.user.display_avatar)

        verification_embed.set_image(url=msg.attachments[0].url)

        await apply_verification_submit_actions(interaction, verification_embed)


class LibraryDeveloperModal(discord.ui.Modal, title="Apply as a Library Developer"):

    name = discord.ui.TextInput(
        label="Library's Name",
        style=discord.TextStyle.short,
        max_length=1024
    )

    github_link = discord.ui.TextInput(
        label="Library's GitHub link",
        style=discord.TextStyle.short,
        max_length=1024
    )

    support_server_invite = discord.ui.TextInput(
        label="Library's Support Server Invite URL",
        style=discord.TextStyle.short,
        max_length=1024
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        verification_embed = discord.Embed(
            title="Library Developer Verification Request",
            description=f"{interaction.user.mention} ({interaction.user}) is wanting to enter the server.",
            color=interaction.client.color,
            timestamp=discord.utils.utcnow()
        )

        verification_embed.add_field(name="Library Name", value=self.name.value, inline=False)
        verification_embed.add_field(name="GitHub Link", value=self.github_link.value, inline=False)
        verification_embed.add_field(name="Support Server Invite", value=self.support_server_invite.value, inline=False)
        verification_embed.add_field(name="Status", value="Pending", inline=False)

        verification_embed.set_thumbnail(url=interaction.user.display_avatar)

        await apply_verification_submit_actions(interaction, verification_embed)


class BotTeamModal(discord.ui.Modal, title="Apply as a Bot Team Member"):

    generator_user_id = discord.ui.TextInput(
        label="Code Owner's ID",
        style=discord.TextStyle.short,
        placeholder="The ID of the user who gave you the code."
    )

    code = discord.ui.TextInput(
        label="Code",
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            user_id = int(self.generator_user_id.value)
        except ValueError:
            return await interaction.response.send_message("You must input a valid user ID.", ephemeral=True)

        guild_member = await interaction.client.mongo.fetch_guild_member(user_id)

        if self.code.value not in guild_member["verification_codes"]:
            return await interaction.response.send_message("You have entered an invalid code.", ephemeral=True)

        if guild_member["verification_codes"][self.code.value] is not None:
            return await interaction.response.send_message(
                "The code you have entered has already been used.", ephemeral=True
            )

        await interaction.client.mongo.update_guild_member_document(
            interaction.user.id,
            {"$set": {"verification_join_code": self.code.value, "verification_join_inviter": user_id}}
        )
        await interaction.client.mongo.update_guild_member_document(
            user_id, {"$set": {f"verification_codes.{self.code.value}": interaction.user.id}}
        )

        bot_team_role = interaction.guild.get_role(interaction.client.config["role_id"]["bot_team_member"])
        verified_member = interaction.guild.get_role(interaction.client.config["role_id"]["verified_member"])

        await interaction.response.send_message(
            "You have successfully verified yourself as a bot team member.", ephemeral=True
        )

        await interaction.user.add_roles(bot_team_role, verified_member)


class VerificationView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Bot Owner", style=discord.ButtonStyle.blurple, custom_id="persisten:bot_owner")
    async def bot_owner(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await is_on_cooldown(interaction) is True:
            return

        await interaction.response.send_modal(BotOwnerModal())

    @discord.ui.button(label="Library Developer", style=discord.ButtonStyle.blurple, custom_id="persisten:lib_dev")
    async def library_developer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await is_on_cooldown(interaction) is True:
            return

        await interaction.response.send_modal(LibraryDeveloperModal())

    @discord.ui.button(label="Bot Team Member", style=discord.ButtonStyle.blurple, custom_id="persisten:bot_team")
    async def bot_team(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(BotTeamModal())


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

    """ Verification with code commands. """

    @app_commands.command(name="codes")
    async def codes(self, interaction: discord.Interaction):
        """Show the codes you own to invite members from your bot team."""
        if interaction.user.get_role(self.client.config["role_id"]["verified_bot_developer"]) is None:
            return await interaction.response.send_message(
                "You must be a verified bot owner to use this command.", ephemeral=True
            )

        guild_member = await self.client.mongo.fetch_guild_member(interaction.user.id)

        total_codes = 0
        for role in interaction.user.roles:
            role_codes = self.client.config["role_id"]["bot_owner_roles"].get(str(role.id), 0)
            total_codes += role_codes

        if len(guild_member["verification_codes"]) < total_codes:
            new_codes = total_codes - len(guild_member["verification_codes"])
            for x in range(new_codes):
                characters = string.ascii_letters + string.digits
                code = "".join(random.choice(characters) for _ in range(6))
                guild_member["verification_codes"][code] = None

            await self.client.mongo.update_guild_member_document(
                interaction.user.id, {"$set": {"verification_codes": guild_member["verification_codes"]}}
            )

        description = ""
        for code, user_id in guild_member["verification_codes"].items():
            member = interaction.guild.get_member(user_id)
            member_formatted = "Unused"
            if member is not None:
                member_formatted = f"{member.mention} ({member})"
            description += f"`{code}` - {member_formatted}\n"

        if len(description) == 0:
            description = "You currently aren't qualified for any staff codes. Staff codes will be automatically " \
                          "unlocked when your bot reaches more servers."
        else:
            description = "Invite members from your bot team using the following code(s):\n\n" + description

        codes_embed = discord.Embed(
            title="Codes",
            description=description,
            color=self.client.color
        )

        await interaction.response.send_message(embed=codes_embed, ephemeral=True)

    """ Team commands. """

    team_group = app_commands.Group(name="team", description="Manage your team on the server.")

    @team_group.command(name="remove")
    async def team_remove(self, interaction: discord.Interaction, user: discord.Member):
        """Remove a member of your bot team from this server."""
        guild_member = await self.client.mongo.fetch_guild_member(interaction.user.id)
        if user.id not in guild_member["verification_codes"].values():
            return await interaction.response.send_message("You did not invite this user.", ephemeral=True)

        await user.kick(reason=f"Removed by {interaction.user} ({interaction.user.id}), from their bot team.")
        await interaction.response.send_message(
            f"You have successfully removed {user.mention} from your team.", ephemeral=True
        )

    @team_group.command(name="view")
    async def team_view(self, interaction: discord.Interaction, user: Optional[discord.Member]):
        """View the team of a bot owner in this server."""
        if user.get_role(self.client.config["role_id"]["verified_bot_developer"]) is None:
            return await interaction.response.send_message(
                "The user you provided is not a verified bot owner.", ephemeral=True
            )

        guild_member = await self.client.mongo.fetch_guild_member(user.id)

        invited_members = ""
        for code, user_id in guild_member["verification_codes"].items():
            if user_id is None:
                continue

            team_member = interaction.guild.get_member(user_id)
            invited_members += f"- {team_member.mention}\n"

        if len(invited_members) == 0:
            return await interaction.response.send_message(
                "This member has not invited anyone from their team to this server.."
            )

        team_view_embed = discord.Embed(
            title="Team View",
            description=f"The following users are part of {user.mention}'s team:\n\n"
                        f"{invited_members}",
            color=self.client.color,
            timestamp=discord.utils.utcnow()
        )

        await interaction.response.send_message(embed=team_view_embed)

    """ Invited member remove handling. """

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_member = await self.client.mongo.fetch_guild_member(member.id)
        if guild_member["verification_join_code"] is None:
            return

        code = guild_member["verification_join_code"]
        inviter_id = guild_member["verification_join_inviter"]

        await self.client.mongo.update_guild_member_document(
            member.id, {"$set": {"verification_join_code": None, "verification_join_inviter": None}}
        )
        await self.client.mongo.update_guild_member_document(inviter_id, {"$unset": {f"verification_codes.{code}": ""}})


async def setup(client):
    await client.add_cog(Verification(client))
