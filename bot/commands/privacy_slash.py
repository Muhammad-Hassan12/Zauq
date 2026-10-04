
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.api import BACKEND_URL, api_client

class PrivacySlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="forget", description="Purge all stored episodic memories associated with your User ID")
    async def purge_my_data(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        user_id = str(interaction.user.id)

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.delete(f"{BACKEND_URL}/api/admin/purge_user_data?user_id={user_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Failed to purge data: {res.text}", ephemeral=True)
                    return

                data = res.json()
                count = data.get("deleted_memories_count", 0)

                embed = discord.Embed(
                    title="🧹 Privacy Data Purge Complete",
                    description=f"Successfully purged **{count}** stored episodic memory entries associated with your User ID (`{user_id}`).",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Zauq respects user privacy and data retention rights.")
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error purging user data: {e}", ephemeral=True)

    @app_commands.command(name="privacy", description="View Zauq privacy disclosure and data handling policies")
    async def privacy_info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔒 Zauq Privacy & Data Handling Policy",
            description=(
                "**External processing:**\n"
                "Messages, relevant context and attachments may reach the selected AI provider, fallback providers, search/page services or configured MCP tools. "
                "Provider retention and training terms depend on the operator's accounts; Zauq cannot guarantee their policies.\n\n"
                "**Data Controls:**\n"
                "• `/forget` deletes stored episodic facts for your user ID. It does not delete Discord history, logs, lore or provider copies. New conversations may create new memories.\n"
                "• `/model status` shows which AI provider is serving your channel."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="AgenticEra Systems — Privacy First AI Architecture")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PrivacySlash(bot))
