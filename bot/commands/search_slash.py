import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class SearchSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="search", description="Search the live web and get an AI-grounded summary with citations")
    @app_commands.describe(query="The topic or question to search the internet for")
    async def search_command(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None

        payload = {
            "channel_id": channel_id,
            "guild_id": guild_id,
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.display_name,
            "messages": [
                {
                    "role": "user",
                    "content": f"Search the live web for the following query and provide a comprehensive, accurate, up-to-date answer with citations: {query}"
                }
            ],
            "enable_web_search": True
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/chat", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Search failed ({res.status_code}): {res.text}")
                    return

                data = res.json()
                response_text = data.get("response", "No response received.")
                provider = data.get("provider", "ai")
                model = data.get("model", "search-model")

                embed = discord.Embed(
                    title=f"🌐 Web Search Results: \"{query[:40]}\"",
                    description=response_text[:4000],
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Grounded Search Engine • Provider: {provider} ({model})")
                await interaction.followup.send(embed=embed)

                if len(response_text) > 4000:
                    for i in range(4000, len(response_text), 1900):
                        await interaction.followup.send(content=response_text[i:i+1900])

        except Exception as e:
            await interaction.followup.send(f"❌ Error communicating with search engine: {str(e)}")

async def setup(bot: commands.Bot):
    await bot.add_cog(SearchSlash(bot))
