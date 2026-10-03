-- Migration: 003_v4_pending_actions.sql
-- Description: Creates pending_actions table for Phase 7 Side-Effect Approval / Human-in-the-Loop

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
