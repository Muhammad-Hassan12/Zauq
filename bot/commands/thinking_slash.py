import discord
from discord import app_commands
from discord.ext import commands
from bot.auth import check_admin_authorization, make_denied_embed
from bot.api import BACKEND_URL, api_client


class ThinkingSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="thinking",
        description="Toggle deep-thinking/reasoning mode for this channel across all AI models (admin only)"
    )
    @app_commands.describe(
        mode="Turn extended deep-thinking reasoning on or off for this channel",
        scope="Apply to this channel only (default) or the entire server"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="🧠 On  — Enable deep reasoning (slower, more thorough)", value="on"),
            app_commands.Choice(name="⚡ Off — Disable thinking mode (faster, standard output)", value="off"),
        ],
        scope=[
            app_commands.Choice(name="Channel (This channel only)", value="channel"),
        ]
    )
    async def thinking_command(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        scope: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)

        # RBAC check — admins only, consistent with /mode and /model set
        if not await check_admin_authorization(interaction):
            await interaction.followup.send(embed=make_denied_embed(), ephemeral=True)
            return

        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "dm"
        thinking_on = (mode.value == "on")

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.post(
                    f"{BACKEND_URL}/api/chat/thinking",
                    json={
                        "channel_id": channel_id,
                        "guild_id": guild_id,
                        "thinking_enabled": thinking_on
                    }
                )

                if res.status_code != 200:
                    await interaction.followup.send(
                        f"⚠️ Failed to update thinking mode: {res.text}", ephemeral=True
                    )
                    return

                if thinking_on:
                    embed = discord.Embed(
                        title="🧠 Deep Thinking Mode Enabled",
                        description=(
                            f"Channel <#{channel_id}> will now use **extended reasoning** "
                            f"for all AI models (Gemini, DigitalOcean, Ollama, Kaggle).\n\n"
                            f"Zauq will analyze problems step-by-step and reason deeply before answering — "
                            f"expect **higher quality, more thorough** replies for complex tasks.\n\n"
                            f"> ⚡ Extended token budget: **16k–65k tokens** allocated for reasoning"
                        ),
                        color=discord.Color.purple()
                    )
                    embed.set_footer(
                        text="Active for all models. Use /thinking mode:off to disable."
                    )
                else:
                    embed = discord.Embed(
                        title="⚡ Thinking Mode Disabled",
                        description=(
                            f"Channel <#{channel_id}> is back to **standard output mode**.\n\n"
                            f"Responses will be faster. Deep reasoning is off."
                        ),
                        color=discord.Color.greyple()
                    )
                    embed.set_footer(
                        text="Use /thinking mode:on to re-enable extended reasoning."
                    )

                embed.add_field(name="Configured By", value=f"@{interaction.user.display_name}", inline=True)
                embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reach backend engine: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ThinkingSlash(bot))
