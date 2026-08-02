import io
import discord
from discord import app_commands
from discord.ext import commands

class ExportSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="export", description="Export recent thread conversation as a Markdown document")
    @app_commands.describe(limit="Number of messages to export (default: 50, max 100)")
    async def export_chat(self, interaction: discord.Interaction, limit: int = 50):
        await interaction.response.defer(thinking=True)
        channel = interaction.channel
        limit = min(max(limit, 10), 100)

        lines = [
            f"# 📜 Zauq Chat Transcript Export",
            f"**Channel:** #{channel.name} | **Guild ID:** `{interaction.guild_id or 'DM'}`",
            f"**Exported At:** {interaction.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**Total Messages:** {limit}",
            "---",
            ""
        ]

        try:
            async for msg in channel.history(limit=limit, oldest_first=True):
                timestamp = msg.created_at.strftime("%H:%M:%S")
                author = f"**{msg.author.display_name}** (`@{msg.author.name}`)"
                content = msg.content.strip()
                if not content and msg.attachments:
                    content = f"*[Attached {len(msg.attachments)} file(s)]*"

                lines.append(f"### [{timestamp}] {author}")
                lines.append(f"{content}\n")

            md_content = "\n".join(lines)
            file_bytes = io.BytesIO(md_content.encode("utf-8"))
            filename = f"zauq_transcript_{channel.name[:15]}_{interaction.created_at.strftime('%Y%m%d')}.md"

            discord_file = discord.File(file_bytes, filename=filename)
            embed = discord.Embed(
                title="📥 Export Complete",
                description=f"Exported **{limit}** messages to `{filename}`.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, file=discord_file)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to export transcript: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportSlash(bot))
