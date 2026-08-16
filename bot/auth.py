import httpx
import discord
from backend.config import settings
from bot.api import BACKEND_URL, api_client

async def check_admin_authorization(interaction: discord.Interaction) -> bool:
    """
    Verifies if interaction user is authorized to configure Zauq:
    1. Direct Messages: Always authorized for personal settings.
    2. Server Owner: Always authorized.
    3. Discord Administrator Permission: Always authorized.
    4. Discord 'Manage Server' or 'Manage Channels' Permission: Authorized.
    5. Member has designated admin/staff role configured in guild_configs.
    """
    if not interaction.guild:
        return True

    member = interaction.user
    if not isinstance(member, discord.Member):
        return False

    # Server Owner or Administrator
    if member.id == interaction.guild.owner_id or member.guild_permissions.administrator:
        return True

    # Manage Guild or Manage Channels
    if member.guild_permissions.manage_guild or member.guild_permissions.manage_channels:
        return True

    # Check designated custom admin role in Supabase guild_configs
    try:
        guild_id = str(interaction.guild.id)
        async with api_client(timeout=3.0) as client:
            res = await client.get(f"{BACKEND_URL}/api/admin/config?guild_id={guild_id}")
            if res.status_code == 200:
                cfg = res.json()
                admin_role_id = cfg.get("admin_role_id")
                if admin_role_id:
                    member_role_ids = {str(r.id) for r in member.roles}
                    if str(admin_role_id) in member_role_ids:
                        return True
    except Exception:
        pass

    return False

def make_denied_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔒 Access Restricted",
        description="Only **Server Administrators**, members with **Manage Server** permissions, or users with the **designated Zauq Admin Role** can configure model and operating mode settings.",
        color=discord.Color.red()
    )
    embed.set_footer(text="Ask a server administrator to configure this channel or grant you the required role.")
    return embed
