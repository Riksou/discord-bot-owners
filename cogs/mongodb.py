import motor.motor_asyncio
import ujson
from discord.ext import commands

from discord_bot_owners import DiscordBotOwners


class MongoDB(commands.Cog):
    """The cog to manage the database."""

    DEFAULT_GUILD_DATA = {
        "_id": 0,
        "tickets_channel_id": None,
        "tickets_message_id": None,
        "verification_channel_id": None,
        "verification_message_id": None,
        "pending_verification_message_ids": {},
        "auto_roles_channel_id": None,
        "auto_roles_message_id": None
    }

    DEFAULT_GUILD_MEMBER = {
        "_id": 0,
        "verification_pending": False,
        "verification_cooldown": None,
        "verification_codes": {},
        "verification_join_code": None,
        "verification_join_inviter": None,
        "exp": 0,
        "level": 1
    }

    def __init__(self, client: DiscordBotOwners):
        self.client = client
        self.db = motor.motor_asyncio.AsyncIOMotorClient(self.client.config["mongodb_uri"])["discordbotowners"]

    @staticmethod
    def _set_default_dict(current_dict, default_dict):
        for default_key, default_value in default_dict.items():
            if default_key not in current_dict.keys():
                current_dict[default_key] = ujson.loads(ujson.dumps(default_value))

            if isinstance(default_value, dict):
                for default_key_2, default_value_2 in default_value.items():
                    if default_key_2 not in current_dict[default_key].keys():
                        current_dict[default_key][default_key_2] = ujson.loads(ujson.dumps(default_value_2))

        return current_dict

    """ Guild Data collection """

    async def fetch_guild_data(self):
        guild_data = await self.db["guild_data"].find_one({"_id": str(self.client.config["guild_id"])})
        if guild_data is not None:
            guild_data = self._set_default_dict(guild_data, self.DEFAULT_GUILD_DATA)
        else:
            guild_data = ujson.loads(ujson.dumps(self.DEFAULT_GUILD_DATA))

        guild_data["_id"] = int(self.client.config["guild_id"])

        return guild_data

    async def update_guild_data_document(self, query):
        await self.db["guild_data"].update_one({"_id": str(self.client.config["guild_id"])}, query, upsert=True)

    """ Guild Member collection """

    async def fetch_guild_member(self, member_id: int):
        guild_member = await self.db["guild_member"].find_one({"_id": str(member_id)})
        if guild_member is not None:
            guild_member = self._set_default_dict(guild_member, self.DEFAULT_GUILD_MEMBER)
        else:
            guild_member = ujson.loads(ujson.dumps(self.DEFAULT_GUILD_MEMBER))

        guild_member["_id"] = member_id

        return guild_member

    async def update_guild_member_document(self, member_id: int, query):
        await self.db["guild_member"].update_one({"_id": str(member_id)}, query, upsert=True)


async def setup(client):
    await client.add_cog(MongoDB(client))
