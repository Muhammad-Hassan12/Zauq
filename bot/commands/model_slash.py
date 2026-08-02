import sys
import os

# Ensure project root is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class ModelSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    model_group = app_commands.Group(name="model", description="Configure AI model tiers and providers for this channel")

    @model_group.command(name="status", description="Check active model tier and provider for this channel")
    async def model_status(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/model/status?channel_id={channel_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching status: {res.text}")
                    return

                data = res.json()
                tier = data.get("tier", 1)
                provider = data.get("provider", "gemini").upper()
                model_name = data.get("model_name", "gemini-2.5-flash")

                embed = discord.Embed(
                    title="🤖 Current Model Configuration",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Channel ID", value=f"`{channel_id}`", inline=False)
                embed.add_field(name="Selected Tier", value=f"**Tier {tier}**", inline=True)
                embed.add_field(name="Provider", value=f"**{provider}**", inline=True)
                embed.add_field(name="Model", value=f"`{model_name}`", inline=True)

                if data.get("is_default"):
                    embed.set_footer(text="Using system default (Tier 1 Gemini). Use '/model set' to change.")
                else:
                    embed.set_footer(text=f"Updated by @{data.get('updated_by', 'Admin')}")

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to query backend engine: {e}")

    async def model_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        models = [
            "gemini-2.5-flash",
            "llama3.3-70b-instruct",
            "llama3.1-8b-instruct",
            "mistral-7b-instruct",
            "qwen3.5:4b",
            "qwen3.5-t4"
        ]
        return [
            app_commands.Choice(name=m, value=m)
            for m in models if current.lower() in m.lower()
        ][:25]

    @model_group.command(name="set", description="Set model tier and provider for this channel")
    @app_commands.describe(
        tier="Choose Tier: 1 (Cloud Primary), 2 (Local Ollama), 3 (Kaggle T4)",
        provider="Select Provider: gemini, digitalocean, ollama, kaggle",
        model_name="Optional custom model name (autocomplete available)"
    )
    @app_commands.choices(
        tier=[
            app_commands.Choice(name="Tier 1 (Cloud Primary: Gemini / DigitalOcean)", value=1),
            app_commands.Choice(name="Tier 2 (Local VPS: Ollama)", value=2),
            app_commands.Choice(name="Tier 3 (Batch GPU: Kaggle T4)", value=3),
        ],
        provider=[
            app_commands.Choice(name="Gemini 2.5 Flash", value="gemini"),
            app_commands.Choice(name="DigitalOcean Gradient", value="digitalocean"),
            app_commands.Choice(name="Local Ollama (qwen3.5:4b)", value="ollama"),
            app_commands.Choice(name="Kaggle T4 Tunnel", value="kaggle"),
        ]
    )
    @app_commands.autocomplete(model_name=model_name_autocomplete)
    async def model_set(
        self,
        interaction: discord.Interaction,
        tier: app_commands.Choice[int],
        provider: app_commands.Choice[str],
        model_name: str = None
    ):

        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)
        user_name = interaction.user.name

        payload = {
            "channel_id": channel_id,
            "tier": tier.value,
            "provider": provider.value,
            "model_name": model_name,
            "updated_by": user_name
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/model/set", json=payload)
                if res.status_code != 200:
                    err_detail = res.json().get("detail", res.text)
                    await interaction.followup.send(f"⚠️ Failed to update configuration: {err_detail}")
                    return

                data = res.json().get("data", {})
                embed = discord.Embed(
                    title="✅ Model Selection Updated",
                    description=f"This channel is now locked to **Tier {tier.value}** via **{provider.name}**.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Model", value=f"`{data.get('model_name')}`", inline=True)
                embed.add_field(name="Updated By", value=f"@{user_name}", inline=True)
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reach backend engine: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ModelSlash(bot))
