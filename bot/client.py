import io
import os
import zipfile
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

AUDIO_EXTENSIONS = {".ogg", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".opus", ".webm", ".oga"}

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

@bot.command(name="sync")
async def sync_slash_commands(ctx):
    """Instant slash command sync to current Discord server."""
    status_msg = await ctx.send("🔄 *Syncing 23 slash commands with Discord Gateway...*")
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        guild_synced = await bot.tree.sync(guild=ctx.guild)
        global_synced = await bot.tree.sync()
        await status_msg.edit(
            content=f"✅ **Slash Commands Synced Instantly!**\n"
                    f"• Synced **{len(guild_synced)}** commands directly to **{ctx.guild.name}**\n"
                    f"• Synced **{len(global_synced)}** global commands\n"
                    f"*Commands `/search`, `/file generate`, and `/create_file` are now live in your menu!*"
        )
    except Exception as e:
        await status_msg.edit(content=f"❌ Slash sync failed: {str(e)}")

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
            "bot.commands.admin_slash",
            "bot.commands.search_slash",
            "bot.commands.file_slash"
        ]
        for cog in cogs:
            try:
                await bot.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as cog_err:
                logger.warning(f"Could not load extension {cog}: {cog_err}")

        # Load community plugins if any present
        await load_plugins(bot)

        # Global sync
        synced = await bot.tree.sync()
        logger.info(f"✅ Synced {len(synced)} global slash commands with Discord Gateway.")

        # Immediate Guild Sync for zero propagation latency
        for g in bot.guilds:
            try:
                bot.tree.copy_global_to(guild=g)
                g_synced = await bot.tree.sync(guild=g)
                logger.info(f"✅ Instantly synced {len(g_synced)} commands to Guild: {g.name} ({g.id})")
            except Exception as g_err:
                logger.warning(f"Guild sync skipped for {g.id}: {g_err}")

        # Start reminder polling worker
        asyncio.create_task(reminder_polling_loop())

    except Exception as e:
        logger.error(f"Failed during bot startup: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or message.author.bot:
        return

    # Allow prefix commands like !sync to execute
    await bot.process_commands(message)

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

    # If it was a prefix command like !sync, don't trigger AI response
    if message.content.startswith("!"):
        return

    # Extract user query (strip mention if tagged)
    content = message.content
    if bot.user:
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

    # Process attachments (Images, Audio/Voice Notes, Documents)
    attachments_payload = []
    is_voice_input = False

    if message.attachments:
        for att in message.attachments[:4]:
            try:
                if att.size > 10 * 1024 * 1024:
                    logger.warning(f"Attachment {att.filename} exceeds 10MB limit. Skipping.")
                    continue

                att_bytes = await att.read()
                b64_str = base64.b64encode(att_bytes).decode("utf-8")
                ext = os.path.splitext(att.filename.lower())[1]
                mime = att.content_type or ""

                if ext in AUDIO_EXTENSIONS or mime.startswith("audio/"):
                    is_voice_input = True

                attachments_payload.append({
                    "filename": att.filename,
                    "content_type": mime,
                    "bytes_b64": b64_str
                })
            except Exception as att_err:
                logger.warning(f"Failed to read attachment {att.filename}: {att_err}")

    # If user sent a voice note without a text caption
    if not content:
        content = "[Voice Note Audio Input]" if is_voice_input else "Hello!"

    # 3. AI Moderation Check
    if message.guild and content != "[Voice Note Audio Input]":
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
        async with httpx.AsyncClient(timeout=180.0) as client:
            res = await client.post(f"{BACKEND_URL}/api/chat", json=chat_payload)
            if res.status_code != 200:
                await initial_msg.edit(content=f"❌ Backend Error ({res.status_code}): {res.text}")
                return

            res_data = res.json()
            full_response = res_data.get("response", "")
            files_payload = res_data.get("files", [])

            # Package generated files as Discord attachments
            discord_files = []
            if files_payload:
                for f_item in files_payload:
                    try:
                        raw_file_bytes = base64.b64decode(f_item["bytes_b64"])
                        discord_files.append(discord.File(io.BytesIO(raw_file_bytes), filename=f_item["filename"]))
                    except Exception as f_err:
                        logger.warning(f"Failed to prepare file {f_item.get('filename')}: {f_err}")

                # If 2 or more files generated, also bundle into a .zip archive
                if len(files_payload) >= 2:
                    try:
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                            for f_item in files_payload:
                                zip_file.writestr(f_item["filename"], base64.b64decode(f_item["bytes_b64"]))
                        zip_buffer.seek(0)
                        discord_files.append(discord.File(zip_buffer, filename="project_files.zip"))
                    except Exception as zip_err:
                        logger.warning(f"Failed to create project zip bundle: {zip_err}")

            # Optional Voice Response Attachment for Voice Input in Hangout Mode
            if is_voice_input and res_data.get("mode") == "hangout" and full_response:
                try:
                    tts_text = full_response[:300]
                    tts_res = await client.post(f"{BACKEND_URL}/api/media/tts", json={"text": tts_text, "voice": "christopher"})
                    if tts_res.status_code == 200:
                        discord_files.append(discord.File(io.BytesIO(tts_res.content), filename="zauq_voice_reply.mp3"))
                except Exception as tts_err:
                    logger.info(f"Voice reply synthesis skipped: {tts_err}")

            chunks = split_message_chunks(full_response, max_length=1900)

            # Edit initial message with first chunk
            await initial_msg.edit(content=chunks[0])

            # Send remaining text chunks
            for follow_up_chunk in chunks[1:]:
                await target_channel.send(content=follow_up_chunk)

            # Attach generated files / zip bundle / audio reply
            if discord_files:
                try:
                    await target_channel.send(content="📎 **Download Generated File(s):**", files=discord_files)
                except Exception as upload_err:
                    logger.error(f"Failed to send Discord file attachments: {upload_err}")
                    await target_channel.send(content=f"⚠️ *File attachment upload failed: {upload_err}*")

    except Exception as e:
        await initial_msg.edit(content=f"❌ Error communicating with Zauq engine: {str(e)}")

if __name__ == "__main__":
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        logger.error("❌ DISCORD_BOT_TOKEN is not set in environment.")
    else:
        bot.run(token)
