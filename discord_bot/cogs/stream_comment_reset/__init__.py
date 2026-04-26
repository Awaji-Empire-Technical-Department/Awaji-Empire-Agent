from discord.ext import commands
from .cog import StreamCommentResetCog


async def setup(bot: commands.Bot):
    await bot.add_cog(StreamCommentResetCog(bot))
