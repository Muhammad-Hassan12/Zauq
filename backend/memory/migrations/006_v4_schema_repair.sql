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
