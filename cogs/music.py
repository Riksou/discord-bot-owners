import re

import discord
import lavalink
from discord.ext import commands, menus
from discord_bot_owners import DiscordBotOwners

from utils.context import MusicContext
from utils.exceptions import MusicError

url_rx = re.compile(r'https?://(?:www\.)?.+')


class QueueMenuSource(menus.ListPageSource):

    def __init__(self, data):
        super().__init__(data, per_page=10)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page

        page_embed = discord.Embed(
            title="Queue",
            description="\n".join(f"{i + 1}. {v.author} - {v.title}" for i, v in enumerate(entries, start=offset)),
            color=menu.bot.color
        )
        page_embed.set_footer(text=f"Page {(menu.current_page + 1)}/{self.get_max_pages()}")

        return page_embed


class LavalinkVoiceClient(discord.VoiceClient):

    def __init__(self, client: DiscordBotOwners, channel: discord.abc.Connectable):
        super().__init__(client, channel)
        self.lavalink = client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
            't': 'VOICE_SERVER_UPDATE',
            'd': data
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
            't': 'VOICE_STATE_UPDATE',
            'd': data
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = False, self_mute: bool = False) -> \
            None:
        """
        Connect the bot to the voice channel and create a player_manager
        if it doesn't exist yet.
        """
        # ensure there is a player_manager when creating a new voice_client
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel, self_mute=self_mute, self_deaf=self_deaf)

    async def disconnect(self, *, force: bool = False) -> None:
        """
        Handles the disconnect.
        Cleans up running player and leaves the voice client.
        """
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel=None)

        # update the channel_id of the player to None
        # this must be done because the on_voice_state_update that would set channel_id
        # to None doesn't get dispatched after the disconnect
        player.channel_id = None
        self.cleanup()


