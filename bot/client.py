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
from bot.auth import check_admin_authorization, make_denied_embed
from bot.api import BACKEND_URL, api_client

setup_logging()
logger = logging.getLogger("zauq.bot")

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
            async with api_client(timeout=10.0) as client:
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

@bot.tree.command(name="mode", description="Switch operating mode (channel-specific or permanent community default)")
@app_commands.describe(
    mode="Operating mode: Dev (technical, low temp) or Hangout (casual, high temp)",
    scope="Set for this channel only or as the permanent community server default"
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Dev Mode (Technical, low temperature, code execution enabled)", value="dev"),
        app_commands.Choice(name="Hangout Mode (Casual, high temperature, creative companion)", value="hangout"),
    ],
    scope=[
        app_commands.Choice(name="Channel (This channel only)", value="channel"),
        app_commands.Choice(name="Server (Permanent Community Default)", value="server"),
    ]
)
async def mode_command(interaction: discord.Interaction, mode: app_commands.Choice[str], scope: app_commands.Choice[str] = None):
    await interaction.response.defer(thinking=True)

    if not await check_admin_authorization(interaction):
        await interaction.followup.send(embed=make_denied_embed(), ephemeral=True)
        return

    channel_id = str(interaction.channel_id)
    guild_id = str(interaction.guild_id) if interaction.guild_id else "dm"
    chosen_scope = scope.value if scope else "channel"

    try:
        async with api_client(timeout=10.0) as client:
            payload = {
                "channel_id": channel_id,
                "guild_id": guild_id,
                "scope": chosen_scope,
                "operating_mode": mode.value
            }
            res = await client.post(f"{BACKEND_URL}/api/chat/profile", json=payload)
            if res.status_code == 200:
                if chosen_scope == "server":
                    embed = discord.Embed(
                        title="🌐 Community Default Mode Set",
                        description=f"The entire server **{interaction.guild.name if interaction.guild else ''}** is now permanently set to **{mode.name}**.",
                        color=discord.Color.gold()
                    )
                    embed.set_footer(text="All server channels without specific overrides will inherit this mode.")
                else:
                    embed = discord.Embed(
                        title="📌 Channel Mode Override Set",
                        description=f"Channel <#{channel_id}> is now locked to **{mode.name}**.",
                        color=discord.Color.green()
                    )
                    embed.set_footer(text="Use '/mode_reset' to revert this channel back to community server defaults.")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(f"⚠️ Channel mode set to **{mode.name}** (warning: {res.text})")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to set mode: {e}")

