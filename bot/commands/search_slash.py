import httpx
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
from backend.config import settings
from bot.api import BACKEND_URL, api_client

CATEGORY_ICONS = {
    "all": "🌐",
    "github": "💻",
    "arxiv": "📑",
    "docs": "📚",
    "wikipedia": "📖",
    "news": "📰"
}

class SearchSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="search", description="Search the live web with deep page roaming and domain filters")
    @app_commands.describe(
        query="The topic or question to search the internet for",
        deep="Enable Autonomous Deep Web Roaming (visits & reads top full pages)",
        category="Targeted domain filter (e.g. GitHub repos, ArXiv papers, Developer Docs)"
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="🌐 All Web (General)", value="all"),
        app_commands.Choice(name="💻 GitHub (Code & Repos)", value="github"),
        app_commands.Choice(name="📑 ArXiv (Research Papers)", value="arxiv"),
        app_commands.Choice(name="📚 Developer Docs (APIs & Frameworks)", value="docs"),
        app_commands.Choice(name="📖 Wikipedia (Encyclopedia)", value="wikipedia"),
        app_commands.Choice(name="📰 News & Tech (Recent Updates)", value="news"),
    ])
    async def search_command(
        self,
        interaction: discord.Interaction,
        query: str,
        deep: bool = True,
        category: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        cat_val = category.value if category else "all"
        icon = CATEGORY_ICONS.get(cat_val, "🌐")

        deep_directive = "Perform a thorough deep-research synthesis by reading and citing the attached multi-source full-page contents." if deep else "Provide a concise summary with citations."

        payload = {
            "channel_id": channel_id,
            "guild_id": guild_id,
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.display_name,
            "messages": [
                {
                    "role": "user",
                    "content": f"Please research and answer: \"{query}\". {deep_directive}"
                }
            ],
            "enable_web_search": True,
            "deep_search": deep,
            "search_category": cat_val,
            "search_query": query
        }

        try:
            async with api_client(timeout=180.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/chat", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Search failed ({res.status_code}): {res.text}")
                    return

                data = res.json()
                response_text = data.get("response", "No response received.")
                provider = data.get("provider", "ai")
                model = data.get("model", "search-model")

                badge = "Deep Research" if deep else "Quick Search"
                embed = discord.Embed(
                    title=f"{icon} {badge}: \"{query[:45]}\"",
                    description=response_text[:4000],
                    color=discord.Color.blue() if not deep else discord.Color.teal()
                )
                tool_trace = data.get("tool_trace", [])
                tools_used = [t.get("tool") for t in tool_trace if t.get("tool")]
                tools_suffix = f" • Tools: {' → '.join(tools_used)}" if tools_used else ""
                embed.set_footer(text=f"Zauq Web Intelligence • Category: {cat_val.upper()}{tools_suffix} • {provider} ({model})")
                await interaction.followup.send(embed=embed)

                if len(response_text) > 4000:
                    for i in range(4000, len(response_text), 1900):
                        await interaction.followup.send(content=response_text[i:i+1900])

        except httpx.TimeoutException:
            await interaction.followup.send(
                "⏳ **Search Timed Out**: Gathering multi-source web intelligence took too long. "
                "Please try again or use a faster model like Gemini Flash via `/model set provider:gemini model:gemini-2.5-flash`!"
            )
        except Exception as e:
            err_msg = str(e) if str(e).strip() else (repr(e) or type(e).__name__)
            await interaction.followup.send(f"❌ Error communicating with search engine: {err_msg}")

async def setup(bot: commands.Bot):
    await bot.add_cog(SearchSlash(bot))
