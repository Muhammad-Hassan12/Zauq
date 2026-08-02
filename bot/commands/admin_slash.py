import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class AdminSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_group = app_commands.Group(name="admin", description="Admin dashboard and server diagnostic tools")

    @admin_group.command(name="memory", description="View server memory and lore vector stats")
    @app_commands.checks.has_permissions(administrator=True)
    async def memory_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/admin/metrics?guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching stats: {res.text}", ephemeral=True)
                    return

                data = res.json()
                embed = discord.Embed(
                    title="🧠 Zauq Vector Memory & Server Stats",
                    color=discord.Color.purple()
                )
                embed.add_field(name="Total API Requests", value=f"**{data.get('total_requests', 0)}**", inline=True)
                embed.add_field(name="Avg Response Latency", value=f"**{data.get('avg_latency_ms', 0)} ms**", inline=True)
                embed.add_field(name="Data Source", value=f"`{data.get('source', 'backend').upper()}`", inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error querying admin metrics: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminSlash(bot))
