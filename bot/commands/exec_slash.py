import os
import re
import io
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Tuple
from backend.config import settings
from bot.api import BACKEND_URL, api_client

def extract_code_and_lang(text: str) -> Tuple[str, str]:
    """
    Extracts code block and detected language from markdown code fences.
    Returns (code_string, language).
    """
    if not text:
        return ("", "python")

    # Match ```language\n code ```
    pattern = r"```([a-zA-Z0-9_-]*)\n?(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        raw_lang = match.group(1).lower().strip()
        code = match.group(2).strip()

        if raw_lang in ["python", "py", "python3"]:
            lang = "python"
        elif raw_lang in ["javascript", "js", "node", "typescript", "ts"]:
            lang = "javascript"
        elif raw_lang in ["bash", "sh", "shell", "zsh"]:
            lang = "bash"
        else:
            lang = "python"

        return (code, lang)

    return (text.strip(), "python")

async def execute_and_send_result(
    interaction: discord.Interaction,
    code: str,
    language: str,
    channel_id: str
):
    """Executes code in Docker sandbox and sends formatted Discord embed results."""
    payload = {
        "code": code,
        "language": language,
        "timeout": 5.0,
        "channel_id": channel_id,
        "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
    }

    try:
        async with api_client(timeout=15.0) as client:
            res = await client.post(f"{BACKEND_URL}/api/sandbox/exec", json=payload)
            if res.status_code != 200:
                await interaction.followup.send(f"⚠️ Sandbox Error ({res.status_code}): {res.text}")
                return

            data = res.json()
            success = data.get("success", False)
            stdout = data.get("stdout", "").strip()
            stderr = data.get("stderr", "").strip()
            duration = data.get("execution_time_ms", 0)
            exit_code = data.get("exit_code", 0)

            color = discord.Color.green() if (success and exit_code == 0) else discord.Color.red()
            embed = discord.Embed(
                title=f"⚙️ Code Execution Sandbox ({language.upper()})",
                color=color
            )

            # Code Preview (First 5 lines)
            code_lines = code.splitlines()
            preview = "\n".join(code_lines[:6])
            if len(code_lines) > 6:
                preview += f"\n... ({len(code_lines) - 6} more lines)"
            embed.add_field(name="Input Code", value=f"```{language}\n{preview}\n```", inline=False)

            if stdout:
                output_text = stdout[:1000] + ("\n... [Truncated]" if len(stdout) > 1000 else "")
                embed.add_field(name="Output (stdout)", value=f"```\n{output_text}\n```", inline=False)
            if stderr:
                err_text = stderr[:1000] + ("\n... [Truncated]" if len(stderr) > 1000 else "")
                embed.add_field(name="Errors (stderr)", value=f"```\n{err_text}\n```", inline=False)
            if not stdout and not stderr:
                embed.add_field(name="Status", value="Completed with zero output.", inline=False)

            embed.set_footer(text=f"Sandbox Isolation: Docker (--network none) • Latency: {duration} ms • Exit: {exit_code}")
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error communicating with Zauq sandbox: {str(e)}")

