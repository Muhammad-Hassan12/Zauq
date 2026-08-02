import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
import discord
from discord import app_commands
from discord.ext import commands
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

class GitHubSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    github_group = app_commands.Group(name="github", description="GitHub repository integrations and PR/issue insights")

    @github_group.command(name="pr", description="Fetch and summarize a Pull Request")
    @app_commands.describe(repo="Format: owner/repo (e.g. fastapi/fastapi)", pr_number="PR number")
    async def pr_info(self, interaction: discord.Interaction, repo: str, pr_number: int):
        await interaction.response.defer(thinking=True)
        try:
            parts = repo.split("/")
            if len(parts) != 2:
                await interaction.followup.send("⚠️ Invalid format. Use `owner/repo` (e.g., `fastapi/fastapi`).")
                return
            owner, repo_name = parts[0], parts[1]

            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/github/pr?owner={owner}&repo={repo_name}&pr_number={pr_number}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Failed to fetch PR #{pr_number}: {res.text}")
                    return

                data = res.json()
                embed = discord.Embed(
                    title=f"🔀 Pull Request #{pr_number}: {data.get('title')}",
                    url=f"https://github.com/{owner}/{repo_name}/pull/{pr_number}",
                    color=discord.Color.dark_theme()
                )
                embed.add_field(name="Author", value=f"@{data.get('author')}", inline=True)
                embed.add_field(name="State", value=f"`{data.get('state')}`", inline=True)

                diff_preview = data.get("diff", "")[:1000]
                if diff_preview:
                    embed.add_field(name="Diff Preview", value=f"```diff\n{diff_preview}\n```", inline=False)

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching PR info: {e}")

    @github_group.command(name="issue", description="Fetch and summarize a GitHub Issue")
    @app_commands.describe(repo="Format: owner/repo (e.g. fastapi/fastapi)", issue_number="Issue number")
    async def issue_info(self, interaction: discord.Interaction, repo: str, issue_number: int):
        await interaction.response.defer(thinking=True)
        try:
            parts = repo.split("/")
            if len(parts) != 2:
                await interaction.followup.send("⚠️ Invalid format. Use `owner/repo`.")
                return
            owner, repo_name = parts[0], parts[1]

            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(f"{BACKEND_URL}/api/github/issue?owner={owner}&repo={repo_name}&issue_number={issue_number}")
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Failed to fetch Issue #{issue_number}: {res.text}")
                    return

                data = res.json()
                embed = discord.Embed(
                    title=f"❓ Issue #{issue_number}: {data.get('title')}",
                    url=f"https://github.com/{owner}/{repo_name}/issues/{issue_number}",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Author", value=f"@{data.get('author')}", inline=True)
                embed.add_field(name="State", value=f"`{data.get('state')}`", inline=True)

                body_text = data.get("body", "")[:1000]
                if body_text:
                    embed.add_field(name="Description", value=f"```\n{body_text}\n```", inline=False)

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching issue info: {e}")

    @app_commands.command(name="ingest_repo", description="Ingest a GitHub repository's README into server lore")
    @app_commands.describe(repo="Format: owner/repo (e.g. fastapi/fastapi)")
    async def ingest_repo(self, interaction: discord.Interaction, repo: str):
        await interaction.response.defer(thinking=True)
        try:
            parts = repo.split("/")
            if len(parts) != 2:
                await interaction.followup.send("⚠️ Invalid format. Use `owner/repo`.")
                return
            owner, repo_name = parts[0], parts[1]
            guild_id = str(interaction.guild_id) if interaction.guild_id else "global"

            payload = {
                "guild_id": guild_id,
                "owner": owner,
                "repo": repo_name
            }

            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(f"{BACKEND_URL}/api/github/ingest", json=payload)
                if res.status_code != 200:
                    await interaction.followup.send(f"⚠️ Ingestion failed: {res.text}")
                    return

                embed = discord.Embed(
                    title="📚 Repository Ingested",
                    description=f"Ingested README for `{owner}/{repo_name}` into Zauq vector memory.",
                    color=discord.Color.teal()
                )
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Ingestion Error: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(GitHubSlash(bot))
