

import os
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class VoiceSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    voice_group = app_commands.Group(name="voice", description="Voice channel and TTS voice companion controls")

    @voice_group.command(name="join", description="Join your current voice channel")
    async def join_channel(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("⚠️ You are not in a voice channel!", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        try:
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(channel)
            else:
                await channel.connect()
            await interaction.response.send_message(f"🔊 Joined voice channel **#{channel.name}**")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to join voice channel: {e}", ephemeral=True)

    @voice_group.command(name="leave", description="Disconnect from the voice channel")
    async def leave_channel(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Disconnected from voice channel.")
        else:
            await interaction.response.send_message("⚠️ Bot is not in a voice channel.", ephemeral=True)

    @app_commands.command(name="tts", description="Generate high quality neural voice speech using Edge-TTS")
    @app_commands.describe(
        text="Text message to convert to voice",
        voice="Voice preset: christopher, ava, guy, sonia, brian"
    )
    @app_commands.choices(
        voice=[
            app_commands.Choice(name="Christopher (US Male)", value="christopher"),
            app_commands.Choice(name="Ava (US Female)", value="ava"),
            app_commands.Choice(name="Asad (Urdu Male)", value="asad"),
            app_commands.Choice(name="Uzma (Urdu Female)", value="uzma"),
            app_commands.Choice(name="Madhur (Hindi Male)", value="madhur"),
            app_commands.Choice(name="Hamed (Arabic Male)", value="hamed"),
            app_commands.Choice(name="Alvaro (Spanish Male)", value="alvaro"),
            app_commands.Choice(name="Henri (French Male)", value="henri"),
            app_commands.Choice(name="Keita (Japanese Male)", value="keita"),
        ]
    )
    async def speak_tts(
        self,
        interaction: discord.Interaction,
        text: str,
        voice: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)
        selected_voice = voice.value if voice else "christopher"

        payload = {
            "text": text,
            "voice": selected_voice
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/media/tts", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ TTS synthesis error: {res.text}")
                    return

                # Save temp audio file locally for Discord attachment upload
                import tempfile
                temp_audio_path = os.path.join(tempfile.gettempdir(), f"discord_tts_{os.urandom(4).hex()}.mp3")
                with open(temp_audio_path, "wb") as f:
                    f.write(res.content)

                discord_file = discord.File(temp_audio_path, filename="zauq_speech.mp3")
                await interaction.followup.send(
                    content=f"🔊 **TTS Speech** (`{selected_voice}`): \"{text[:100]}\"",
                    file=discord_file
                )
                try:
                    os.remove(temp_audio_path)
                except Exception:
                    pass

        except Exception as e:
            await interaction.followup.send(f"❌ Error generating TTS: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceSlash(bot))
