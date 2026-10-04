"""Discord slash commands for Zauq v4 Autonomous Agent management and discovery."""

from __future__ import annotations
import math
import logging
from typing import Any, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from bot.api import BACKEND_URL, api_client
from bot.auth import check_admin_authorization, make_denied_embed

logger = logging.getLogger("zauq.bot.commands.agent")

PAGE_SIZE = 6


class AgentToolsPaginationView(discord.ui.View):
    """Interactive paginated view for browsing registered agent tools."""

    def __init__(
        self,
        tools: List[Dict[str, Any]],
        initiator_id: int,
        guild_name: Optional[str] = None,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.tools = tools
        self.initiator_id = initiator_id
        self.guild_name = guild_name
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(tools) / PAGE_SIZE))
        self.message: Optional[discord.Message] = None
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.first_button.disabled = self.current_page == 0
        self.prev_button.disabled = self.current_page == 0
        self.page_indicator.label = f"Page {self.current_page + 1}/{self.total_pages}"
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.last_button.disabled = self.current_page >= self.total_pages - 1

    def build_page_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🛠️ Registered Agent Tools",
            color=0x3498db,
        )
        scope_text = f" for **{self.guild_name}**" if self.guild_name else ""
        embed.description = f"Browsing **{len(self.tools)}** registered tool(s){scope_text}:\n"

        start_idx = self.current_page * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        page_tools = self.tools[start_idx:end_idx]

        for t in page_tools:
            name = t.get("name", "unknown")
            risk = str(t.get("risk", "read")).upper()
            source = t.get("source", "native")
            server_id = t.get("server_id")
            desc = t.get("description", "No description provided.")

            origin_tag = f"mcp:{server_id}" if server_id else source
            badge = f"`[{risk}]` • `{origin_tag}`"
            
            val_text = desc[:140] + ("..." if len(desc) > 140 else "")
            embed.add_field(
                name=f"`{name}` {badge}",
                value=val_text,
                inline=False,
            )

        embed.set_footer(
            text=f"Page {self.current_page + 1} of {self.total_pages} • Zauq v4 Agent Runtime"
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.initiator_id:
            await interaction.response.send_message(
                "Use `/agent tools` to open your own paginated browser.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_page_embed(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page > 0:
            self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_page_embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_page_embed(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_page = self.total_pages - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_page_embed(), view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class AgentSlash(commands.Cog):
    """Slash command group for inspecting Autonomous Agent runtime status and registered tools."""

    agent_group = app_commands.Group(
        name="agent",
        description="Autonomous Agent runtime status and tool discovery",
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @agent_group.command(name="status", description="Display Zauq Agent Runtime configuration, budgets, and subsystem health")
    async def agent_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            async with api_client(timeout=5.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/agent/status",params={'channel_id':str(interaction.channel_id),'guild_id':str(interaction.guild_id) if interaction.guild_id else ''})

            if res.status_code != 200:
                await interaction.followup.send(
                    f"⚠️ Failed to fetch agent status: Backend returned HTTP {res.status_code}",
                    ephemeral=True,
                )
                return

            data = res.json()
            runtime_on = data.get("agent_runtime_enabled", False)
            max_steps = data.get("max_tool_steps", 4)
            deep_steps = data.get("deep_max_tool_steps", 6)
            search_prov = data.get("web_search_provider", "serper").capitalize()
            auto_code = str(data.get("auto_code_test_mode", "off")).upper()
            mcp_enabled = data.get("mcp_enabled", False)
            mcp_conn = data.get("mcp_servers_connected", 0)
            mcp_tot = data.get("mcp_servers_total", 0)
            total_tools = data.get("total_tools", 0)

            embed = discord.Embed(
                title="🤖 Zauq Autonomous Agent Runtime Status",
                color=0x2ecc71 if runtime_on else 0x95a5a6,
            )
            runtime_str = "🟢 **ON** (Bounded Tool Loop Active)" if runtime_on else "⚪ **OFF** (Direct Generation Mode)"
            embed.description = f"**Runtime Execution:** {runtime_str}"

            embed.add_field(
                name="⚡ Tool Step Budgets",
                value=f"• Standard Chat: `{max_steps}` steps\n• Deep Research: `{deep_steps}` steps",
                inline=True,
            )

            embed.add_field(
                name="🌐 Web Retrieval",
                value=f"• Provider: `{search_prov}`\n• Grounding: `Unified Evidence`",
                inline=True,
            )

            embed.add_field(
                name="🧪 Sandbox Testing",
                value=f"• Default Mode: `{auto_code}`\n• Max Auto-Repairs: `{data.get('auto_code_repair_attempts', 1)}`",
                inline=True,
            )

            if mcp_enabled:
                mcp_val = f"🟢 Connected (`{mcp_conn}/{mcp_tot}` active)" if mcp_tot > 0 else "🟢 Enabled (0 configured)"
            else:
                mcp_val = "⚪ Disabled (`MCP_ENABLED=false`)"
            embed.add_field(
                name="🔌 MCP Subsystem",
                value=mcp_val,
                inline=True,
            )

            embed.add_field(
                name="🛠️ Tool Catalog",
                value=f"`{total_tools}` total active tools",
                inline=True,
            )

            embed.set_footer(text="Zauq v4 • Autonomous Agent Architecture")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error fetching agent status: {e}")
            await interaction.followup.send(
                f"❌ Error communicating with backend agent service: {e}",
                ephemeral=True,
            )

    @agent_group.command(name="tools", description="Browse registered tools with risk levels and descriptions")
    @app_commands.describe(page="Jump directly to a specific page number")
    async def agent_tools(self, interaction: discord.Interaction, page: Optional[int] = 1) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        guild_name = interaction.guild.name if interaction.guild else None

        try:
            url = f"{BACKEND_URL}/api/agent/tools"
            params = {}
            if guild_id:
                params["guild_id"] = guild_id

            async with api_client(timeout=5.0) as client:
                res = await client.get(url, params=params)

            if res.status_code != 200:
                await interaction.followup.send(
                    f"⚠️ Failed to fetch tools: Backend returned HTTP {res.status_code}",
                    ephemeral=True,
                )
                return

            tools: List[Dict[str, Any]] = res.json()
            if not tools:
                embed = discord.Embed(
                    title="🛠️ Registered Agent Tools",
                    description="No tools are currently registered or accessible in this context.",
                    color=0x95a5a6,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            view = AgentToolsPaginationView(
                tools=tools,
                initiator_id=interaction.user.id,
                guild_name=guild_name,
            )

            # Jump to requested page if provided
            req_page = (page or 1) - 1
            if 0 <= req_page < view.total_pages:
                view.current_page = req_page
                view._update_buttons()

            msg = await interaction.followup.send(embed=view.build_page_embed(), view=view, ephemeral=True)
            view.message = msg

        except Exception as e:
            logger.error(f"Error fetching agent tools: {e}")
            await interaction.followup.send(
                f"❌ Error communicating with backend tool service: {e}",
                ephemeral=True,
            )

    @agent_group.command(name='enable', description='Enable or disable the agent for this channel or server')
    @app_commands.choices(scope=[app_commands.Choice(name='Channel',value='channel'),app_commands.Choice(name='Server',value='server')])
    async def agent_enable(self, interaction: discord.Interaction, enabled: bool, scope: app_commands.Choice[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_authorization(interaction):
            await interaction.followup.send(embed=make_denied_embed(),ephemeral=True)
            return
        async with api_client(timeout=10) as client:
            response=await client.post(f'{BACKEND_URL}/api/agent/config',json={'feature':'agent','enabled':enabled,'scope':scope.value if scope else 'channel','channel_id':str(interaction.channel_id),'guild_id':str(interaction.guild_id) if interaction.guild_id else None})
        if response.status_code != 200:
            await interaction.followup.send('Configuration could not be saved. Check backend availability and migrations.',ephemeral=True)
            return
        master=response.json().get('master_enabled')
        await interaction.followup.send(f'Agent preference saved: {"enabled" if enabled else "disabled"}. Global master switch: {"on" if master else "off"}.',ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AgentSlash(bot))
