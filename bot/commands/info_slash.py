import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from backend.version import ZAUQ_VERSION
from bot.api import BACKEND_URL, api_client

PROVIDER_DISPLAY_NAMES = {
    "gemini": "Google AI Studio",
    "google": "Google AI Studio",
    "digitalocean": "DigitalOcean Gradient",
    "do": "DigitalOcean Gradient",
    "ollama": "Local VPS Ollama",
    "kaggle": "Kaggle T4 Tunnel"
}

class InfoSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="View complete live specifications, active model, mode, and engine parameters")
    async def info_command(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "dm"

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/model/info?channel_id={channel_id}&guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Failed to fetch system info ({res.status_code}): {res.text}")
                    return

                data = res.json()
                engine = data.get("engine", {})
                model = data.get("model", {})
                persona = data.get("persona", {})
                limits = data.get("limits", {})
                caps = data.get("capabilities", {})

                provider_raw = model.get("provider", "gemini").lower()
                provider_name = PROVIDER_DISPLAY_NAMES.get(provider_raw, provider_raw.title())
                model_name = model.get("model_name", "gemini-2.5-flash")
                tier = model.get("tier", 1)

                scope_badge = "⚙️ System Fallback"
                if model.get("is_channel_override"):
                    scope_badge = "📌 Channel-Specific Override"
                elif model.get("is_server_default"):
                    scope_badge = "🌐 Community Server Default"

                mode_name = persona.get("mode", "hangout")
                mode_badge = "🛠️ Dev Mode" if mode_name == "dev" else "💬 Hangout Mode"
                temp = persona.get("temperature", 0.85)
                exec_badge = "✅ Enabled (Docker Sandbox)" if persona.get("allow_code_exec") else "❌ Disabled"
                thinking_badge = "🧠 Requested (model dependent)" if persona.get("thinking_enabled") else "⚡ Disabled"

                embed = discord.Embed(
                    title="🤖 Zauq (ذوق) — System Specifications & Active Configuration",
                    description=(
                        f"**Engine:** `{engine.get('name', 'Zauq')}` v`{engine.get('version', ZAUQ_VERSION)}` • `{engine.get('license', 'Apache 2.0')}`\n"
                        f"**Architect:** `{engine.get('creator', 'Syed Muhammad Hassan / AgenticEra Systems')}`\n"
                        f"**Channel:** <#{channel_id}>"
                    ),
                    color=discord.Color.teal() if mode_name == "dev" else discord.Color.blue()
                )

                # 1. Active Model & Routing
                model_field_val = (
                    f"• **Tier:** Tier {tier}\n"
                    f"• **Provider:** {provider_name}\n"
                    f"• **Active Model:** `{model_name}`\n"
                    f"• **Scope:** {scope_badge}"
                )
                embed.add_field(name="⚡ Active Model & Routing", value=model_field_val, inline=False)

                # 2. Operating Persona & Execution
                persona_field_val = (
                    f"• **Mode:** {mode_badge}\n"
                    f"• **Temperature:** `{temp}` ({'Deterministic' if temp <= 0.3 else 'Creative/Witty'})\n"
                    f"• **Thinking Mode:** {thinking_badge}\n"
                    f"• **Code Execution:** {exec_badge}"
                )
                embed.add_field(name="🎭 Persona & Execution", value=persona_field_val, inline=False)

                # 3. Context Windows & Hardware Sandbox Limits
                limits_field_val = (
                    f"• **Input Capacity:** `{limits.get('input_tokens_max', 30000):,} Tokens` (~120k chars)\n"
                    f"• **Output Generation:** `{limits.get('output_tokens_max', 65536):,} Tokens` (~250k chars)\n"
                    f"• **Working Context:** Last `{limits.get('history_window', 8)} messages`\n"
                    f"• **Sandbox Bounds:** `{limits.get('sandbox_timeout_s', settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS)}s timeout` • `{limits.get('sandbox_memory', '256m')}` • `{limits.get('sandbox_cpus', '0.5')} CPU`"
                )
                embed.add_field(name="📊 Context, Memory & Sandbox Bounds", value=limits_field_val, inline=False)

                # 4. Intelligence & Media Subsystems
                caps_field_val = (
                    f"• **Web Search:** {caps.get('web_search', 'Deep Web Roaming')}\n"
                    f"• **Voice TTS:** {caps.get('voice_tts', 'Edge Neural TTS')}\n"
                    f"• **Image Gen:** {caps.get('image_generation', 'Gemini Flash Image')}\n"
                    f"• **Vector Memory:** {caps.get('memory', 'L1/L2/L3 pgvector')}\n"
                    f"• **SSRF Protection:** {caps.get('ssrf_protection', 'Active')}"
                )
                embed.add_field(name="🌐 Intelligence Subsystems", value=caps_field_val, inline=False)

                embed.set_footer(text="Zauq Engine • Use '/model set' or '/mode' to modify configurations.")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error communicating with backend: {str(e)}")

async def setup(bot: commands.Bot):
    await bot.add_cog(InfoSlash(bot))
