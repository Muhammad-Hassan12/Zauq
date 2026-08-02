import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class TriviaView(discord.ui.View):
    def __init__(self, correct_index: int, explanation: str, author_id: int):
        super().__init__(timeout=60.0)
        self.correct_index = correct_index
        self.explanation = explanation
        self.author_id = author_id

    async def _handle_answer(self, interaction: discord.Interaction, chosen_index: int):
        # Disable all buttons
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        if chosen_index == self.correct_index:
            embed = discord.Embed(
                title="🎉 Correct Answer!",
                description=f"**Congratulations @{interaction.user.name}!**\n\n💡 **Explanation:** {self.explanation}",
                color=discord.Color.green()
            )
        else:
            options_labels = ["A", "B", "C", "D"]
            correct_letter = options_labels[self.correct_index] if self.correct_index < len(options_labels) else str(self.correct_index + 1)
            embed = discord.Embed(
                title="❌ Incorrect!",
                description=f"Sorry @{interaction.user.name}, the correct answer was **Option {correct_letter}**.\n\n💡 **Explanation:** {self.explanation}",
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Option A", style=discord.ButtonStyle.primary, custom_id="btn_a")
    async def button_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 0)

    @discord.ui.button(label="Option B", style=discord.ButtonStyle.primary, custom_id="btn_b")
    async def button_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 1)

    @discord.ui.button(label="Option C", style=discord.ButtonStyle.primary, custom_id="btn_c")
    async def button_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 2)

    @discord.ui.button(label="Option D", style=discord.ButtonStyle.primary, custom_id="btn_d")
    async def button_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 3)

class TriviaSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="trivia", description="Start an interactive tech & server-lore trivia question")
    async def start_trivia(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/games/trivia?guild_id={guild_id}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Trivia Error: {res.text}")
                    return

                data = res.json()
                question = data.get("question", "Sample Question?")
                options = data.get("options", [])
                correct_index = data.get("correct_index", 0)
                explanation = data.get("explanation", "No explanation available.")

                embed = discord.Embed(
                    title="🎮 Zauq Trivia Time!",
                    description=f"**{question}**\n\n" + "\n".join([f"**{chr(65+i)}.** {opt}" for i, opt in enumerate(options)]),
                    color=discord.Color.gold()
                )
                embed.set_footer(text="Click a button below to lock in your answer within 60 seconds!")

                view = TriviaView(correct_index=correct_index, explanation=explanation, author_id=interaction.user.id)
                await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            await interaction.followup.send(f"❌ Error initiating trivia: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(TriviaSlash(bot))
