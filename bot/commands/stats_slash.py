

import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class StatsSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="stats", description="View server request volume, latency, and LLM provider metrics")
    async def server_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/admin/metrics?guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Metrics Error: {res.text}")
                    return

                data = res.json()
                total_reqs = data.get("total_requests", 0)
                avg_latency = data.get("avg_latency_ms", 0)
                breakdown = data.get("provider_breakdown", {})

                embed = discord.Embed(
                    title="📊 Zauq Server Analytics & Audit Dashboard",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Total Requests", value=f"**{total_reqs}**", inline=True)
                embed.add_field(name="Avg Response Latency", value=f"**{avg_latency} ms**", inline=True)

                if breakdown:
                    breakdown_str = "\n".join([f"• **{k}**: {v} requests" for k, v in breakdown.items()])
                    embed.add_field(name="Model Provider Usage", value=breakdown_str, inline=False)
                else:
                    embed.add_field(name="Model Provider Usage", value="No requests logged yet.", inline=False)

                embed.set_footer(text=f"Data Source: {data.get('source', 'backend').upper()}")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to query metrics: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsSlash(bot))
