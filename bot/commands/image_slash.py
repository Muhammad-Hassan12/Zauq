import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class ImageSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="image", description="Generate an AI visual image based on a text prompt")
    @app_commands.describe(
        prompt="Description of the image to generate",
        model="Choose image generation model (DigitalOcean Gradient)"
    )
    @app_commands.choices(
        model=[
            app_commands.Choice(name="Stable Diffusion 3.5 Large (Default)", value="stable-diffusion-3.5-large"),
            app_commands.Choice(name="Ideogram 3.0 Turbo", value="ideogram-3.0-turbo")
        ]
    )
    async def make_image(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)
        selected_model = model.value if model else "stable-diffusion-3.5-large"

        payload = {
            "prompt": prompt,
            "model": selected_model
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/media/image", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Image Generation Error: {res.text}")
                    return

                import tempfile
                temp_img_path = os.path.join(tempfile.gettempdir(), f"discord_image_{os.urandom(4).hex()}.png")
                with open(temp_img_path, "wb") as f:
                    f.write(res.content)

                discord_file = discord.File(temp_img_path, filename="zauq_ai_art.png")
                embed = discord.Embed(
                    title="🎨 AI Image Generation",
                    description=f"**Prompt:** *\"{prompt}\"*",
                    color=discord.Color.blue()
                )
                embed.set_image(url="attachment://zauq_ai_art.png")
                embed.set_footer(text=f"Requested by @{interaction.user.name}")

                await interaction.followup.send(embed=embed, file=discord_file)
                try:
                    os.remove(temp_img_path)
                except Exception:
                    pass

        except Exception as e:
            await interaction.followup.send(f"❌ Error generating image: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ImageSlash(bot))
