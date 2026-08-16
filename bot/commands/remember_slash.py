
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.api import BACKEND_URL, api_client

class RememberSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="remember", description="Save a server lore fact or rule into Zauq vector memory")
    @app_commands.describe(
        fact="The server fact, rule, or inside joke to remember",
        source_type="Category: inside_joke, rule, doc, repo"
    )
    @app_commands.choices(
        source_type=[
            app_commands.Choice(name="Inside Joke", value="inside_joke"),
            app_commands.Choice(name="Server Rule", value="rule"),
            app_commands.Choice(name="Documentation", value="doc"),
            app_commands.Choice(name="Repository Note", value="repo"),
        ]
    )
    async def remember(
        self,
        interaction: discord.Interaction,
        fact: str,
        source_type: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"
        category = source_type.value if source_type else "inside_joke"

        payload = {
            "guild_id": guild_id,
            "source_type": category,
            "content": fact
        }

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/lore/add", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Failed to store lore: {res.text}")
                    return

                embed = discord.Embed(
                    title="🧠 Server Lore Remembered",
                    description=f"Saved to vector memory under **[{category.upper()}]**:",
                    color=discord.Color.purple()
                )
                embed.add_field(name="Fact", value=f"\"{fact}\"", inline=False)
                embed.set_footer(text=f"Added by @{interaction.user.name}")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error communicating with Zauq engine: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RememberSlash(bot))
