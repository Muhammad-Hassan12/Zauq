# Using Zauq v4

Mention Zauq, reply directly to its message, send it a DM or use a conversation thread. Ordinary conversation does not require slash commands. Attach a supported document, image or voice note to ask about it. Availability, stored settings and remote services depend on the operator's deployment.

## Model and mode controls

`/model status` reports the selected provider/model and whether it came from the channel or server. `/model set` takes a tier, provider, optional model ID and channel/server scope; `/model reset` removes the channel override. Model resolution is channel → server → system default. A valid custom model ID is accepted, but account availability is checked by the provider when used, not by autocomplete.

| Tier | Providers |
| --- | --- |
| 1 | Gemini, DigitalOcean, Anthropic, Qwen, DeepSeek |
| 2 | Ollama |
| 3 | Kaggle worker |

`/mode` chooses Dev or Hangout for a channel or server. `/mode_reset` clears a channel override. A mode update preserves explicit execution denial and saved auto-test policy. Dev Mode's technical persona alone does not authorize a request to run code.

`/thinking` saves a native-reasoning preference. Its response distinguishes requested and effective support. The implementation enables only verified native controls; unsupported models do not receive a hidden reasoning instruction. Provider-native private thoughts/signatures are preserved internally for continuation and excluded from the visible answer.

Provider fallback may change the answering model when a provider fails before tool execution. The response discloses it. If tools already ran and the model fails, the runtime returns an incomplete result instead of replaying the loop. Images/audio on a non-native model may require external preprocessing; see [PRIVACY.md](PRIVACY.md).

Model IDs and lifecycle change. Gemini 2.5 API access is restricted to existing users in the current [Google model guide](https://ai.google.dev/gemini-api/docs/models). Claude Sonnet 4.5 is currently scheduled for retirement on 30 November 2026 in [Anthropic's deprecation guide](https://platform.claude.com/docs/en/about-claude/model-deprecations). Existing defaults are preserved for compatibility; operators should validate their account and choose an appropriate supported model before rollout. DeepSeek defaults use `deepseek-flash`; retired chat/reasoner aliases are no longer suggested. [DeepSeek lifecycle notice](https://api-docs.deepseek.com/news/news260424/).

## Web research

Use `/search query:your question deep:false` for a quick lookup, or `deep:true` for deeper research. Categories are `all`, `github`, `arxiv`, `docs`, `wikipedia` and `news`. The command defaults to deep research; choose false when speed is preferable.

Quick research performs one query and visits at most two pages. Deep research performs up to three complementary queries, with one fallback for an empty result set, and visits at most five unique pages. Serper credentials are required; unavailable search is disclosed instead of presented as live evidence. Page failures may degrade to labeled search snippets, which are not verified page content. Citations are restricted to retrieved sources; retrieval does not itself prove every generated claim.

Normal chat uses the same retrieval service when a request needs current information. API clients can explicitly set `enable_web_search:false` to prevent search and URL fetching. Search is independent of the agent master switch, so basic retrieval remains available with the agent disabled.

## Code execution

`/run` executes a provided Python, JavaScript or Bash snippet in the sandbox; the message context menu can run a selected snippet too. The channel must permit execution. The runner enforces no networking, non-root execution, read-only code mounts and resource/time/output caps. Execution results show success, stdout/stderr, timeout and truncation.

`/sandbox status` checks runner limits. `/sandbox auto_mode` chooses:

| Policy | Behavior |
| --- | --- |
| `off` | No automatic code testing; permitted manual `/run` remains available |
| `auto` | Exposes execution for relevant runnable code tasks; the model decides whether a lightweight check helps |
| `always` | Requests testing for runnable code output; casual conversation stays tool-free |

Automatic testing also requires channel permission and an enabled agent with a native-tool model. One corrected retry can follow a failed run when configured. Code needing packages, network access, secrets or a full application environment may not be runnable in this sandbox; the answer should disclose what was actually tested.

## Tools, MCP and approvals

`/agent status` shows effective runtime/MCP settings, budgets and auto mode for the current channel. `/agent tools` shows the backend's guild-visible registry with pagination. Administrators can save `/agent enable enabled:true/false` for Channel or Server scope. Operator master flags and allowlists take precedence; a saved enable does not bypass them.

`/mcp status` reports connection health; `/mcp tools` lists the configured external tools visible to the current guild. The operator chooses trusted servers, grants tools and classifies risks. Discovery alone does not authorize a tool. DMs cannot use guild-only tools.

A write/destructive call creates a pending action with its tool, arguments, risk and initiating user. Review the preview; for a large payload, **Review arguments** downloads the complete sanitized JSON. The initiating user or a Discord administrator may click **Approve** or **Deny**. Only an approved, intact, unexpired action can be claimed for execution. Approvals expire after five minutes.

Repeated clicks cannot start the same action twice. A claim is an at-most-once attempt: a timeout or crash can leave the external outcome uncertain. Verify the target system before creating a replacement action. If the tool, risk or scope changes, execution can be refused even after approval. Denial and expiry do not execute the tool.

## Command reference

| Commands | Purpose |
| --- | --- |
| `/mode`, `/mode_reset` | Channel/server persona configuration |
| `/model status`, `/model set`, `/model reset` | Selection and inheritance |
| `/thinking`, `/info` | Reasoning preference and current engine information |
| `/search` | Quick/deep web research and category selection |
| `/run`, `/sandbox status`, `/sandbox auto_mode` | Manual execution and testing policy |
| `/agent status`, `/agent tools`, `/agent enable` | Runtime status, registry and scoped preference |
| `/mcp status`, `/mcp tools` | External connection/tool visibility |
| `/file generate`, `/create_file` | Generate a downloadable standalone file |
| `/export`, `/summarize` | Export or summarize recent context |
| `/remember`, `/ingest_repo` | Add server lore or a repository README |
| `/github pr`, `/github issue` | Read and summarize GitHub items |
| `/voice join`, `/voice leave`, `/tts` | Voice-channel connection and speech output |
| `/image`, `/meme`, `/trivia` | Media and community activities |
| `/remind`, `/rank`, `/leaderboard`, `/stats` | Reminders, participation and usage statistics |
| `/moderation enable`, `/moderation sensitivity`, `/moderation log` | Server moderation controls |
| `/admin memory`, `/admin channels`, `/admin set_role` | Administrative configuration and statistics |
| `/forget`, `/privacy` | Delete existing episodic facts and inspect disclosure |

The owner-only `!sync` maintenance command refreshes Discord command registration. Exact availability/permissions are enforced by each command and server configuration. Approval is through buttons; there is no shipped `/approve` command. Deep research uses `/search deep:true`; there is no separate `/research` command.

## Files, privacy and troubleshooting

`/file generate` and `/create_file` use the separate direct-generation timeout and return sanitized download bytes. Documents and model output can be truncated to protect resources; parsing is not lossless for every format. `/api/chat/stream` buffers generation and then chunks the checked answer, so it does not provide incremental token delivery.

`/forget` deletes existing episodic facts only; it is not a permanent opt-out and does not delete Discord history, lore, logs or provider copies. New conversations may produce new facts. Consult [PRIVACY.md](PRIVACY.md) and your operator for broader controls.

For missing tools, inspect `/agent status`, `/mcp status`, guild grants and native model support. For execution failure, inspect permission, auto mode, runner status and the actual stderr/timeout. For a model failure, the operator should check its endpoint, key and account model access. `/stats` estimates use configured model rates and reported usage; unknown costs are not zero, and external service fees are separate.
