-- Supabase Schema for Zauq (AgenticEra Hybrid AI Discord Bot) v3.0

-- Enable pgvector extension if not enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Guild Configurations
CREATE TABLE IF NOT EXISTS guild_configs (
    guild_id TEXT PRIMARY KEY,
    guild_name TEXT NOT NULL,
    default_mode TEXT NOT NULL DEFAULT 'hangout' CHECK (default_mode IN ('dev', 'hangout')),
    default_tier INT NOT NULL DEFAULT 1,
    default_provider TEXT NOT NULL DEFAULT 'gemini',
    default_model_name TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
    admin_role_id TEXT,
    moderation_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    moderation_sensitivity TEXT NOT NULL DEFAULT 'medium' CHECK (moderation_sensitivity IN ('low', 'medium', 'high')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Channel Profiles
CREATE TABLE IF NOT EXISTS channel_profiles (
    channel_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL REFERENCES guild_configs(guild_id) ON DELETE CASCADE,
    operating_mode TEXT NOT NULL DEFAULT 'hangout' CHECK (operating_mode IN ('dev', 'hangout')),
    system_persona_prompt TEXT,
    temperature DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    allow_code_exec BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Explicit Model Selection per Channel
CREATE TABLE IF NOT EXISTS model_selection (
    channel_id TEXT PRIMARY KEY,
    tier INT NOT NULL CHECK (tier IN (1, 2, 3)),
    provider TEXT NOT NULL CHECK (provider IN ('gemini', 'digitalocean', 'ollama', 'kaggle')),
    model_name TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

-- 4. User Episodic Memory (Vector Store)
CREATE TABLE IF NOT EXISTS user_memories (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    fact_content TEXT NOT NULL,
    embedding vector(768),
    confidence_score DOUBLE PRECISION DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 5. Server Lore / Knowledge Base
CREATE TABLE IF NOT EXISTS server_lore (
    lore_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('repo', 'doc', 'inside_joke', 'rule', 'summary')),
    content TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_server_lore_guild ON server_lore(guild_id);

-- 6. Request Logs & Cost Audit Dashboard
CREATE TABLE IF NOT EXISTS request_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT,
    channel_id TEXT,
    user_id TEXT,
    tier INT NOT NULL DEFAULT 1,
    provider TEXT NOT NULL DEFAULT 'gemini',
    model_name TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
    response_time_ms INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_request_logs_guild ON request_logs(guild_id);

-- 7. User Stats & XP Reputation System (Composite PK: user_id + guild_id)
CREATE TABLE IF NOT EXISTS user_stats (
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    display_name TEXT,
    xp INT NOT NULL DEFAULT 0,
    level INT NOT NULL DEFAULT 1,
    messages_count INT NOT NULL DEFAULT 0,
    commands_used INT NOT NULL DEFAULT 0,
    trivia_correct INT NOT NULL DEFAULT 0,
    trivia_played INT NOT NULL DEFAULT 0,
    streak_days INT NOT NULL DEFAULT 0,
    last_active_date DATE,
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, guild_id)
);

CREATE INDEX IF NOT EXISTS idx_user_stats_guild ON user_stats(guild_id);
CREATE INDEX IF NOT EXISTS idx_user_stats_xp ON user_stats(xp DESC);

-- 8. Scheduled Reminders
CREATE TABLE IF NOT EXISTS scheduled_reminders (
    reminder_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    message TEXT NOT NULL,
    remind_at TIMESTAMPTZ NOT NULL,
    delivered BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reminders_pending ON scheduled_reminders(remind_at) WHERE delivered = FALSE;

-- 9. Moderation Log
CREATE TABLE IF NOT EXISTS moderation_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    message_content TEXT,
    action_taken TEXT NOT NULL CHECK (action_taken IN ('flagged', 'warned', 'deleted')),
    severity TEXT NOT NULL DEFAULT 'low' CHECK (severity IN ('low', 'medium', 'high')),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_moderation_guild ON moderation_log(guild_id);

-- ========================================================
-- Enable Row Level Security (RLS) & Policies
-- ========================================================
ALTER TABLE guild_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_selection ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE server_lore ENABLE ROW LEVEL SECURITY;
ALTER TABLE request_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE moderation_log ENABLE ROW LEVEL SECURITY;

-- Restrictive policies: authenticated/anon roles blocked from direct client access
-- Backend service_role key bypasses RLS and maintains full programmatic access
CREATE POLICY "Service role only on guild_configs" ON guild_configs FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on channel_profiles" ON channel_profiles FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on model_selection" ON model_selection FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on user_memories" ON user_memories FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on server_lore" ON server_lore FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on request_logs" ON request_logs FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on user_stats" ON user_stats FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on scheduled_reminders" ON scheduled_reminders FOR ALL TO authenticated USING (false);
CREATE POLICY "Service role only on moderation_log" ON moderation_log FOR ALL TO authenticated USING (false);

CREATE POLICY "Block anon on guild_configs" ON guild_configs FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on channel_profiles" ON channel_profiles FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on model_selection" ON model_selection FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on user_memories" ON user_memories FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on server_lore" ON server_lore FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on request_logs" ON request_logs FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on user_stats" ON user_stats FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on scheduled_reminders" ON scheduled_reminders FOR ALL TO anon USING (false);
CREATE POLICY "Block anon on moderation_log" ON moderation_log FOR ALL TO anon USING (false);

-- Vector similarity search RPC function for server_lore
CREATE OR REPLACE FUNCTION match_server_lore(
    query_embedding vector(768),
    match_guild_id TEXT,
    match_threshold float DEFAULT 0.1,
    match_count int DEFAULT 3
)
RETURNS TABLE (
    lore_id UUID,
    guild_id TEXT,
    source_type TEXT,
    content TEXT,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        server_lore.lore_id,
        server_lore.guild_id,
        server_lore.source_type,
        server_lore.content,
        1 - (server_lore.embedding <=> query_embedding) AS similarity
    FROM server_lore
    WHERE server_lore.guild_id = match_guild_id
      AND 1 - (server_lore.embedding <=> query_embedding) > match_threshold
    ORDER BY server_lore.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
