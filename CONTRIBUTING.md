# Contributing to Zauq

Read [ARCHITECTURE.md](ARCHITECTURE.md), the relevant phase in [v4-Update.md](v4-Update.md), and existing tests before changing behavior. Keep Discord delivery, orchestration, providers, tools and sandbox execution in their established layers. Finish a phase with passing checks and a short changelog before starting the next.

## Development

Use Python 3.11/3.12 and install `requirements.txt` in a virtual environment. Copy `.env.example` only for manual development; never commit credentials or an operator MCP config. Tests deliberately disable `.env`, clear external credentials and refuse external socket connections. Mock paid providers explicitly, including the credentials required to reach a mocked transport.

```bash
python -m pytest -q
python -m compileall -q backend bot tests
pip check
```

Tests live in `tests/`; historical utility probes in `backend/utils/` are not a replacement for pytest and may require deliberate runtime setup. The real MCP stdio and HTTP fixtures are owned by `tests/mcp/fixtures/`.

## External integration gates

PostgreSQL tests create and remove disposable `zauq_test_*` databases on a loopback-only cluster. Use an isolated cluster with an administrative test role, never a deployment database:

```bash
ZAUQ_TEST_POSTGRES_DSN=postgresql://postgres:test-password@127.0.0.1:5432/postgres python -m pytest tests/memory -q
```

The CI PostgreSQL image contains pgvector. Set `ZAUQ_REQUIRE_PGVECTOR=true` to fail rather than skip the fresh-schema gate when that extension is absent. Tests cover fresh-schema reruns, ordered existing-install upgrades, early boolean repair, provider constraints, RLS and metrics RPC execution.

For real Docker tests, pre-pull the images listed in deployment docs, then opt in:

```bash
ZAUQ_RUN_DOCKER_TESTS=true python -m pytest tests/sandbox/test_real_docker.py -q
```

These tests verify mounted code, the execution UID, blocked networking and container removal after cancellation. They require a Docker-capable test identity. CI additionally builds the separate images and checks bot-to-backend connectivity and backend-to-runner host mounts. A skipped integration gate is unverified, not passed.

## Invariants

- Register tool schemas and valid aliases atomically; reject remote schema references. Validate arguments before dispatch.
- Enforce request selection, guild scope, master flags and channel execution permissions independently of model instructions. Omitted MCP scope and newly discovered ungranted tools must deny access.
- Treat documents, web content and MCP output as untrusted data. Keep them out of authorization/relevance decisions.
- Preserve provider-native signed/opaque continuation blocks without displaying or logging private reasoning. Do not imitate native thinking with a hidden prose instruction.
- Respect total deadlines, global/configured tool caps and per-resource limits. Keep cancellation cleanup and bounded output streaming intact.
- Write/destructive tools require signed approval. Claim execution atomically before the handler, recheck current policy and never replay a claimed action after an uncertain outcome.
- Keep search ownership in chat orchestration and `SearchService`. Do not add hidden provider-side searches to standard chat preprocessing.
- Sanitize downloadable bytes as well as previews. Credentials belong in trusted transport configuration, never model arguments or action previews.
- Persist truthful telemetry. Unknown usage/rates remain unknown; model estimates exclude unrelated external charges.
- Add numbered idempotent migrations and keep the fresh schema consistent. Preserve existing channel preferences during unrelated updates.

## Pull requests

Describe the concrete trigger, previous behavior and resulting behavior. Include the relevant tests and any external gate that remains unverified. Update examples, privacy disclosures and user guidance when their behavior changes. Avoid unrelated refactors, new heavyweight services or claims of live readiness based only on mocks. Preserve feature flags off by default.
