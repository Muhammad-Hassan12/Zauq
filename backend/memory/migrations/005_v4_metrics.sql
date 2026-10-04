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
