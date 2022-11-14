from discord.ext import commands


class MusicError(commands.CommandError):

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
