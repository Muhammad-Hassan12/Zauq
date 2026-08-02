import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class ModerationSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    mod_group = app_commands.Group(name="moderation", description="Configure AI content moderation settings")

    @mod_group.command(name="enable", description="Enable or disable AI content moderation for this server")
    @app_commands.describe(status="Choose True to enable, False to disable")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_mod(self, interaction: discord.Interaction, status: bool):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        payload = {
            "guild_id": guild_id,
            "enabled": status,
            "sensitivity": "medium"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/moderation/settings", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error updating moderation: {res.text}", ephemeral=True)
                    return

                status_str = "ENABLED 🛡️" if status else "DISABLED ⚪"
                embed = discord.Embed(
                    title=f"🛡️ AI Moderation {status_str}",
                    description=f"AI content filtering has been set to **{status_str}** for this server.",
                    color=discord.Color.green() if status else discord.Color.greyple()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error updating moderation: {e}", ephemeral=True)

    @mod_group.command(name="sensitivity", description="Set AI moderation sensitivity level")
    @app_commands.describe(level="Choose sensitivity: low, medium, high")
    @app_commands.choices(
        level=[
            app_commands.Choice(name="Low (Only severe toxic content)", value="low"),
            app_commands.Choice(name="Medium (Balanced protection)", value="medium"),
            app_commands.Choice(name="High (Strict content filtering)", value="high"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_sensitivity(self, interaction: discord.Interaction, level: app_commands.Choice[str]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        payload = {
            "guild_id": guild_id,
            "enabled": True,
            "sensitivity": level.value
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/moderation/settings", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error updating sensitivity: {res.text}", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="⚙️ Moderation Sensitivity Updated",
                    description=f"AI moderation sensitivity is now set to **{level.name}**.",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error updating sensitivity: {e}", ephemeral=True)

    @mod_group.command(name="log", description="View recent moderation log entries for this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_log(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/moderation/log?guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching moderation logs: {res.text}", ephemeral=True)
                    return

                logs = res.json().get("logs", [])
                if not logs:
                    await interaction.followup.send("🟢 No moderation flags recorded for this server.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="🛡️ Recent Moderation Logs",
                    color=discord.Color.red()
                )
                for item in logs[:5]:
                    action = item.get("action_taken", "flagged").upper()
                    user = item.get("user_id", "unknown")
                    reason = item.get("reason", "no reason")
                    embed.add_field(
                        name=f"[{action}] User: <@{user}>",
                        value=f"**Reason:** {reason}\n**Content:** `{item.get('message_content', '')[:100]}`",
                        inline=False
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching moderation logs: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationSlash(bot))
