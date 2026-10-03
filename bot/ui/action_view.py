"""Discord UI components for Human-in-the-Loop side-effect approval (Phase 7)."""

import logging
import json
import discord
from typing import Any, Optional
from bot.api import BACKEND_URL, api_client

logger = logging.getLogger("zauq.bot.ui.action_view")


class ActionConfirmationView(discord.ui.View):
    """Interactive Discord buttons for approving or denying staged side-effect actions."""

    def __init__(
        self,
        action_id: str,
        initiator_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk: str = "write",
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.action_id = action_id
        self.initiator_id = str(initiator_id)
        self.tool_name = tool_name
        self.arguments = arguments
        self.risk = risk
        self.message: Optional[discord.Message] = None

    def build_preview_embed(self) -> discord.Embed:
        """Construct a formatted Discord embed previewing the proposed action."""
        embed = discord.Embed(
            title="⚠️ Action Requires Confirmation",
            description=(
                f"Zauq wants to execute a side-effect tool (**{self.risk.upper()}** risk).\n"
                "Please review the parameters below and confirm execution."
            ),
            color=0xf39c12 if self.risk == "write" else 0xe74c3c,
        )
        embed.add_field(name="Tool", value=f"`{self.tool_name}`", inline=True)
        embed.add_field(name="Risk Level", value=f"`{self.risk.upper()}`", inline=True)
        embed.add_field(name="Initiated By", value=f"<@{self.initiator_id}>", inline=True)

        # Truncate and format arguments
        args_str = json.dumps(self.arguments, indent=2)
        if len(args_str) > 1000:
            args_str = args_str[:1000] + "\n...[truncated]"
        embed.add_field(
            name="Proposed Arguments",
            value=f"```json\n{args_str}\n```",
            inline=False,
        )
        embed.set_footer(text=f"Action ID: {self.action_id} • Expires in 5 minutes")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce that only the initiating user or server administrator can act."""
        is_initiator = str(interaction.user.id) == self.initiator_id
        is_admin = False
        if interaction.guild and hasattr(interaction.user, "guild_permissions"):
            is_admin = interaction.user.guild_permissions.administrator

        if not (is_initiator or is_admin):
            await interaction.response.send_message(
                "⛔ You cannot approve or deny this action. Only the initiating user can confirm.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        is_admin = False
        if interaction.guild and hasattr(interaction.user, "guild_permissions"):
            is_admin = interaction.user.guild_permissions.administrator

        try:
            res = await api_client.post(
                f"{BACKEND_URL}/api/actions/{self.action_id}/approve",
                json={
                    "user_id": str(interaction.user.id),
                    "is_admin": is_admin,
                },
                timeout=30.0,
            )

            # Disable all buttons
            for child in self.children:
                child.disabled = True

            if res.status_code == 200:
                data = res.json()
                exec_data = data.get("execution", {})
                success = exec_data.get("success", False)

                embed = discord.Embed(
                    title="✅ Action Approved & Executed" if success else "⚠️ Action Approved but Failed",
                    color=0x2ecc71 if success else 0xe67e22,
                )
                embed.description = f"Approved by <@{interaction.user.id}>."
                embed.add_field(name="Tool", value=f"`{self.tool_name}`", inline=True)

                output_text = str(exec_data.get("content") or exec_data.get("error") or "Done.")
                if len(output_text) > 1000:
                    output_text = output_text[:1000] + "\n...[truncated]"

                embed.add_field(
                    name="Result",
                    value=f"```\n{output_text}\n```",
                    inline=False,
                )
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                err_detail = res.text
                try:
                    err_detail = res.json().get("detail", res.text)
                except Exception:
                    pass
                embed = discord.Embed(
                    title="❌ Approval Rejected by Policy",
                    description=f"Backend rejected execution: `{err_detail}`",
                    color=0xe74c3c,
                )
                await interaction.edit_original_response(embed=embed, view=self)

        except Exception as e:
            logger.error(f"Error approving action '{self.action_id}': {e}")
            await interaction.followup.send(f"❌ Error communicating with backend: {e}", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        is_admin = False
        if interaction.guild and hasattr(interaction.user, "guild_permissions"):
            is_admin = interaction.user.guild_permissions.administrator

        try:
            res = await api_client.post(
                f"{BACKEND_URL}/api/actions/{self.action_id}/deny",
                json={
                    "user_id": str(interaction.user.id),
                    "is_admin": is_admin,
                },
                timeout=10.0,
            )

            # Disable all buttons
            for child in self.children:
                child.disabled = True

            embed = discord.Embed(
                title="❌ Action Denied",
                description=f"Action `{self.tool_name}` was denied by <@{interaction.user.id}>. Execution cancelled.",
                color=0x7f8c8d,
            )
            await interaction.edit_original_response(embed=embed, view=self)

        except Exception as e:
            logger.error(f"Error denying action '{self.action_id}': {e}")
            await interaction.followup.send(f"❌ Error communicating with backend: {e}", ephemeral=True)

    async def on_timeout(self) -> None:
        """Automatically disable buttons when the action expires."""
        for child in self.children:
            child.disabled = True

        if self.message:
            try:
                embed = discord.Embed(
                    title="⏱️ Action Expired",
                    description=f"Action `{self.tool_name}` was not approved within the time limit. Execution cancelled.",
                    color=0x7f8c8d,
                )
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