class Music(commands.Cog):

    def __init__(self, client: DiscordBotOwners):
        self.client = client

        lavalink.add_event_hook(self.track_hook)

    async def cog_unload(self):
        self.client.lavalink._event_hooks.clear()

    async def cog_before_invoke(self, ctx):
        guild_check = ctx.guild is not None

        if guild_check:
            await self.ensure_voice(ctx)

        return guild_check

    async def ensure_voice(self, ctx):
        player = self.client.lavalink.player_manager.create(ctx.guild.id)

        should_connect = ctx.command.name in ("play",)

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise MusicError("Join a voicechannel first.")

        v_client = ctx.voice_client
        if not v_client:
            if not should_connect:
                raise MusicError("Not connected.")

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect or not permissions.speak:
                raise MusicError("I need the `CONNECT` and `SPEAK` permissions.")

            player.store("channel", ctx.channel.id)
            await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
        else:
            if v_client.channel.id != ctx.author.voice.channel.id:
                raise MusicError("You need to be in my voicechannel.")

    async def track_hook(self, event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            # When this track_hook receives a "QueueEndEvent" from lavalink.py
            # it indicates that there are no tracks left in the player's queue.
            # To save on resources, we can tell the bot to disconnect from the voicechannel.
            guild_id = event.player.guild_id
            guild = self.client.get_guild(guild_id)
            await guild.voice_client.disconnect(force=True)
        elif isinstance(event, lavalink.events.TrackStartEvent):
            channel = self.client.get_channel(event.player.fetch("channel"))
            await channel.send(embed=self._get_now_playing_embed(event.player))

    def _get_now_playing_embed(self, player: lavalink.DefaultPlayer) -> discord.Embed:
        embed = discord.Embed(
            title="Now playing",
            description=f"[{player.current.title}]({player.current.uri})",
            color=self.client.color
        )
        return embed

    @commands.command(aliases=["p"], usage="[query]")
    async def play(self, ctx: MusicContext, *, query: str = ""):
        """ Searches and plays a song from a given query. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        query = query.strip("<>")

        if len(ctx.message.attachments) == 0 and len(query) == 0:
            raise commands.BadArgument()

        if not url_rx.match(query):
            if len(ctx.message.attachments) > 0:
                query = ctx.message.attachments[0].url
            else:
                query = f"ytsearch:{query}"

        results = await player.node.get_tracks(query)

        if not results or not results.tracks:
            return await ctx.error("Nothing found!")

        embed = discord.Embed(color=self.client.color)

        # Valid loadTypes are:
        #   TRACK_LOADED    - single video/direct URL
        #   PLAYLIST_LOADED - direct URL to playlist
        #   SEARCH_RESULT   - query prefixed with either ytsearch: or scsearch:.
        #   NO_MATCHES      - query yielded no results
        #   LOAD_FAILED     - most likely, the video encountered an exception during loading.
        if results.load_type == "PLAYLIST_LOADED":
            tracks = results.tracks

            for track in tracks:
                # Add all the tracks from the playlist to the queue.
                player.add(requester=ctx.author.id, track=track)

            embed.title = "Playlist Enqueued!"
            embed.description = f'{results.playlist_info.name} - {len(tracks)} tracks'
        else:
            track = results.tracks[0]
            embed.title = "Track Enqueued"
            embed.description = f'[{track.title}]({track.uri})'

            player.add(requester=ctx.author.id, track=track)

        await ctx.send(embed=embed)

        if not player.is_playing:
            await player.play()

    @commands.command(aliases=["s"])
    async def skip(self, ctx: MusicContext):
        """ Skip the current track. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        await player.skip()
        await ctx.message.add_reaction("👌")

    @commands.command(aliases=["np", "nowplaying"])
    async def now_playing(self, ctx: MusicContext):
        """ Skip the current track. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if player.current is None:
            return await ctx.error("I'm not playing anything.")

        await ctx.send(embed=self._get_now_playing_embed(player))

    @commands.command(aliases=["q"])
    async def queue(self, ctx: MusicContext):
        """ Display the current queue of tracks. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if len(player.queue) == 0:
            return await ctx.error("The queue is empty.")

        pages = menus.MenuPages(source=QueueMenuSource(player.queue), clear_reactions_after=True, timeout=30.0)
        await pages.start(ctx)

    @commands.command(aliases=["rm"], usage="<position>")
    async def remove(self, ctx: MusicContext, position: int):
        """ Remove a track from the queue. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if len(player.queue) == 0:
            return await ctx.error("The queue is empty.")

        if position < 1:
            return await ctx.error("The position must be equal or greater than 1.")

        if position > len(player.queue):
            return await ctx.error(f"The queue only contains {len(player.queue)} tracks.")

        track = player.queue.pop(position - 1)

        await ctx.info(f"Removed {track.author} - {track.title} from the queue.")

    @commands.command(usage="<timecode>")
    async def seek(self, ctx: MusicContext, timecode: str):
        """ Seek to a given position in the track. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        parsed = timecode.split(":")
        if len(parsed) != 2 or not parsed[0].isdigit() or not parsed[1].isdigit():
            raise commands.BadArgument()

        total_ms = int(parsed[0]) * 60 * 1000 + int(parsed[1]) * 1000

        await player.seek(total_ms)
        await ctx.info(f"Seeked to `{timecode}`.")

    @commands.command()
    async def pause(self, ctx: MusicContext):
        """ Pause the current track. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        await player.set_pause(True)
        await ctx.message.add_reaction("⏸")

    @commands.command()
    async def resume(self, ctx: MusicContext):
        """ Resume the current track. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        await player.set_pause(False)
        await ctx.message.add_reaction("▶")

    @commands.command(aliases=["vol", "vl", "v"], usage="<volume>")
    async def volume(self, ctx: MusicContext, volume: int):
        """ Set the volume for the player. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if volume <= 0 or volume > 1000:
            return await ctx.send("The volume of the player must be greater than 0 and lower than 1000.")

        await player.set_volume(volume)
        await ctx.message.add_reaction("✅")

    @commands.command(aliases=["dc", "d", "leave"])
    async def disconnect(self, ctx: MusicContext):
        """ Disconnects the player from the voice channel and clears its queue. """
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not ctx.voice_client:
            return await ctx.error("Not connected.")

        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.error("You're not in my voicechannel!")

        player.queue.clear()
        await player.stop()
        await ctx.voice_client.disconnect(force=True)
        await ctx.message.add_reaction("👌")


async def setup(client):
    await client.add_cog(Music(client))