@bot.tree.command(name="mode_reset", description="Clear channel mode override and revert to community server defaults")
async def mode_reset_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    if not await check_admin_authorization(interaction):
        await interaction.followup.send(embed=make_denied_embed(), ephemeral=True)
        return

    channel_id = str(interaction.channel_id)
    try:
        async with api_client(timeout=10.0) as client:
            res = await client.post(f"{BACKEND_URL}/api/chat/profile/reset?channel_id={channel_id}")
            if res.status_code == 200:
                embed = discord.Embed(
                    title="🔄 Channel Mode Override Cleared",
                    description=f"Channel <#{channel_id}> has been reset and will now **inherit the community server default mode**.",
                    color=discord.Color.teal()
                )
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(f"⚠️ Failed to reset channel mode: {res.text}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error resetting channel mode: {e}")

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
            "bot.commands.file_slash",
            "bot.commands.info_slash",
            "bot.commands.thinking_slash"
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
        bot._reminder_task = asyncio.create_task(reminder_polling_loop())

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
        async with api_client(timeout=5.0) as client:
            await client.post(
                f"{BACKEND_URL}/api/xp/award?user_id={message.author.id}&guild_id={guild_id}&display_name={message.author.display_name}&xp=1&stat_type=message"
            )
    except Exception:
        pass

    # 2. Check if message warrants bot response (Mention, DM, Thread, or Direct Reply to Bot)
    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_thread = isinstance(message.channel, discord.Thread)

    is_reply_to_bot = False
    if message.reference:
        if getattr(message.reference, "resolved", None) and isinstance(message.reference.resolved, discord.Message):
            is_reply_to_bot = (message.reference.resolved.author.id == bot.user.id)
        elif message.reference.message_id:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                if ref_msg and ref_msg.author.id == bot.user.id:
                    is_reply_to_bot = True
            except Exception:
                pass

    if not (is_mentioned or is_dm or is_thread or is_reply_to_bot):
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

    # 2. Ingest Replied-to Reference Message (if this message is a Reply)
    ref_context_parts = []
    if message.reference:
        ref_msg = None
        if getattr(message.reference, "resolved", None) and isinstance(message.reference.resolved, discord.Message):
            ref_msg = message.reference.resolved
        elif message.reference.message_id:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
            except Exception as ref_err:
                logger.debug(f"Could not fetch referenced message {message.reference.message_id}: {ref_err}")

        if ref_msg:
            ref_author = ref_msg.author.display_name
            ref_text = ref_msg.content or ""

            # Extract content and URLs from embeds inside the referenced message
            for emb in ref_msg.embeds:
                if emb.url and emb.url not in ref_text:
                    ref_text += f"\n{emb.url}"
                if emb.title:
                    ref_text += f"\n{emb.title}"
                if emb.description:
                    ref_text += f"\n{emb.description}"

            if ref_text.strip():
                ref_context_parts.append(f"[Replied to @{ref_author}'s message:\n\"{ref_text.strip()}\"]")

            # Extract attachments from referenced message (images, audio, docs)
            if ref_msg.attachments:
                for att in ref_msg.attachments[:3]:
                    try:
                        if att.size <= 10 * 1024 * 1024:
                            att_bytes = await att.read()
                            b64_str = base64.b64encode(att_bytes).decode("utf-8")
                            ext = os.path.splitext(att.filename.lower())[1]
                            mime = att.content_type or ""
                            if ext in AUDIO_EXTENSIONS or mime.startswith("audio/"):
                                is_voice_input = True
                            attachments_payload.append({
                                "filename": f"replied_{att.filename}",
                                "content_type": mime,
                                "bytes_b64": b64_str
                            })
                    except Exception as ref_att_err:
                        logger.warning(f"Failed to read referenced attachment {att.filename}: {ref_att_err}")

    # 3. Ingest Forwarded Message Snapshots (Discord message forwards)
    if hasattr(message, "message_snapshots") and message.message_snapshots:
        for snapshot in message.message_snapshots:
            if getattr(snapshot, "content", None):
                ref_context_parts.append(f"[Forwarded message content:\n\"{snapshot.content.strip()}\"]")
            for att in getattr(snapshot, "attachments", [])[:3]:
                try:
                    if att.size <= 10 * 1024 * 1024:
                        att_bytes = await att.read()
                        b64_str = base64.b64encode(att_bytes).decode("utf-8")
                        attachments_payload.append({
                            "filename": f"forwarded_{att.filename}",
                            "content_type": att.content_type or "",
                            "bytes_b64": b64_str
                        })
                except Exception as snap_err:
                    logger.warning(f"Failed to read forwarded attachment: {snap_err}")

    if ref_context_parts:
        content = "\n\n".join(ref_context_parts) + f"\n\n[User's reply]: {content}"

    # If user sent a voice note without a text caption
    if not content:
        content = "[Voice Note Audio Input]" if is_voice_input else "Hello!"

    # 4. AI Moderation Check
    if message.guild and content != "[Voice Note Audio Input]":
        try:
            mod_payload = {
                "guild_id": str(message.guild.id),
                "channel_id": str(message.channel.id),
                "user_id": str(message.author.id),
                "message_content": content
            }
            async with api_client(timeout=5.0) as client:
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
    wants_thread = any(kw in content.lower() for kw in ["start a thread", "in a thread", "make a thread", "thread:"])

    # Spawn a Discord Thread only if explicitly requested by the user
    if wants_thread and not is_thread and not is_dm:
        try:
            thread_name = f"Zauq Chat - {message.author.display_name[:15]}"
            target_channel = await message.create_thread(name=thread_name, auto_archive_duration=60)
            initial_msg = await target_channel.send("💭 *Thinking...*")
        except Exception as e:
            logger.warning(f"Could not spawn requested thread: {e}")
            try:
                initial_msg = await message.reply("💭 *Thinking...*", mention_author=False)
            except Exception:
                initial_msg = await target_channel.send("💭 *Thinking...*")
    else:
        # Default: Clean in-channel reply without creating unwanted threads
        try:
            initial_msg = await message.reply("💭 *Thinking...*", mention_author=False)
        except Exception:
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

    stop_heartbeat = asyncio.Event()

    async def _progress_heartbeat(target_msg, stop_ev: asyncio.Event):
        elapsed = 0
        while not stop_ev.is_set():
            try:
                await asyncio.sleep(15)
                if stop_ev.is_set():
                    break
                elapsed += 15
                if elapsed < 30:
                    status_text = f"⚡ *Analyzing input & planning architecture... ({elapsed}s)*"
                elif elapsed < 90:
                    status_text = f"🧠 *Generating full code / notebook cells... ({elapsed}s)*"
                elif elapsed < 180:
                    status_text = f"📦 *Structuring training loops, models & Grad-CAM... ({elapsed}s)*"
                else:
                    status_text = f"📦 *Finalizing code and packaging files... ({elapsed}s)*"
                await target_msg.edit(content=status_text)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    heartbeat_task = asyncio.create_task(_progress_heartbeat(initial_msg, stop_heartbeat))

    try:
        async with api_client(timeout=600.0) as client:
            res = await client.post(f"{BACKEND_URL}/api/chat", json=chat_payload)
            stop_heartbeat.set()
            heartbeat_task.cancel()

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

            # Fallback notification — inform user when their configured provider failed
            # and Gemini Flash was substituted automatically
            if res_data.get("fallback_triggered"):
                original_provider = res_data.get("original_provider", "unknown").upper()
                original_model = res_data.get("original_model", "unknown")
                fallback_embed = discord.Embed(
                    title="⚠️ Provider Fallback Activated",
                    description=(
                        f"Your configured provider **{original_provider}** "
                        f"(`{original_model}`) was unreachable or returned an error.\n\n"
                        f"This response was generated by **Gemini 2.5 Flash** as an automatic fallback "
                        f"to ensure zero interruption."
                    ),
                    color=discord.Color.orange()
                )
                fallback_embed.set_footer(
                    text="Use /model set to reconfigure your provider, or check if it's online."
                )
                try:
                    await target_channel.send(embed=fallback_embed)
                except Exception as fb_err:
                    logger.warning(f"Could not send fallback notification embed: {fb_err}")

    except httpx.TimeoutException:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        logger.error("Request to backend engine timed out after 600s.")
        try:
            await initial_msg.edit(
                content="⏳ **Generation Timed Out**: The request took longer than 10 minutes to complete. "
                        "Please try breaking the request into smaller modules or switch to Gemini Flash via `/model set provider:gemini model:gemini-2.5-flash`!"
            )
        except Exception:
            pass
    except Exception as e:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        err_msg = str(e) if str(e).strip() else (repr(e) or type(e).__name__)
        logger.error(f"Error communicating with Zauq engine: {e}", exc_info=True)
        try:
            await initial_msg.edit(content=f"❌ Error communicating with Zauq engine: {err_msg}")
        except Exception:
            pass
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()

if __name__ == "__main__":
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        logger.error("❌ DISCORD_BOT_TOKEN is not set in environment.")
    else:
        bot.run(token)
