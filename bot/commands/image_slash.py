import io
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.api import BACKEND_URL, api_client

class ImageSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="image", description="Generate an AI visual image based on a text prompt")
    @app_commands.describe(
        prompt="Description of the image to generate",
        model="Choose image generation model provider"
    )
    @app_commands.choices(
        model=[
            app_commands.Choice(name="Gemini Flash Image (Free, Default)", value="gemini-3.1-flash-image"),
            app_commands.Choice(name="Stable Diffusion 3.5 Large (DO)", value="stable-diffusion-3.5-large"),
            app_commands.Choice(name="Ideogram 3.0 Turbo (DO)", value="ideogram-3.0-turbo")
        ]
    )
    async def make_image(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)
        selected_model = model.value if model else "gemini-3.1-flash-image"

        payload = {
            "prompt": prompt,
            "model": selected_model
        }

        try:
            async with api_client(timeout=90.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/media/image", json=payload)
                if res.status_code != 200:
                    err_msg = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
                    await interaction.followup.send(f"⚠️ Image Generation Error ({res.status_code}): {err_msg}")
                    return

                image_bytes = io.BytesIO(res.content)
                discord_file = discord.File(image_bytes, filename="zauq_ai_art.png")

                embed = discord.Embed(
                    title="🎨 AI Image Generation",
                    description=f"**Prompt:** *\"{prompt}\"*",
                    color=discord.Color.blue()
                )
                embed.set_image(url="attachment://zauq_ai_art.png")
                embed.set_footer(text=f"Model: {selected_model} | Requested by @{interaction.user.name}")

                await interaction.followup.send(embed=embed, file=discord_file)

        except Exception as e:
            await interaction.followup.send(f"❌ Error generating image: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ImageSlash(bot))
