from discord.ext import commands
from .cog import SurveyCog


async def setup(bot: commands.Bot):
    await bot.add_cog(SurveyCog(bot))
