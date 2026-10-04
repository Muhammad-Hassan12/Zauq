ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS agent_runtime_enabled BOOLEAN;
ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS mcp_enabled BOOLEAN;
ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS agent_runtime_enabled BOOLEAN;
ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS mcp_enabled BOOLEAN;
