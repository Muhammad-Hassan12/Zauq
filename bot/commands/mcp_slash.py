"""Discord slash commands for Model Context Protocol (MCP) management in Zauq v4."""

import logging
import discord
from discord import app_commands
from discord.ext import commands
import httpx
from bot.api import BACKEND_URL, api_client
from bot.commands.agent_slash import AgentToolsPaginationView

logger = logging.getLogger("zauq.bot.commands.mcp")


class MCPSlash(commands.Cog):
    """Slash command group for inspecting MCP servers and discovered tools."""

    mcp_group = app_commands.Group(
        name="mcp",
        description="Model Context Protocol (MCP) server status and tools",
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @mcp_group.command(name="status", description="Check connection health for external MCP servers")
    async def mcp_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            async with api_client(timeout=5.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/mcp/status")
            if res.status_code != 200:
                await interaction.followup.send(
                    f"⚠️ Failed to fetch MCP status: Backend returned HTTP {res.status_code}",
                    ephemeral=True,
                )
                return

            data = res.json()
            enabled = data.get("enabled", False)
            servers = data.get("servers", [])

            embed = discord.Embed(
                title="🔌 Model Context Protocol (MCP) Status",
                color=0x2ecc71 if enabled else 0x95a5a6,
            )
            embed.description = f"**MCP Subsystem:** {'🟢 Enabled' if enabled else '⚪ Disabled (MCP_ENABLED=false)'}"

            if not servers:
                embed.add_field(
                    name="Configured Servers",
                    value="No external MCP servers configured or active.",
                    inline=False,
                )
            else:
                for s in servers:
                    sid = s.get("id", "unknown")
                    connected = s.get("connected", False)
                    tool_count = s.get("tools", 0)
                    error = s.get("error")

                    status_str = "🟢 Connected" if connected else "🔴 Disconnected"
                    val = f"**Status:** {status_str}\n**Discovered Tools:** {tool_count}"
                    if error:
                        val += f"\n**Error:** `{error[:100]}`"

                    embed.add_field(
                        name=f"Server: `{sid}`",
                        value=val,
                        inline=False,
                    )

            embed.set_footer(text="Zauq v4 • Model Context Protocol Client Layer")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error fetching MCP status: {e}")
            await interaction.followup.send(
                f"❌ Error communicating with backend MCP service: {e}",
                ephemeral=True,
            )

    @mcp_group.command(name="tools", description="List external MCP tools registered and available in this server")
    async def mcp_tools(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None

        try:
            async with api_client(timeout=5) as client:
                response=await client.get(f'{BACKEND_URL}/api/agent/tools',params={'guild_id':guild_id or ''})
            if response.status_code != 200:
                await interaction.followup.send('Backend tool discovery is unavailable.',ephemeral=True)
                return
            tools=[tool for tool in response.json() if tool.get('source')=='mcp']
            if not tools:
                await interaction.followup.send('No approved MCP tools are available in this guild.',ephemeral=True)
                return
            view=AgentToolsPaginationView(tools,interaction.user.id,interaction.guild.name if interaction.guild else None)
            view.message=await interaction.followup.send(embed=view.build_page_embed(),view=view,ephemeral=True)
        except Exception:
            await interaction.followup.send('Could not contact backend tool discovery.',ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MCPSlash(bot))
