
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.api import BACKEND_URL, api_client

class StatsSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="stats", description="View server request volume, latency, and LLM provider metrics")
    async def server_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with api_client(timeout=10.0) as client:
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

                embed.add_field(name="Tools", value=(
                    f"Steps: {data.get('total_tool_steps', 0)} · Search: {data.get('total_search_calls', 0)}\n"
                    f"Pages: {data.get('total_pages_fetched', 0)} · Sandbox: {data.get('total_sandbox_calls', 0)}\n"
                    f"MCP: {data.get('total_mcp_calls', 0)} · Failures: {data.get('total_tool_failures', 0)}"
                ), inline=False)
                unknown_usage = data.get('unknown_usage_requests', 0)
                embed.add_field(name="Reported Tokens", value=(
                    f"Input: {data.get('total_input_tokens', 0)} · Output: {data.get('total_output_tokens', 0)}\n"
                    f"Requests with unknown usage: {unknown_usage}"
                ), inline=False)
                cost = data.get('total_estimated_cost_usd')
                cost_text = f"${cost:.6f}" if isinstance(cost, (int, float)) else 'Unknown'
                embed.add_field(name="Estimated Model Cost", value=(
                    f"{cost_text}\nRequests with unknown cost: {data.get('unknown_cost_requests', 0)}\n"
                    "Configured model rates only; external service fees excluded."
                ), inline=False)
                embed.set_footer(text=f"Data Source: {data.get('source', 'backend').upper()} · {data.get('window', 'backend reporting window')}")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to query metrics: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsSlash(bot))
