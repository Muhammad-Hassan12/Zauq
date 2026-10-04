# Zauq v4 deployment and migration

Use a controlled staging environment before enabling tools for a community. The backend requires Python 3.11/3.12 and an internal API key; code execution additionally requires Docker Engine, pre-pulled images and the separate runner. Supabase is optional for basic chat but required for persistent profiles, memory, durable approvals and metrics.

## Database setup

Back up the database before upgrading. For a **fresh Supabase installation**, run [backend/memory/schema.sql](backend/memory/schema.sql). It includes pgvector, application tables, RLS, memory functions and v4 additions. It is tested for repeat execution by the pgvector CI gate.

For an **existing v3 installation**, apply the SQL files in this order, using the SQL editor or a database migration tool:

1. [001_v4_providers.sql](backend/memory/migrations/001_v4_providers.sql): provider constraint expansion.
2. [002_v4_auto_code_test_mode.sql](backend/memory/migrations/002_v4_auto_code_test_mode.sql): text auto-test policy.
3. [003_v4_pending_actions.sql](backend/memory/migrations/003_v4_pending_actions.sql): signatures, indexes and RLS for actions.
4. [004_v4_rollout.sql](backend/memory/migrations/004_v4_rollout.sql): nullable channel/server preferences.
5. [005_v4_metrics.sql](backend/memory/migrations/005_v4_metrics.sql): complete telemetry and service-role-only aggregate.
6. [006_v4_schema_repair.sql](backend/memory/migrations/006_v4_schema_repair.sql): repair early boolean auto modes and reconcile constraints.

The sequence is additive and rerunnable. Legacy boolean `true` becomes `auto`; `false` becomes `off`. It preserves explicit `allow_code_exec` values. Use the numbered SQL files as the executable upgrade source. Upgrades assume the v3 base tables already exist. Older pre-v3 deployments need the corresponding base-schema upgrade first.

Use a **service-role** Supabase key on the backend. Anonymous/authenticated clients cannot access action records, and cannot execute the metrics summary function. Existing unsigned pending approvals must be staged again after upgrading; do not execute them. Changing the internal signing key invalidates outstanding approvals.

## Docker Compose

From the repository root:

```bash
cp .env.example .env
openssl rand -hex 32
```

Put the generated value in `INTERNAL_API_KEY`. Fill in the Discord token and the credentials you actually use; leave optional services blank. Keep `DEVELOPMENT_MODE=false`, `AGENT_RUNTIME_ENABLED=false` and `MCP_ENABLED=false` initially.

