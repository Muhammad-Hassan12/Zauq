-- Supabase Schema for Zauq (AgenticEra Hybrid AI Discord Bot)

-- Enable pgvector extension if not enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Guild Configurations
CREATE TABLE IF NOT EXISTS guild_configs (
    guild_id TEXT PRIMARY KEY,
    guild_name TEXT NOT NULL,
    default_mode TEXT NOT NULL DEFAULT 'hangout' CHECK (default_mode IN ('dev', 'hangout')),
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

-- Index for user_id lookup
CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id);

-- Vector similarity search index
CREATE INDEX IF NOT EXISTS idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 5. Server Lore / Knowledge Base (for Phase 2 RAG)
CREATE TABLE IF NOT EXISTS server_lore (
    lore_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('repo', 'doc', 'inside_joke', 'rule')),
    content TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_server_lore_guild ON server_lore(guild_id);

-- ========================================================
-- Enable Row Level Security (RLS) & Policies
-- ========================================================
ALTER TABLE guild_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_selection ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE server_lore ENABLE ROW LEVEL SECURITY;

-- Allow full access for backend service role
CREATE POLICY "Allow service role full access on guild_configs" ON guild_configs FOR ALL USING (true);
CREATE POLICY "Allow service role full access on channel_profiles" ON channel_profiles FOR ALL USING (true);
CREATE POLICY "Allow service role full access on model_selection" ON model_selection FOR ALL USING (true);
CREATE POLICY "Allow service role full access on user_memories" ON user_memories FOR ALL USING (true);
CREATE POLICY "Allow service role full access on server_lore" ON server_lore FOR ALL USING (true);

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
ALTER TABLE request_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow service role full access on request_logs" ON request_logs FOR ALL USING (true);


