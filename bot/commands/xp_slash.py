import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.api import BACKEND_URL, api_client

class XPSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rank", description="Check your XP level and server rank")
    @app_commands.describe(user="Select user to view rank (optional)")
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer(thinking=True)
        target_user = user or interaction.user
        target_id = str(target_user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/xp/rank?user_id={target_id}&guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching rank: {res.text}")
                    return

                data = res.json()
                xp = data.get("xp", 0)
                level = data.get("level", 1)
                rank_num = data.get("rank", 1)

                embed = discord.Embed(
                    title=f"📊 Rank Card — {target_user.display_name}",
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=target_user.display_avatar.url)
                embed.add_field(name="Server Rank", value=f"**#{rank_num}**", inline=True)
                embed.add_field(name="Level", value=f"**Level {level}**", inline=True)
                embed.add_field(name="Total XP", value=f"**{xp} XP**", inline=True)

                next_level_xp = ((level) ** 2) * 100
                current_level_base = ((level - 1) ** 2) * 100 if level > 1 else 0
                needed = next_level_xp - current_level_base
                gained = xp - current_level_base
                percentage = min(max(gained / max(needed, 1), 0.0), 1.0)
                filled = int(percentage * 10)
                bar = "🟩" * filled + "⬜" * (10 - filled)

                embed.add_field(name="Level Progress", value=f"`{bar}` ({int(percentage * 100)}%)", inline=False)
                embed.set_footer(text=f"Messages: {data.get('messages_count', 0)} | Commands: {data.get('commands_used', 0)}")

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching rank: {e}")

    @app_commands.command(name="leaderboard", description="View top server members by XP")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/xp/leaderboard?guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching leaderboard: {res.text}")
                    return

                leaders = res.json().get("leaderboard", [])
                if not leaders:
                    await interaction.followup.send("🏆 No XP recorded for this server yet! Start chatting to earn XP.")
                    return

                embed = discord.Embed(
                    title="🏆 Server XP Leaderboard",
                    color=discord.Color.purple()
                )

                medals = ["🥇", "🥈", "🥉"]
                description_lines = []
                for i, item in enumerate(leaders):
                    prefix = medals[i] if i < 3 else f"**#{i+1}**"
                    name = item.get("display_name", "User")
                    lvl = item.get("level", 1)
                    xp_val = item.get("xp", 0)
                    description_lines.append(f"{prefix} **{name}** — Level {lvl} (`{xp_val} XP`)")

                embed.description = "\n".join(description_lines)
                embed.set_footer(text="Earn XP by sending messages, using commands, and winning trivia!")

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching leaderboard: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(XPSlash(bot))
