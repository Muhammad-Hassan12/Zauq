import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.auth import check_admin_authorization, make_denied_embed
from bot.api import BACKEND_URL, api_client

class ModelSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    model_group = app_commands.Group(name="model", description="Configure AI model tiers, providers, and server defaults")

    @model_group.command(name="status", description="Check active model tier and provider for this channel or server")
    async def model_status(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "dm"

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/model/status?channel_id={channel_id}&guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching status: {res.text}")
                    return

                data = res.json()
                tier = data.get("tier", 1)
                provider = data.get("provider", "gemini").upper()
                model_name = data.get("model_name", "gemini-2.5-flash")
                scope = data.get("scope", "system")

                provider_display = "Google AI Studio" if provider == "GEMINI" else ("DigitalOcean Gradient" if provider == "DIGITALOCEAN" else provider)

                embed = discord.Embed(
                    title="🤖 Current Model Configuration",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Active Channel", value=f"<#{channel_id}>", inline=False)
                embed.add_field(name="Selected Tier", value=f"**Tier {tier}**", inline=True)
                embed.add_field(name="Provider", value=f"**{provider_display}**", inline=True)
                embed.add_field(name="Model", value=f"`{model_name}`", inline=True)

                if data.get("is_channel_override"):
                    embed.add_field(name="Configuration Scope", value="📌 **Channel-Specific Override**", inline=False)
                    embed.set_footer(text=f"Updated by @{data.get('updated_by', 'Admin')} • Use '/model reset' to restore server default.")
                elif data.get("is_server_default"):
                    embed.add_field(name="Configuration Scope", value="🌐 **Community Server Default**", inline=False)
                    embed.set_footer(text="Inherited from permanent server settings. Use '/model set scope:Channel' to override.")
                else:
                    embed.add_field(name="Configuration Scope", value="⚙️ **System Fallback** (Google Gemini 2.5 Flash)", inline=False)
                    embed.set_footer(text="Use '/model set' to configure custom model for this channel or server.")

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to query backend engine: {e}")

    async def model_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        models = [
            # Google AI Studio - Gemini Family
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            # Google AI Studio - Gemma Family
            "gemma-4-26b-a4b-it",
            "gemma-4-31b-it",
            # DigitalOcean Gradient Models
            "kimi-k3",
            "glm-5.1",
            "glm-5.2",
            "deepseek-v4-pro",
            "deepseek-4-flash",
            "qwen3.5-397b-a17b",
            "llama3.3-70b-instruct",
            # Local & Kaggle
            "qwen3.5:4b",
            "qwen3.5-t4"
        ]
        return [
            app_commands.Choice(name=m, value=m)
            for m in models if current.lower() in m.lower()
        ][:25]

    @model_group.command(name="set", description="Set model tier and provider (per channel or permanent community default)")
    @app_commands.describe(
        tier="Choose Tier: 1 (Cloud Primary), 2 (Local Ollama), 3 (Kaggle T4)",
        provider="Select Provider: Google AI Studio, DigitalOcean, Ollama, Kaggle",
        scope="Set for this channel only or as the community server default",
        model_name="Optional custom model name (autocomplete available)"
    )
    @app_commands.choices(
        tier=[
            app_commands.Choice(name="Tier 1 (Cloud Primary: Google / DigitalOcean)", value=1),
            app_commands.Choice(name="Tier 2 (Local VPS: Ollama)", value=2),
            app_commands.Choice(name="Tier 3 (Batch GPU: Kaggle T4)", value=3),
        ],
        provider=[
            app_commands.Choice(name="Google AI Studio (Gemini / Gemma)", value="gemini"),
            app_commands.Choice(name="DigitalOcean Gradient", value="digitalocean"),
            app_commands.Choice(name="Local VPS (Ollama: qwen3.5:4b)", value="ollama"),
            app_commands.Choice(name="Batch GPU (Kaggle T4 Tunnel)", value="kaggle"),
        ],
        scope=[
            app_commands.Choice(name="Channel (This channel only)", value="channel"),
            app_commands.Choice(name="Server (Permanent Community Default)", value="server"),
        ]
    )
    @app_commands.autocomplete(model_name=model_name_autocomplete)
    async def model_set(
        self,
        interaction: discord.Interaction,
        tier: app_commands.Choice[int],
        provider: app_commands.Choice[str],
        scope: app_commands.Choice[str] = None,
        model_name: str = None
    ):
        await interaction.response.defer(thinking=True)

        # RBAC Check
        if not await check_admin_authorization(interaction):
            await interaction.followup.send(embed=make_denied_embed(), ephemeral=True)
            return

        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "dm"
        chosen_scope = scope.value if scope else "channel"
        user_name = interaction.user.display_name

        payload = {
            "channel_id": channel_id,
            "guild_id": guild_id,
            "scope": chosen_scope,
            "tier": tier.value,
            "provider": provider.value,
            "model_name": model_name,
            "updated_by": user_name
        }

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/model/set", json=payload)
                if res.status_code != 200:
                    err_detail = res.json().get("detail", res.text)
                    await interaction.followup.send(f"⚠️ Failed to update configuration: {err_detail}")
                    return

                data = res.json().get("data", {})
                active_model = data.get("model_name", model_name or "default")

                if chosen_scope == "server":
                    embed = discord.Embed(
                        title="🌐 Community Model Default Updated",
                        description=f"The entire server **{interaction.guild.name if interaction.guild else ''}** is now permanently configured to **Tier {tier.value}** via **{provider.name}**.",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="Server Default Model", value=f"`{active_model}`", inline=True)
                    embed.add_field(name="Configured By", value=f"@{user_name}", inline=True)
                    embed.set_footer(text="All server channels without specific overrides will inherit this model.")
                else:
                    embed = discord.Embed(
                        title="📌 Channel Model Override Set",
                        description=f"Channel <#{channel_id}> is now locked to **Tier {tier.value}** via **{provider.name}**.",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Channel Model", value=f"`{active_model}`", inline=True)
                    embed.add_field(name="Configured By", value=f"@{user_name}", inline=True)
                    embed.set_footer(text="Use '/model reset' to revert this channel back to community server defaults.")

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reach backend engine: {e}")

    @model_group.command(name="reset", description="Clear channel model override and revert to community server defaults")
    async def model_reset(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        if not await check_admin_authorization(interaction):
            await interaction.followup.send(embed=make_denied_embed(), ephemeral=True)
            return

        channel_id = str(interaction.channel_id)
        try:
            async with api_client(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/model/reset?channel_id={channel_id}")
                if res.status_code == 200:
                    embed = discord.Embed(
                        title="🔄 Channel Model Override Cleared",
                        description=f"Channel <#{channel_id}> has been reset and will now **inherit the community server default model**.",
                        color=discord.Color.teal()
                    )
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"⚠️ Failed to reset channel model: {res.text}")
        except Exception as e:
            await interaction.followup.send(f"❌ Error resetting model: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ModelSlash(bot))
