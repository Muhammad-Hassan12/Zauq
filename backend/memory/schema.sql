-- Supabase Schema for Zauq v4.0 — fresh installs; existing installs use ordered migrations.

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Channel Profiles
CREATE TABLE IF NOT EXISTS channel_profiles (
    channel_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL REFERENCES guild_configs(guild_id) ON DELETE CASCADE,
    operating_mode TEXT NOT NULL DEFAULT 'hangout' CHECK (operating_mode IN ('dev', 'hangout')),
    system_persona_prompt TEXT,
    temperature DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    allow_code_exec BOOLEAN NOT NULL DEFAULT FALSE,
    thinking_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    auto_code_test_mode TEXT NOT NULL DEFAULT 'off' CHECK (auto_code_test_mode IN ('off', 'auto', 'always')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Explicit Model Selection per Channel
CREATE TABLE IF NOT EXISTS model_selection (
    channel_id TEXT PRIMARY KEY,
    tier INT NOT NULL CHECK (tier IN (1, 2, 3)),
    provider TEXT NOT NULL CHECK (provider IN ('gemini', 'digitalocean', 'anthropic', 'qwen', 'deepseek', 'ollama', 'kaggle')),
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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
    delivering BOOLEAN NOT NULL DEFAULT FALSE,  -- in-flight guard to prevent duplicate sends
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

-- Enable Row Level Security (RLS) & Policies

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
DROP POLICY IF EXISTS "Service role only on guild_configs" ON guild_configs;
CREATE POLICY "Service role only on guild_configs" ON guild_configs FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on channel_profiles" ON channel_profiles;
CREATE POLICY "Service role only on channel_profiles" ON channel_profiles FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on model_selection" ON model_selection;
CREATE POLICY "Service role only on model_selection" ON model_selection FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on user_memories" ON user_memories;
CREATE POLICY "Service role only on user_memories" ON user_memories FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on server_lore" ON server_lore;
CREATE POLICY "Service role only on server_lore" ON server_lore FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on request_logs" ON request_logs;
CREATE POLICY "Service role only on request_logs" ON request_logs FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on user_stats" ON user_stats;
CREATE POLICY "Service role only on user_stats" ON user_stats FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on scheduled_reminders" ON scheduled_reminders;
CREATE POLICY "Service role only on scheduled_reminders" ON scheduled_reminders FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Service role only on moderation_log" ON moderation_log;
CREATE POLICY "Service role only on moderation_log" ON moderation_log FOR ALL TO authenticated USING (false);

DROP POLICY IF EXISTS "Block anon on guild_configs" ON guild_configs;
CREATE POLICY "Block anon on guild_configs" ON guild_configs FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on channel_profiles" ON channel_profiles;
CREATE POLICY "Block anon on channel_profiles" ON channel_profiles FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on model_selection" ON model_selection;
CREATE POLICY "Block anon on model_selection" ON model_selection FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on user_memories" ON user_memories;
CREATE POLICY "Block anon on user_memories" ON user_memories FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on server_lore" ON server_lore;
CREATE POLICY "Block anon on server_lore" ON server_lore FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on request_logs" ON request_logs;
CREATE POLICY "Block anon on request_logs" ON request_logs FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on user_stats" ON user_stats;
CREATE POLICY "Block anon on user_stats" ON user_stats FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on scheduled_reminders" ON scheduled_reminders;
CREATE POLICY "Block anon on scheduled_reminders" ON scheduled_reminders FOR ALL TO anon USING (false);
DROP POLICY IF EXISTS "Block anon on moderation_log" ON moderation_log;
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

-- v3.1 Migrations (additive only — safe to re-run)

-- M1: Thinking mode toggle per channel
ALTER TABLE channel_profiles
    ADD COLUMN IF NOT EXISTS thinking_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- M2: Enhanced user memory fields for true vector-based L2 memory
ALTER TABLE user_memories
    ADD COLUMN IF NOT EXISTS importance_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS access_count INT NOT NULL DEFAULT 0;

-- M3: Vector similarity search RPC for L2 user memories
-- Ranks by similarity * importance_score so relevant AND important memories float up
CREATE OR REPLACE FUNCTION match_user_memories(
    query_embedding vector(768),
    match_user_id TEXT,
    match_threshold float DEFAULT 0.65,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    memory_id UUID,
    user_id TEXT,
    category TEXT,
    fact_content TEXT,
    similarity float,
    importance_score DOUBLE PRECISION,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.memory_id,
        m.user_id,
        m.category,
        m.fact_content,
        1 - (m.embedding <=> query_embedding) AS similarity,
        m.importance_score,
        m.created_at
    FROM user_memories m
    WHERE m.user_id = match_user_id
      AND m.embedding IS NOT NULL
      AND 1 - (m.embedding <=> query_embedding) > match_threshold
    ORDER BY (1 - (m.embedding <=> query_embedding)) * m.importance_score DESC
    LIMIT match_count;
END;
$$;

-- M4: Performance indexes for memory decay queries
CREATE INDEX IF NOT EXISTS idx_user_memories_importance
    ON user_memories(importance_score ASC);

CREATE INDEX IF NOT EXISTS idx_user_memories_last_accessed
    ON user_memories(last_accessed_at ASC);

-- v4.0: Pending Actions (Human-in-the-Loop)

CREATE TABLE IF NOT EXISTS pending_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk TEXT NOT NULL DEFAULT 'write',
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'approved' | 'denied' | 'expired' | 'executed'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    executed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status ON pending_actions (user_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_expires_at ON pending_actions (expires_at);

ALTER TABLE pending_actions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role only on pending_actions" ON pending_actions;
CREATE POLICY "Service role only on pending_actions" ON pending_actions FOR ALL TO authenticated USING (false);
DROP POLICY IF EXISTS "Block anon on pending_actions" ON pending_actions;
CREATE POLICY "Block anon on pending_actions" ON pending_actions FOR ALL TO anon USING (false);

-- v4.0 Additive Migrations for Existing Databases

-- M5: Auto code test mode toggle per channel
ALTER TABLE channel_profiles
    ADD COLUMN IF NOT EXISTS auto_code_test_mode TEXT NOT NULL DEFAULT 'off' CHECK (auto_code_test_mode IN ('off', 'auto', 'always'));

-- M6: Observability, token usage, cost audit, and agent metrics
ALTER TABLE request_logs
    ADD COLUMN IF NOT EXISTS tool_steps INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS search_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pages_fetched INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sandbox_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mcp_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tool_failures INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS agent_duration_ms INT,
    ADD COLUMN IF NOT EXISTS input_tokens INT,
    ADD COLUMN IF NOT EXISTS output_tokens INT,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS request_id TEXT,
    ADD COLUMN IF NOT EXISTS agent_run_id TEXT;

-- Included migration: 004_v4_rollout.sql
ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS agent_runtime_enabled BOOLEAN;
ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS mcp_enabled BOOLEAN;
ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS agent_runtime_enabled BOOLEAN;
ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS mcp_enabled BOOLEAN;

-- Included migration: 005_v4_metrics.sql
ALTER TABLE request_logs
    ADD COLUMN IF NOT EXISTS tool_steps INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS search_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pages_fetched INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sandbox_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mcp_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tool_failures INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS agent_duration_ms INT,
    ADD COLUMN IF NOT EXISTS input_tokens INT,
    ADD COLUMN IF NOT EXISTS output_tokens INT,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS request_id TEXT,
    ADD COLUMN IF NOT EXISTS agent_run_id TEXT,
    ADD COLUMN IF NOT EXISTS provider_usage JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ok';

CREATE OR REPLACE FUNCTION v4_metrics_summary(requested_guild TEXT DEFAULT NULL)
RETURNS JSONB LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public AS $$
WITH logs AS (SELECT * FROM request_logs WHERE requested_guild IS NULL OR guild_id = requested_guild),
providers AS (SELECT upper(provider) AS provider, count(*) AS n FROM logs GROUP BY provider)
SELECT jsonb_build_object(
    'total_requests', count(*), 'avg_latency_ms', COALESCE(round(avg(response_time_ms), 1), 0),
    'provider_breakdown', COALESCE((SELECT jsonb_object_agg(provider,n) FROM providers), '{}'::jsonb),
    'total_tool_steps', COALESCE(sum(tool_steps),0),
    'total_search_calls', COALESCE(sum(search_calls),0),
    'total_pages_fetched', COALESCE(sum(pages_fetched),0),
    'total_sandbox_calls', COALESCE(sum(sandbox_calls),0),
    'total_mcp_calls', COALESCE(sum(mcp_calls),0),
    'total_tool_failures', COALESCE(sum(tool_failures),0),
    'total_input_tokens', COALESCE(sum(input_tokens),0),
    'total_output_tokens', COALESCE(sum(output_tokens),0),
    'unknown_usage_requests', count(*) FILTER (WHERE input_tokens IS NULL OR output_tokens IS NULL),
    'known_estimated_cost_usd', COALESCE(sum(estimated_cost_usd),0),
    'unknown_cost_requests', count(*) FILTER (WHERE estimated_cost_usd IS NULL),
    'total_estimated_cost_usd', CASE WHEN count(*) FILTER (WHERE estimated_cost_usd IS NULL) > 0 THEN NULL ELSE COALESCE(sum(estimated_cost_usd),0) END,
    'window', 'all retained database requests'
) FROM logs;
$$;
REVOKE ALL ON FUNCTION v4_metrics_summary(TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION v4_metrics_summary(TEXT) TO service_role;

-- Included migration: 006_v4_schema_repair.sql
-- Reconcile installations that applied the early boolean auto-test example.
-- TRUE becomes auto (never always); explicit execution permissions stay intact.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='channel_profiles' AND column_name='auto_code_test_mode' AND data_type='boolean') THEN
        ALTER TABLE channel_profiles DROP CONSTRAINT IF EXISTS channel_profiles_auto_code_test_mode_check;
        ALTER TABLE channel_profiles ALTER COLUMN auto_code_test_mode DROP DEFAULT;
        ALTER TABLE channel_profiles ALTER COLUMN auto_code_test_mode TYPE TEXT
            USING CASE WHEN auto_code_test_mode THEN 'auto' ELSE 'off' END;
    END IF;
END;
$$;
ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS auto_code_test_mode TEXT;
UPDATE channel_profiles SET auto_code_test_mode='off' WHERE auto_code_test_mode IS NULL OR auto_code_test_mode NOT IN ('off','auto','always');
ALTER TABLE channel_profiles ALTER COLUMN auto_code_test_mode SET DEFAULT 'off';
ALTER TABLE channel_profiles ALTER COLUMN auto_code_test_mode SET NOT NULL;
ALTER TABLE channel_profiles DROP CONSTRAINT IF EXISTS channel_profiles_auto_code_test_mode_check;
ALTER TABLE channel_profiles ADD CONSTRAINT channel_profiles_auto_code_test_mode_check CHECK (auto_code_test_mode IN ('off','auto','always'));
ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS thinking_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE pending_actions ADD COLUMN IF NOT EXISTS signature TEXT;
ALTER TABLE pending_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE guild_configs DROP CONSTRAINT IF EXISTS guild_configs_default_provider_check;
ALTER TABLE guild_configs ADD CONSTRAINT guild_configs_default_provider_check CHECK (default_provider IN ('gemini','digitalocean','anthropic','qwen','deepseek','ollama','kaggle'));

-- M-atomic: Atomic access_count increment for user memories (race-free reinforce_memory)
CREATE OR REPLACE FUNCTION increment_memory_access(p_memory_id UUID)
RETURNS void
LANGUAGE sql
AS $$
    UPDATE user_memories
       SET access_count      = access_count + 1,
           last_accessed_at  = NOW()
     WHERE memory_id = p_memory_id;
$$;

-- M-deliver: Add in-flight guard column to scheduled_reminders (idempotent delivery)
ALTER TABLE scheduled_reminders ADD COLUMN IF NOT EXISTS delivering BOOLEAN NOT NULL DEFAULT FALSE;

-- M-timestamps: Consistent (created_at, updated_at) on all tables
ALTER TABLE guild_configs      ADD COLUMN IF NOT EXISTS updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE channel_profiles   ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE model_selection     ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW();
