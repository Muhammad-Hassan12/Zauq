import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.api import BACKEND_URL, api_client

class RemindSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="remind", description="Schedule a reminder message")
    @app_commands.describe(
        message="What would you like Zauq to remind you about?",
        in_minutes="Time from now in minutes (e.g. 5, 30, 1440 for 1 day)"
    )
    async def set_reminder(
        self,
        interaction: discord.Interaction,
        message: str,
        in_minutes: int
    ):
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        payload = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "user_id": user_id,
            "message": message,
            "in_minutes": in_minutes
        }

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/reminders/create", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Failed to set reminder: {res.text}")
                    return

                embed = discord.Embed(
                    title="⏰ Reminder Set!",
                    description=f"Zauq will remind you in **{in_minutes} minute(s)**:",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Message", value=f"\"{message}\"", inline=False)
                embed.set_footer(text=f"Requested by @{interaction.user.name}")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error setting reminder: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RemindSlash(bot))
