import datetime
from typing import Union, Optional

import discord
from discord import app_commands
from discord.ext import commands


class Moderation(commands.Cog):

    def __init__(self, client) -> None:
        self.client = client

    async def send_staff_log(
            self, case_type, user: Union[discord.Member, discord.User], moderator, reason=None, duration=None
    ) -> None:
        staff_log_embed = discord.Embed(
            color=self.client.color,
            timestamp=discord.utils.utcnow()
        )

        staff_log_embed.set_author(name=f"{case_type} | {user}", icon_url=user.avatar.url)
        staff_log_embed.add_field(name="**User**", value=user.mention)
        staff_log_embed.add_field(name="**Moderator**", value=moderator.mention)
        if duration is not None:
            staff_log_embed.add_field(name="**Duration**", value=duration)
        if reason is not None:
            staff_log_embed.add_field(name="**Reason**", value=reason)
        staff_log_embed.set_footer(text=f"ID: {user.id}")

        logging_channel = self.client.get_channel(self.client.config["channel_id"]["staff_logs"])

        await logging_channel.send(embed=staff_log_embed)

    @staticmethod
    def _has_higher_role(member: discord.Member, target: discord.Member) -> bool:
        return member.top_role > target.top_role

    @staticmethod
    def str_duration_to_seconds(s) -> Optional[int]:
        try:
            return int(s[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[s[-1]]
        except (ValueError, KeyError):
            return None

    @app_commands.command(name="ban")
    @app_commands.default_permissions()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Ban a member from the server."""
        if self._has_higher_role(interaction.user, member) is False:
            return await interaction.response.send_message(
                "You do not have the permission to ban this member.", ephemeral=True
            )

        await member.ban(delete_message_days=7, reason=reason)

        await interaction.response.send_message(
            f"You have successfully banned {member.mention} from the server.", ephemeral=True
        )

        await self.send_staff_log("Ban", member, interaction.user, reason)

    @app_commands.command(name="unban")
    @app_commands.default_permissions()
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: str = None):
        """Unban a user from the server."""
        try:
            await interaction.guild.unban(user)
        except discord.HTTPException:
            return await interaction.response.send_message(f"{user.mention} is not banned.", ephemeral=True)

        await interaction.response.send_message(
            f"You have successfully unbanned {user.mention} from the server.", ephemeral=True
        )

        await self.send_staff_log("Unban", user, interaction.user, reason)

    @app_commands.command(name="softban")
    @app_commands.default_permissions()
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Softban a member from the server."""
        if self._has_higher_role(interaction.user, member) is False:
            return await interaction.response.send_message(
                "You do not have the permission to ban this member.", ephemeral=True
            )

        await member.ban(delete_message_days=7, reason=reason)
        await member.unban(reason=reason)

        await interaction.response.send_message(
            f"You have successfully softbanned {member.mention} from the server.", ephemeral=True
        )

        await self.send_staff_log("Softban", member, interaction.user, reason)

    @app_commands.command(name="kick")
    @app_commands.default_permissions()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Kick a member from the server."""
        if self._has_higher_role(interaction.user, member) is False:
            return await interaction.response.send_message(
                "You do not have the permission to ban this member.", ephemeral=True
            )

        await member.kick(reason=reason)

        await interaction.response.send_message(
            f"You have successfully kicked {member.mention} from the server.", ephemeral=True
        )

        await self.send_staff_log("Kick", member, interaction.user, reason)

    @app_commands.command(name="mute")
    @app_commands.default_permissions()
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
        """Mute a member of the server."""
        if self._has_higher_role(interaction.user, member) is False:
            return await interaction.response.send_message(
                "You do not have the permission to ban this member.", ephemeral=True
            )

        expire_seconds = self.str_duration_to_seconds(duration)
        if expire_seconds is None:
            return await interaction.response.send_message("Please use a valid duration.", ephemeral=True)

        if expire_seconds > 2419200:
            return await interaction.response.send_message("You can only mute a member for 28 days.")

        timeout_duration = datetime.timedelta(seconds=expire_seconds)

        await member.timeout(timeout_duration, reason=reason)

        await interaction.response.send_message(
            f"You have successfully muted {member.mention} until "
            f"{discord.utils.format_dt(discord.utils.utcnow() + timeout_duration, 'F')}.", ephemeral=True
        )

        await self.send_staff_log("Mute", member, interaction.user, reason, duration=duration)

    @app_commands.command(name="unmute")
    @app_commands.default_permissions()
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Unmute a member of the server."""
        if member.is_timed_out() is False:
            return await interaction.response.send_message("This member is not muted.", ephemeral=True)

        await member.timeout(None, reason=reason)

        await interaction.response.send_message(f"You have successfully unmuted {member.mention}.", ephemeral=True)

        await self.send_staff_log("Unmute", member, interaction.user, reason)

    @app_commands.command(name="purge")
    @app_commands.default_permissions()
    async def purge(self, interaction: discord.Interaction, amount: int, user: discord.User = None):
        """Purge a specific amount of messages."""
        if amount < 1 or amount > 500:
            return await interaction.response.send_message(
                "You can only delete a maximum amount of 500 messages.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # Useful so we don't delete our current interaction.
        before = discord.utils.utcnow() - datetime.timedelta(milliseconds=5)

        if user is not None:
            deleted_count = 0

            def can_be_deleted(msg):
                nonlocal deleted_count

                if deleted_count >= amount:
                    return False

                if msg.author.id != user.id:
                    return False

                deleted_count += 1

                return True

            deleted = await interaction.channel.purge(limit=300, check=can_be_deleted, before=before)
        else:
            deleted = await interaction.channel.purge(limit=amount, before=before)

        await interaction.followup.send(f"You successfully deleted {len(deleted)} messages.")


async def setup(client):
    await client.add_cog(Moderation(client))
