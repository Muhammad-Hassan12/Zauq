-- Migration 002: Add auto_code_test_mode to channel_profiles
-- Allowed values: 'off', 'auto', 'always' (default: 'off')

ALTER TABLE channel_profiles
ADD COLUMN IF NOT EXISTS auto_code_test_mode TEXT
DEFAULT 'off'
CHECK (auto_code_test_mode IN ('off', 'auto', 'always'));
