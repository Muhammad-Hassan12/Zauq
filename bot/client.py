import sys
import os

# Ensure project root is in Python path when executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.stream_buffer import split_message_chunks

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Zauq Discord Bot online as {bot.user} (ID: {bot.user.id})")
    try:
        # Load slash command cogs
        cogs = [
            "bot.commands.model_slash",
            "bot.commands.remember_slash",
            "bot.commands.exec_slash",
            "bot.commands.github_slash",
            "bot.commands.voice_slash",
            "bot.commands.meme_slash",
            "bot.commands.trivia_slash",
            "bot.commands.stats_slash",
            "bot.commands.privacy_slash",
            "bot.commands.image_slash"
        ]
        for cog in cogs:
            try:
                await bot.load_extension(cog)
            except Exception as cog_err:
                print(f"[Bot Warning] Could not load extension {cog}: {cog_err}")

        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands with Discord Gateway.")
    except Exception as e:
        print(f"⚠️ Failed to sync slash commands: {e}")

@bot.tree.command(name="mode", description="Switch channel operating mode (dev | hangout)")
@app_commands.describe(mode="Operating mode for this channel: 'dev' or 'hangout'")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Dev Mode (Technical, low temperature)", value="dev"),
        app_commands.Choice(name="Hangout Mode (Casual, high temperature)", value="hangout"),
    ]
)
async def mode_command(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    await interaction.response.defer(thinking=True)
    channel_id = str(interaction.channel_id)
    guild_id = str(interaction.guild_id) if interaction.guild_id else "dm"

    # Call backend to update channel profile in database
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {
                "channel_id": channel_id,
                "guild_id": guild_id,
                "operating_mode": mode.value
            }
            res = await client.post(f"{BACKEND_URL}/api/chat/profile", json=payload)
            if res.status_code == 200:
                await interaction.followup.send(f"✅ Channel mode set to **{mode.name}** and saved to channel profile.")
            else:
                await interaction.followup.send(f"⚠️ Channel mode set to **{mode.name}** (warning: {res.text})")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to set mode: {e}")

@bot.event
async def on_message(message: discord.Message):
    # Ignore messages sent by the bot itself
    if message.author == bot.user or message.author.bot:
        return

    # Check if bot is mentioned or if message is in a DM / Thread
    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_thread = isinstance(message.channel, discord.Thread)

    if not (is_mentioned or is_dm or is_thread):
        return

    # Extract user query (strip mention if tagged)
    content = message.content
    if bot.user:
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

    if not content:
        content = "Hello!"

    # Target channel/thread for output
    target_channel = message.channel

    # Auto-spawn a Discord Thread if multi-turn conversation starts in a standard channel
    if not is_thread and not is_dm:
        try:
            thread_name = f"Zauq Chat - {message.author.display_name[:15]}"
            target_channel = await message.create_thread(name=thread_name, auto_archive_duration=60)
        except Exception as e:
            print(f"[Bot Warning] Could not spawn thread: {e}")

    # Send initial placeholder message
    initial_msg = await target_channel.send("💭 *Thinking...*")

    # Fetch extended history context (last 15 messages for full context memory)
    history_messages = []
    try:
        async for past_msg in target_channel.history(limit=15, oldest_first=False):
            if past_msg.id == initial_msg.id:
                continue
            role = "assistant" if past_msg.author == bot.user else "user"
            msg_text = past_msg.content.replace(f"<@{bot.user.id}>", "").strip()
            if msg_text and not msg_text.startswith("💭 *Thinking...*"):
                history_messages.append({"role": role, "content": msg_text})
        history_messages.reverse()
    except Exception as e:
        print(f"[Bot Warning] History fetch failed: {e}")

    if not history_messages:
        history_messages = [{"role": "user", "content": content}]

    # Process Discord attachments (up to 3 files)
    attachments_payload = []
    if message.attachments:
        import base64
        for att in message.attachments[:3]:
            try:
                att_bytes = await att.read()
                b64_str = base64.b64encode(att_bytes).decode("utf-8")
                attachments_payload.append({
                    "filename": att.filename,
                    "content_type": att.content_type or "",
                    "bytes_b64": b64_str
                })
            except Exception as att_err:
                print(f"[Bot Warning] Failed to read attachment {att.filename}: {att_err}")

    # Send request to FastAPI backend
    chat_payload = {
        "channel_id": str(message.channel.id),
        "guild_id": str(message.guild.id) if message.guild else None,
        "user_id": str(message.author.id),
        "user_name": message.author.name,
        "messages": history_messages,
        "attachments": attachments_payload
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(f"{BACKEND_URL}/api/chat", json=chat_payload)
            if res.status_code != 200:
                await initial_msg.edit(content=f"❌ Backend Error ({res.status_code}): {res.text}")
                return

            full_response = res.json().get("response", "")
            chunks = split_message_chunks(full_response, max_length=1900)

            # Single-shot edit of initial message with first chunk
            await initial_msg.edit(content=chunks[0])

            # Send remaining chunks as sequential follow-up messages
            for follow_up_chunk in chunks[1:]:
                await target_channel.send(content=follow_up_chunk)

    except Exception as e:
        await initial_msg.edit(content=f"❌ Error communicating with Zauq engine: {str(e)}")

if __name__ == "__main__":
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        print("❌ DISCORD_BOT_TOKEN is not set in environment.")
    else:
        bot.run(token)
