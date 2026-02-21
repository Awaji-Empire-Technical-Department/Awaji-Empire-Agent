from discord.ext import commands
from .cog import MassMuteCog


async def setup(bot: commands.Bot):
    await bot.add_cog(MassMuteCog(bot))