Set `SANDBOX_HOST_SPOOL_DIR` to an absolute Docker-host path, normally `/var/lib/zauq/sandbox`. The runner mounts that host directory at `/sandbox-spool` and maps code files back to the host path when starting sibling containers. Docker resolves bind sources on the daemon host, not inside the runner container. The runner must be able to create and clean files there. Remote Docker daemons need an equivalent shared path; a runner-local temporary directory alone does not work. [Docker bind-mount documentation](https://docs.docker.com/engine/storage/bind-mounts/).

Pre-pull execution images; requests use `--pull never`:

```bash
docker pull python:3.11-slim
docker pull node:18-alpine
docker pull alpine:latest
docker compose config --quiet
docker compose up -d --build
```

Only the runner mounts `/var/run/docker.sock`. Its environment contains the internal token and sandbox settings, excluding Discord, provider and Supabase credentials. The runner is a trusted Docker administrator; an execution-container boundary does not make the runner itself unprivileged. The backend and bot images copy selected source directories, and `.dockerignore` excludes local credentials and MCP secrets.

The backend publishes **127.0.0.1:8002**. The runner listens on **8001 inside the Compose network**, with no host port. The bot uses `http://backend:8002`; the backend uses `http://sandbox-runner:8001`. All three receive the same internal key. Keep the Docker socket and internal API off public networks.

Check service health:

```bash
docker compose ps
curl --fail http://127.0.0.1:8002/health
docker compose exec backend python -c "import httpx; print(httpx.get('http://sandbox-runner:8001/health').json())"
docker compose logs --tail=100 backend sandbox-runner bot
```

For authenticated status/API requests, send `X-Zauq-Token` to the backend. The backend uses `X-Internal-Token` for the runner. `/health` is public liveness, not a guarantee that providers, database or execution images work. `/sandbox status` reports runner availability; execute a small permitted `/run` to verify the entire mount path.

## Separate processes / PM2

Launch from the repository root so imports, `.env` and relative paths resolve correctly:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8002
python -m uvicorn backend.sandbox.runner_service:app --host 127.0.0.1 --port 8001
python -m bot.client
```

Set `SANDBOX_RUNNER_URL=http://127.0.0.1:8001`. Run the runner under a separately controlled Docker-capable identity; the backend should not share that privilege. For processes on the same host without a containerized runner, leave both spool settings blank to use host temporary files. The included [infra/pm2.config.js](infra/pm2.config.js) supervises backend and bot without hard-coded installation paths; supervise the privileged runner separately.

```bash
pm2 start infra/pm2.config.js
pm2 logs
```

Do not run development reload mode under production supervision. If an API must be exposed beyond loopback, configure authentication, TLS and a trusted network boundary deliberately; Compose does not publish the runner.

## Scoped rollout

1. Verify ordinary chat, chosen model, files, memory and the fallback disclosure with both master flags off.
2. Set `AGENT_ALLOWED_GUILD_IDS` and/or `AGENT_ALLOWED_CHANNEL_IDS` to your test IDs, then enable `AGENT_RUNTIME_ENABLED` and restart the backend. A nonempty list restricts access; both list checks must pass when both are configured.
3. Use `/agent enable enabled:true scope:Channel` or `scope:Server`. Saved channel preference overrides server preference, but cannot bypass a master disable or operator allowlist. `/agent status` shows effective settings. Persistence requires Supabase.
4. Test quick/deep search and explicit search disable. Verify unavailable-key behavior, snippet labels and bounded citations.
5. Enable execution permission on a test channel. Auto mode is separate: `off` permits manual `/run`, `auto` allows relevant lightweight testing, and `always` requests testing for runnable code tasks. Explicit permission `false` remains a denial after mode updates.
6. Add one read-only MCP server, then enable `MCP_ENABLED` and its rollout allowlists. Supply guild scope and explicit allowed tools. Verify out-of-scope denial before considering write tools.
7. Exercise approval, denial, expiry, changed scope and concurrent clicks. Claims are at-most-once attempts; a crash after claiming may leave an unknown external outcome. Check the external system before staging a replacement action.
8. Review usage, deadlines and resource measurements before expanding access.

## MCP configuration

Copy [config/mcp_servers.example.json](config/mcp_servers.example.json) to `config/mcp_servers.json`. Examples are disabled and require a real server/endpoint. Config is trusted operator input and is never accepted from chat. Prefer `${VARIABLE}` references for tokens.

Servers support `stdio` and `streamable_http`; SSE is not implemented. Omitted guild scope denies tool access. An explicit `allow_global_access:true` grants global scope; otherwise supply `allowed_guild_ids`. New discovered tools stay disabled unless named in `allowed_tools` or given a local `tool_risks` classification. Default risk is `write`; use `read` only for tools you have verified. `selection_keywords` controls cheap relevance routing for non-GitHub services.

Mount the actual operator config read-only into the backend when enabling MCP in Compose, and set `MCP_CONFIG_PATH` to that mounted path. It is intentionally excluded from images. Do not pass all backend credentials to a stdio server; configure only its required environment. Reconnection backs off and stops after five failures; an operator refresh restarts attempts.

## Required release checks

CI must pass syntax/imports, dependency consistency, hermetic regressions, actual MCP transports, repeat PostgreSQL/pgvector migrations, real Docker execution/cancellation and the Compose spool topology. Local mock results do not replace those gates.

Controlled staging must additionally verify Discord mentions/replies/DMs/threads, uploads and voice notes, model switching, fallback, memory/lore, moderation, media, reminders/XP, manual and automatic sandbox execution, scoped MCP and signed buttons. Verify database RLS with non-service-role credentials, actual model availability and account prices. Measure p50/p95 latency and memory/CPU under realistic concurrency. Automated tests do not establish these live results.

## Rollback and recovery

Disable agent/MCP master flags and automatic code testing first; ordinary direct chat remains available. Keep additive columns in place when rolling application code back. Do not replay executed/claimed actions. Preserve database backups and verify the target version can read current text policy fields before restoring it. Restore data only through your normal database recovery procedure.

If execution reports a mount error, verify the daemon-host spool path and ownership. If it reports image absence, pre-pull the configured image on that Docker daemon. If auth returns 401, verify all service keys match; 503 with a blank key means development bypass is off. If metrics fall back to in-memory, check migration 005, service-role credentials and RPC permissions. A provider failure needs an account/model availability check; autocomplete does not validate those remotely.
