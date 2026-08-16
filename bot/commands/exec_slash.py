
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings
from bot.api import BACKEND_URL, api_client

class ExecSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="run", description="Execute code safely in an isolated sandbox container")
    @app_commands.describe(
        code="The code snippet to execute",
        language="Programming language: python, javascript, bash"
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="Python 3", value="python"),
            app_commands.Choice(name="JavaScript (Node.js)", value="javascript"),
            app_commands.Choice(name="Bash", value="bash"),
        ]
    )
    async def run(
        self,
        interaction: discord.Interaction,
        code: str,
        language: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)
        lang = language.value if language else "python"

        payload = {
            "code": code,
            "language": lang,
            "timeout": 5.0,
            "channel_id": str(interaction.channel_id)
        }

        try:
            async with api_client(timeout=10.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/sandbox/exec", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Sandbox Error: {res.text}")
                    return

                data = res.json()
                success = data.get("success", False)
                stdout = data.get("stdout", "").strip()
                stderr = data.get("stderr", "").strip()
                duration = data.get("execution_time_ms", 0)

                color = discord.Color.green() if success else discord.Color.red()
                embed = discord.Embed(
                    title=f"⚙️ Code Execution Results ({lang.upper()})",
                    color=color
                )

                if stdout:
                    output_text = stdout[:1000] + ("..." if len(stdout) > 1000 else "")
                    embed.add_field(name="Output (stdout)", value=f"```\n{output_text}\n```", inline=False)
                if stderr:
                    err_text = stderr[:1000] + ("..." if len(stderr) > 1000 else "")
                    embed.add_field(name="Errors (stderr)", value=f"```\n{err_text}\n```", inline=False)
                if not stdout and not stderr:
                    embed.add_field(name="Status", value="Completed with no output.", inline=False)

                embed.set_footer(text=f"Execution time: {duration} ms | Exit Code: {data.get('exit_code', 0)}")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error communicating with Zauq sandbox: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ExecSlash(bot))
