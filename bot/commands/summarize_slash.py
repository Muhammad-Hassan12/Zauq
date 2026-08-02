import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.stream_buffer import split_message_chunks

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class SummarizeSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="summarize", description="Summarize recent thread or channel conversation into key bullet points")
    @app_commands.describe(limit="Number of recent messages to analyze (default: 30)")
    async def summarize_chat(self, interaction: discord.Interaction, limit: int = 30):
        await interaction.response.defer(thinking=True)
        channel = interaction.channel
        limit = min(max(limit, 5), 50)

        # Fetch recent channel messages
        messages_history = []
        try:
            async for msg in channel.history(limit=limit, oldest_first=False):
                content = msg.content.strip()
                if content and not content.startswith("💭 *Thinking...*"):
                    author = msg.author.display_name
                    messages_history.append(f"{author}: {content[:500]}")
            messages_history.reverse()
        except Exception as e:
            await interaction.followup.send(f"⚠️ Failed to fetch channel history: {e}")
            return

        if not messages_history:
            await interaction.followup.send("⚠️ No text messages found to summarize.")
            return

        transcript_text = "\n".join(messages_history)
        prompt = (
            f"Please provide a clear, concise bullet-point summary of the following discussion transcript ({len(messages_history)} messages):\n\n"
            f"{transcript_text[:8000]}"
        )

        chat_payload = {
            "channel_id": str(channel.id),
            "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "messages": [{"role": "user", "content": prompt}],
            "mode_override": "dev"
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/chat", json=chat_payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Backend Error: {res.text}")
                    return

                summary_text = res.json().get("response", "")
                chunks = split_message_chunks(summary_text, max_length=1900)

                embed = discord.Embed(
                    title=f"📋 Conversation Summary ({len(messages_history)} messages)",
                    description=chunks[0],
                    color=discord.Color.teal()
                )
                embed.set_footer(text=f"Requested by @{interaction.user.name}")
                await interaction.followup.send(embed=embed)

                for follow_up in chunks[1:]:
                    await channel.send(content=follow_up)

        except Exception as e:
            await interaction.followup.send(f"❌ Error generating summary: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(SummarizeSlash(bot))
