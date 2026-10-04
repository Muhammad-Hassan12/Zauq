from backend.config import settings


def feature_enabled(feature: str, channel_id=None, guild_id=None, profile=None, guild_config=None) -> bool:
    """Master flag AND operator allowlists AND channel/server preference."""
    prefix='AGENT' if feature=='agent' else 'MCP'
    if not getattr(settings, 'AGENT_RUNTIME_ENABLED' if feature=='agent' else 'MCP_ENABLED'):
        return False
    for scope, value in (('GUILD',guild_id),('CHANNEL',channel_id)):
        allowed={item.strip() for item in getattr(settings,f'{prefix}_ALLOWED_{scope}_IDS').split(',') if item.strip()}
        if allowed and str(value) not in allowed:
            return False
    field='agent_runtime_enabled' if feature=='agent' else 'mcp_enabled'
    channel_value=(profile or {}).get(field)
    guild_value=(guild_config or {}).get(field)
    return bool(channel_value if channel_value is not None else guild_value if guild_value is not None else True)
