import asyncio
import logging
import base64
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from backend.logging_config import setup_logging
from bot.stream_buffer import split_message_chunks, compress_assistant_history
from bot.plugins import load_plugins

setup_logging()
logger = logging.getLogger("zauq.bot")

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def reminder_polling_loop():
    """Background worker that polls pending reminders every 30 seconds and posts to Discord."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await asyncio.sleep(30)
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/reminders/pending")
                if res.status_code == 200:
                    reminders = res.json().get("reminders", [])
                    for rem in reminders:
                        rem_id = rem.get("reminder_id")
                        channel_id = rem.get("channel_id")
                        user_id = rem.get("user_id")
                        msg_text = rem.get("message")

                        channel = bot.get_channel(int(channel_id)) if channel_id and channel_id.isdigit() else None
                        if channel:
                            embed = discord.Embed(
                                title="⏰ Reminder Alert!",
                                description=f"<@{user_id}>, you asked me to remind you:\n\n\"{msg_text}\"",
                                color=discord.Color.gold()
                            )
                            await channel.send(content=f"<@{user_id}>", embed=embed)

                        # Mark as delivered
                        await client.post(f"{BACKEND_URL}/api/reminders/mark_delivered?reminder_id={rem_id}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in reminder polling loop: {e}")

@bot.event
async def on_ready():
    logger.info(f"🤖 Zauq Discord Bot online as {bot.user} (ID: {bot.user.id})")
    try:
        # Load core slash command cogs
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
            "bot.commands.image_slash",
            "bot.commands.summarize_slash",
            "bot.commands.remind_slash",
            "bot.commands.export_slash",
            "bot.commands.xp_slash",
            "bot.commands.moderation_slash",
            "bot.commands.admin_slash"
        ]
        for cog in cogs:
            try:
                await bot.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as cog_err:
                logger.warning(f"Could not load extension {cog}: {cog_err}")

        # Load community plugins if any present
        await load_plugins(bot)

        synced = await bot.tree.sync()
        logger.info(f"✅ Synced {len(synced)} slash commands with Discord Gateway.")

        # Start reminder polling worker
        asyncio.create_task(reminder_polling_loop())

    except Exception as e:
        logger.error(f"Failed during bot startup: {e}")

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
    if message.author == bot.user or message.author.bot:
        return

    # 1. Award XP for message participation
    try:
        guild_id = str(message.guild.id) if message.guild else "dm"
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{BACKEND_URL}/api/xp/award?user_id={message.author.id}&guild_id={guild_id}&display_name={message.author.display_name}&xp=1&stat_type=message"
            )
    except Exception:
        pass

    # 2. Check if message warrants bot response (Mention, DM, or Thread)
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

    # 3. AI Moderation Check
    if message.guild:
        try:
            mod_payload = {
                "guild_id": str(message.guild.id),
                "channel_id": str(message.channel.id),
                "user_id": str(message.author.id),
                "message_content": content
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                mod_res = await client.post(f"{BACKEND_URL}/api/moderation/check", json=mod_payload)
                if mod_res.status_code == 200:
                    mod_data = mod_res.json()
                    if mod_data.get("action") == "delete":
                        try:
                            await message.delete()
                            await message.author.send("⚠️ Your message was removed automatically for violating community content guidelines.")
                        except Exception:
                            pass
                        return
        except Exception:
            pass

    target_channel = message.channel

    # Auto-spawn a Discord Thread if multi-turn conversation starts in a standard channel
    if not is_thread and not is_dm:
        try:
            thread_name = f"Zauq Chat - {message.author.display_name[:15]}"
            target_channel = await message.create_thread(name=thread_name, auto_archive_duration=60)
        except Exception as e:
            logger.warning(f"Could not spawn thread: {e}")

    initial_msg = await target_channel.send("💭 *Thinking...*")

    # Fetch history context (last 8 messages)
    history_messages = []
    total_history_len = 0
    try:
        async for past_msg in target_channel.history(limit=8, oldest_first=False):
            if past_msg.id == initial_msg.id or past_msg.id == message.id:
                continue
            role = "assistant" if past_msg.author == bot.user else "user"
            msg_text = past_msg.content.replace(f"<@{bot.user.id}>", "").strip()
            if msg_text and not msg_text.startswith("💭 *Thinking...*"):
                if role == "assistant":
                    msg_text = compress_assistant_history(msg_text)
                
                if total_history_len + len(msg_text) > 10000:
                    break
                total_history_len += len(msg_text)

                history_messages.append({"role": role, "content": msg_text})
        history_messages.reverse()
    except Exception as e:
        logger.warning(f"History fetch failed: {e}")

    history_messages.append({"role": "user", "content": content[:10000]})

    # Process attachments
    attachments_payload = []
    if message.attachments:
        for att in message.attachments[:3]:
            try:
                if att.size > 5 * 1024 * 1024:
                    logger.warning(f"Attachment {att.filename} exceeds 5MB limit. Skipping.")
                    continue

                att_bytes = await att.read()
                b64_str = base64.b64encode(att_bytes).decode("utf-8")
                attachments_payload.append({
                    "filename": att.filename,
                    "content_type": att.content_type or "",
                    "bytes_b64": b64_str
                })
            except Exception as att_err:
                logger.warning(f"Failed to read attachment {att.filename}: {att_err}")

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

            await initial_msg.edit(content=chunks[0])

            for follow_up_chunk in chunks[1:]:
                await target_channel.send(content=follow_up_chunk)

    except Exception as e:
        await initial_msg.edit(content=f"❌ Error communicating with Zauq engine: {str(e)}")

if __name__ == "__main__":
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        logger.error("❌ DISCORD_BOT_TOKEN is not set in environment.")
    else:
        bot.run(token)
