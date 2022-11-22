import asyncio

import discord
from discord import app_commands
from discord.ext import commands, tasks

from discord_bot_owners import DiscordBotOwners


class DeniedAdvertisementApplicationModal(discord.ui.Modal, title="Deny Advertisement Application"):

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        max_length=1024
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_data = await interaction.client.mongo.fetch_guild_data()

        user_id = guild_data["pending_ad_message_ids"][str(interaction.message.id)]
        member = interaction.guild.get_member(user_id)

        embed = interaction.message.embeds[0]

        embed.set_field_at(0, name="Status", value="Denied.")
        embed.add_field(name="Reason", value=self.reason.value)
        embed.colour = interaction.client.red
        await interaction.message.edit(embed=embed, view=None)

        await interaction.client.mongo.update_guild_member_document(user_id, {"$set": {"ad_pending": False}})
        await interaction.client.mongo.update_guild_data_document(
            {
                "$unset": {f"pending_ad_message_ids.{interaction.message.id}": ""}
            }
        )

        await interaction.response.send_message(
            f"You have denied {interaction.user.mention}'s advertisement application.", ephemeral=True
        )

        if member is not None:
            denied_embed = discord.Embed(
                title="Advertisement Application Denied",
                description="Your advertisement application has been denied.",
                color=interaction.client.color,
                timestamp=discord.utils.utcnow()
            )

            denied_embed.add_field(name="Reason", value=self.reason.value)

            try:
                await member.send(embed=denied_embed)
            except discord.HTTPException:
                pass


class PendingAdvertisementView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="persisten:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_data = await interaction.client.mongo.fetch_guild_data()

        user_id = guild_data["pending_ad_message_ids"][str(interaction.message.id)]
        member = interaction.guild.get_member(user_id)

        embed = interaction.message.embeds[0]

        if member is None:
            embed.colour = interaction.client.red
            embed.set_field_at(0, name="Status", value="User left.")
            await interaction.client.mongo.update_guild_member_document(user_id, {"$set": {"ad_pending": False}})
            return await interaction.response.send_message("The user left the server.", ephemeral=True)

        await interaction.client.mongo.update_guild_data_document(
            {
                "$push": {"ads": {"user_id": user_id, "content": interaction.message.content}},
                "$unset": {f"pending_ad_message_ids.{interaction.message.id}": ""}
            }
        )

        await interaction.client.mongo.update_guild_member_document(
            user_id, {"$set": {"ad_pending": False, "ad_listed": True}}
        )

        embed = interaction.message.embeds[0]
        embed.colour = interaction.client.green
        embed.set_field_at(0, name="Status", value="Accepted.")

        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message(
            f"You have accepted {member.mention}'s advertisement application.", ephemeral=True
        )

        accepted_embed = discord.Embed(
            title="Advertisement Application Accepted",
            description="Your advertisement application has been accepted.",
            color=interaction.client.color,
            timestamp=discord.utils.utcnow()
        )

        try:
            await member.send(embed=accepted_embed)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, custom_id="persisten:deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(DeniedAdvertisementApplicationModal())


class AdvertisementApplicationModal(discord.ui.Modal, title="Advertisement Application"):

    advertisement_content = discord.ui.TextInput(
        label="Advertisement's Content",
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.client.mongo.update_guild_member_document(
            interaction.user.id, {"$set": {"ad_pending": True}}
        )

        ads_verificatrion_channel = interaction.guild.get_channel(
            interaction.client.config["channel_id"]["ads_verification"]
        )

        ad_owner_embed = discord.Embed(
            title="Advertisement Application",
            description=f"{interaction.user.mention} ({interaction.user}) has sent an advertisement application.",
            color=interaction.client.color
        )
        ad_owner_embed.set_thumbnail(url=interaction.user.display_avatar)

        ad_owner_embed.add_field(name="Status", value="Pending.")

        pending_ad_message = await ads_verificatrion_channel.send(
            content=self.advertisement_content.value, embed=ad_owner_embed, view=PendingAdvertisementView()
        )

        await interaction.client.mongo.update_guild_data_document(
            {"$set": {f"pending_ad_message_ids.{pending_ad_message.id}": interaction.user.id}}
        )

        await interaction.response.send_message(
            "You have successfully applied for an advertisement, please wait while we review your application.",
            ephemeral=True
        )


class Advertisements(commands.Cog):
    """The cog to manage the advertisements feature."""

    def __init__(self, client: DiscordBotOwners):
        self.client = client

    async def cog_load(self) -> None:
        self.post_advertisement.start()

    async def cog_unload(self) -> None:
        self.post_advertisement.stop()

    @tasks.loop(hours=6)
    async def post_advertisement(self) -> None:
        guild_data = await self.client.mongo.fetch_guild_data()

        if len(guild_data["ads"]) == 0:
            await asyncio.sleep(60)
            self.post_advertisement.restart()
            return

        ad_to_post = guild_data["ads"][0]

        await self.client.mongo.update_guild_data_document({"$pull": {"ads": ad_to_post}})
        await self.client.mongo.update_guild_member_document(
            ad_to_post["user_id"], {"$set": {"ad_listed": False}}
        )

        guild = self.client.get_guild(self.client.config["guild_id"])
        member = guild.get_member(ad_to_post["user_id"])

        author = f"Sent by: {ad_to_post['user_id']}"
        if member is not None and len(str(member)) <= 70:
            author = f"Sent by: {member}"

        verified_promotions_channel = self.client.get_channel(self.client.config["channel_id"]["verified_promotions"])

        button_view = discord.ui.View()
        button_view.add_item(item=discord.ui.Button(label=author, disabled=True))
        await verified_promotions_channel.send(ad_to_post["content"], view=button_view)

    @post_advertisement.before_loop
    async def post_advertisement_before_loop(self) -> None:
        await self.client.wait_until_ready()

    @app_commands.command(name="adapply")
    async def ad_apply(self, interaction: discord.Interaction):
        """Apply for an advertisement."""
        guild_member = await self.client.mongo.fetch_guild_member(interaction.user.id)
        if guild_member["ad_pending"] is True:
            return await interaction.response.send_message("Your ad is already pending.", ephemeral=True)

        if guild_member["ad_listed"] is True:
            guild_data = await self.client.mongo.fetch_guild_data()

            position = 1
            for ad in guild_data["ads"]:
                if ad["user_id"] == interaction.user.id:
                    break

                position += 1

            return await interaction.response.send_message(
                f"Your ad is already listed and you are currently number #{position} on the list.", ephemeral=True
            )

        await interaction.response.send_modal(AdvertisementApplicationModal())


async def setup(client):
    await client.add_cog(Advertisements(client))
