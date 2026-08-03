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
                res = await client.get(f"{BACKEND_URL}/api/admin/memory_stats?guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching memory stats: {res.text}", ephemeral=True)
                    return

                data = res.json()
                embed = discord.Embed(
                    title="🧠 Zauq Vector Memory Stats",
                    color=discord.Color.purple()
                )
                embed.add_field(name="User Memories", value=f"**{data.get('user_memories', 0)}**", inline=True)
                embed.add_field(name="Server Lore Entries", value=f"**{data.get('server_lore', 0)}**", inline=True)
                embed.add_field(name="Data Source", value=f"`{data.get('source', 'backend').upper()}`", inline=True)

                # Also fetch general metrics
                metrics_res = await client.get(f"{BACKEND_URL}/api/admin/metrics?guild_id={guild_id}")
                if metrics_res.status_code == 200:
                    metrics = metrics_res.json()
                    embed.add_field(name="Total API Requests", value=f"**{metrics.get('total_requests', 0)}**", inline=True)
                    embed.add_field(name="Avg Response Latency", value=f"**{metrics.get('avg_latency_ms', 0)} ms**", inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error querying admin metrics: {e}", ephemeral=True)

    @admin_group.command(name="channels", description="View channels with configured AI profiles")
    @app_commands.checks.has_permissions(administrator=True)
    async def active_channels(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/admin/active_channels?guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching channels: {res.text}", ephemeral=True)
                    return

                data = res.json()
                channels = data.get("channels", [])

                if not channels:
                    await interaction.followup.send("📭 No channels have been configured with AI profiles yet.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="📡 Active AI Channel Profiles",
                    description=f"**{len(channels)}** channel(s) configured in this server",
                    color=discord.Color.teal()
                )

                for ch in channels[:15]:  # Cap at 15 to avoid embed limits
                    ch_id = ch.get("channel_id", "?")
                    mode = ch.get("operating_mode", "hangout")
                    temp = ch.get("temperature", "default")
                    embed.add_field(
                        name=f"<#{ch_id}>",
                        value=f"Mode: `{mode}` | Temp: `{temp}`",
                        inline=True
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error querying active channels: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminSlash(bot))