class CodeEditorModal(discord.ui.Modal):
    def __init__(self, language: str, channel_id: str):
        super().__init__(title=f"Zauq Code Sandbox ({language.upper()})")
        self.language = language
        self.channel_id = channel_id

        placeholder_map = {
            "python": "def solution():\n    return 'Hello from Zauq Sandbox!'\n\nprint(solution())",
            "javascript": "function solution() {\n    return 'Hello from Node.js!';\n}\n\nconsole.log(solution());",
            "bash": "echo 'Hello from Linux Sandbox!'\nuname -a\ndate"
        }

        self.code_input = discord.ui.TextInput(
            label="Code Editor (Enter-key newlines supported)",
            style=discord.TextStyle.paragraph,
            placeholder=placeholder_map.get(language, "# Enter your code here..."),
            required=True,
            max_length=4000
        )
        self.add_item(self.code_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await execute_and_send_result(
            interaction=interaction,
            code=self.code_input.value,
            language=self.language,
            channel_id=self.channel_id
        )

class ExecSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name="Run Code Snippet",
            callback=self.run_code_context_menu
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    @app_commands.command(name="run", description="Execute code safely in an isolated Docker sandbox container")
    @app_commands.describe(
        code="Quick single-line code snippet (leave empty to open multiline popup editor)",
        language="Programming language: Python 3, JavaScript (Node.js), or Bash",
        file="Attach a .py, .js, or .sh script file to execute"
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="Python 3", value="python"),
            app_commands.Choice(name="JavaScript (Node.js)", value="javascript"),
            app_commands.Choice(name="Bash", value="bash"),
        ]
    )
    async def run_command(
        self,
        interaction: discord.Interaction,
        code: Optional[str] = None,
        language: Optional[app_commands.Choice[str]] = None,
        file: Optional[discord.Attachment] = None
    ):
        lang = language.value if language else None

        # Mode 1: File attachment passed
        if file:
            await interaction.response.defer(thinking=True)
            ext = os.path.splitext(file.filename.lower())[1]
            if not lang:
                if ext == ".py":
                    lang = "python"
                elif ext in [".js", ".ts", ".mjs"]:
                    lang = "javascript"
                elif ext in [".sh", ".bash"]:
                    lang = "bash"
                else:
                    lang = "python"

            if file.size > 50 * 1024:
                await interaction.followup.send("⚠️ File too large. Maximum script size is 50KB.")
                return

            file_bytes = await file.read()
            code_str = file_bytes.decode("utf-8", errors="replace")
            await execute_and_send_result(interaction, code_str, lang, str(interaction.channel_id))
            return

        # Mode 2: Quick inline code string passed
        if code:
            await interaction.response.defer(thinking=True)
            target_lang = lang or "python"
            await execute_and_send_result(interaction, code, target_lang, str(interaction.channel_id))
            return

        # Mode 3: No code or file passed -> Open Multiline Popup Modal
        target_lang = lang or "python"
        await interaction.response.send_modal(CodeEditorModal(language=target_lang, channel_id=str(interaction.channel_id)))

    async def run_code_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        """Right-click message -> Apps -> Run Code Snippet"""
        await interaction.response.defer(thinking=True)
        content = message.content or ""

        code, lang = extract_code_and_lang(content)
        if not code:
            await interaction.followup.send("⚠️ No code snippet found in this message. Make sure the code is wrapped in markdown code fences (` ```python ... ``` `).")
            return

        await execute_and_send_result(interaction, code, lang, str(interaction.channel_id))

    # ── v4 /sandbox Command Group ─────────────────────────────────────────────
    sandbox_group = app_commands.Group(name="sandbox", description="Docker code sandbox status and automation settings")

    @sandbox_group.command(name="status", description="View Docker sandbox health, concurrency limits, and security controls")
    async def sandbox_status(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            async with api_client(timeout=10.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/sandbox/status")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error fetching sandbox status: {res.text}")
                    return
                data = res.json()
                docker_ok = data.get("docker_available", False)
                color = discord.Color.green() if docker_ok else discord.Color.gold()
                embed = discord.Embed(title="⚙️ Zauq Code Sandbox Status", color=color)
                embed.add_field(name="Docker Daemon", value="🟢 Online" if docker_ok else "🟡 Offline / Host Disabled", inline=True)
                embed.add_field(name="Max Concurrency", value=str(data.get("max_concurrency", 1)), inline=True)
                embed.add_field(name="Default Timeout", value=f"{data.get('default_timeout_seconds', 8)}s", inline=True)
                embed.add_field(name="Max Output Chars", value=f"{data.get('max_output_chars', 12000):,}", inline=True)
                embed.add_field(name="Auto-Test Default", value=str(data.get("auto_code_test_default", "off")), inline=True)
                embed.add_field(name="Max Repair Attempts", value=str(data.get("auto_code_repair_attempts", 1)), inline=True)
                images = ", ".join(f"`{img}`" for img in data.get("allowed_images", []))
                embed.add_field(name="Allowed Containers", value=images or "None", inline=False)
                sec = data.get("security", {})
                embed.set_footer(text=f"Network: {sec.get('network')} • RAM: {sec.get('memory')} • CPUs: {sec.get('cpus')} • Cap-drop: {sec.get('cap_drop')}")
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error querying sandbox status: {e}")

    @sandbox_group.command(name="auto_mode", description="Configure automatic code testing for this channel (off, auto, always)")
    @app_commands.describe(mode="Choose auto code test policy: off, auto, or always")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Off (Manual /run only)", value="off"),
            app_commands.Choice(name="Auto (Test when helpful)", value="auto"),
            app_commands.Choice(name="Always (Verify all runnable code)", value="always"),
        ]
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def sandbox_auto_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await interaction.response.defer(thinking=True)
        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "dm"
        payload = {
            "channel_id": channel_id,
            "guild_id": guild_id,
            "auto_mode": mode.value
        }
        try:
            async with api_client(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/sandbox/auto_mode", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Error setting auto mode: {res.text}")
                    return
                await interaction.followup.send(f"✅ Sandbox auto-code-test mode set to **{mode.name}** for this channel.")
        except Exception as e:
            await interaction.followup.send(f"❌ Error updating sandbox auto mode: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ExecSlash(bot))
