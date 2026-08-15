import io
import base64
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class FileSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    file_group = app_commands.Group(name="file", description="On-demand file generation and export tools")

    @file_group.command(name="generate", description="Generate a standalone code or document file on demand")
    @app_commands.describe(
        filename="Target filename with extension (e.g. app.py, config.json, query.sql, README.md)",
        prompt="Instructions describing what the file should contain"
    )
    async def generate_file_group(self, interaction: discord.Interaction, filename: str, prompt: str):
        await self._process_file_generation(interaction, filename, prompt)

    @app_commands.command(name="create_file", description="Quick shortcut to generate a downloadable code or document file")
    @app_commands.describe(
        filename="Target filename with extension (e.g. app.py, index.html, schema.sql)",
        prompt="Instructions describing what the file should contain"
    )
    async def create_file_shortcut(self, interaction: discord.Interaction, filename: str, prompt: str):
        await self._process_file_generation(interaction, filename, prompt)

    async def _process_file_generation(self, interaction: discord.Interaction, filename: str, prompt: str):
        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None

        full_prompt = (
            f"Generate the complete contents for a file named `{filename}` according to these instructions:\n"
            f"{prompt}\n\n"
            f"Wrap the complete code/text strictly inside <zauq_file filename=\"{filename}\">...content...</zauq_file>."
        )

        payload = {
            "channel_id": channel_id,
            "guild_id": guild_id,
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.display_name,
            "messages": [{"role": "user", "content": full_prompt}]
        }

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/chat", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ File generation failed ({res.status_code}): {res.text}")
                    return

                data = res.json()
                response_text = data.get("response", "")
                files = data.get("files", [])

                discord_files = []
                if files:
                    for f_item in files:
                        raw_bytes = base64.b64decode(f_item["bytes_b64"])
                        discord_files.append(discord.File(io.BytesIO(raw_bytes), filename=f_item["filename"]))
                else:
                    # Fallback create file from raw response
                    file_bytes = response_text.encode("utf-8")
                    discord_files.append(discord.File(io.BytesIO(file_bytes), filename=filename))

                embed = discord.Embed(
                    title=f"📄 Generated File: `{filename}`",
                    description=response_text[:1000] if response_text else "Your file has been generated and is attached below.",
                    color=discord.Color.teal()
                )
                embed.set_footer(text=f"Generated via Zauq Engine • {filename}")

                await interaction.followup.send(embed=embed, files=discord_files)

        except Exception as e:
            await interaction.followup.send(f"❌ Error generating file: {str(e)}")

async def setup(bot: commands.Bot):
    await bot.add_cog(FileSlash(bot))
