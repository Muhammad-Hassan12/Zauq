"""Discord slash commands for Model Context Protocol (MCP) management in Zauq v4."""

import logging
import discord
from discord import app_commands
from discord.ext import commands
import httpx
from bot.api import BACKEND_URL, api_client
from backend.tools.registry import tool_registry

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
            res = await api_client.get(f"{BACKEND_URL}/api/mcp/status", timeout=5.0)
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

        # Filter registered tools for MCP source and current guild scoping
        mcp_specs = [
            t for t in tool_registry.list_tools(enabled_only=True)
            if t.source == "mcp"
        ]

        if guild_id:
            mcp_specs = [
                t for t in mcp_specs
                if not t.allowed_guild_ids or guild_id in t.allowed_guild_ids
            ]

        embed = discord.Embed(
            title="🛠️ Registered MCP Tools",
            color=0x3498db,
        )

        if not mcp_specs:
            embed.description = "No MCP tools are currently registered or accessible in this guild."
        else:
            embed.description = f"Found **{len(mcp_specs)}** active MCP tool(s) for this guild:"
            for spec in mcp_specs[:15]:  # Discord embed limit protection
                embed.add_field(
                    name=f"`{spec.name}` ({spec.risk})",
                    value=f"{spec.description[:120]}\n*Origin: Server `{spec.server_id}`*",
                    inline=False,
                )
            if len(mcp_specs) > 15:
                embed.set_footer(text=f"Showing 15 of {len(mcp_specs)} tools • Zauq v4")
            else:
                embed.set_footer(text="Zauq v4 • Model Context Protocol Client Layer")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MCPSlash(bot))
