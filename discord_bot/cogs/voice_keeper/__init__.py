from discord.ext import commands
from .main import VoiceKeeper

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceKeeper(bot))
