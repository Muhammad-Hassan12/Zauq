-- Migration 001: Expand Tier 1 Providers in model_selection table
-- Allows 'anthropic', 'qwen', and 'deepseek' alongside existing providers

ALTER TABLE model_selection
DROP CONSTRAINT IF EXISTS model_selection_provider_check;

ALTER TABLE model_selection
ADD CONSTRAINT model_selection_provider_check
CHECK (provider IN (
    'gemini',
    'digitalocean',
    'anthropic',
    'qwen',
    'deepseek',
    'ollama',
    'kaggle'
));
