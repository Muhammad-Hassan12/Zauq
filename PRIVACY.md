# Zauq privacy and data handling

**Updated:** 3 October 2026. **Project maintainer:** Syed Muhammad Hassan / AgenticEra Systems.

This document describes the repository's data flows. The operator of each deployed bot chooses accounts, hosting, access controls and retention. Ask that operator for the contact and policies applicable to your instance; this repository does not supply a universal privacy guarantee for every deployment.

## What is processed

Zauq reads messages and relevant context when mentioned, replied to, messaged privately or used in threads. Attachments can include text, documents, images and audio/voice notes. User names and Discord user, guild and channel IDs identify context and settings. Server features may also process participation for XP, reminder content and moderation events even when an AI reply is not requested.

The bot/backend may send the prompt, relevant history, configured persona, retrieved memories/lore and attachment content to the selected model provider. Optional background memory extraction and embeddings create additional processing requests. These processes are distinct from storing request counters.

## External recipients

| Feature | Possible recipient/data |
| --- | --- |
| Model inference | Gemini, Anthropic, Alibaba Qwen, DeepSeek, DigitalOcean, or the configured Ollama/Kaggle endpoint; prompt/context and supported media |
| Fallback and media preprocessing | Gemini OCR and fallback, or the configured audio transcription service; media or associated prompt |
| Research | Serper receives search queries; Jina Reader receives requested URLs; target websites receive direct fetch requests |
| MCP | Operator-configured external servers receive tool arguments and return results; approved actions may change external data |
| Voice/media | TTS and image-generation services receive text/prompts and other request data required by the feature |
| Persistence | Operator's Supabase database stores application records and embeddings |
| Delivery/hosting | Discord and the operator's hosting/network services process delivery, infrastructure and operational data |

Choosing a local model does not automatically disable remote search, image/audio preprocessing, embeddings or fallback. `/model status` shows the selected model; responses disclose model fallback. Ask the operator which optional services are enabled before sending sensitive content.

Zauq has no model-training pipeline, but cannot promise how third parties handle submitted data. Provider terms depend on the account, product and settings. For example, Google's Gemini terms distinguish unpaid and paid service data use. Review [Gemini's current terms](https://ai.google.dev/gemini-api/terms) and the applicable terms for every other configured provider. Do not assume a free quota and paid account have identical data policies.

## Stored information and retention

- **Conversation context:** bot/backend context used for replies and optional summaries; Discord also retains its own messages.
- **Episodic memory:** extracted personal/preference/project facts and optional vector embeddings in `user_memories`. Facts are not guaranteed to be perfectly accurate; decay/pruning may remove low-importance records. There is no universal maximum age for all facts.
- **Server lore:** facts, rules or imported repository/document information in `server_lore`.
- **Configuration:** guild/channel preferences, model choices and administrative roles.
- **Community records:** XP/stats, reminders and moderation logs where enabled.
- **Metrics:** user/guild/channel IDs, model, latency, token usage when reported, tool counters, cost estimates and execution IDs. Request metrics intentionally exclude full prompts and tool arguments. Database metrics have no automatic retention period in this implementation; the operator must configure one.
- **Pending approvals:** tool name, arguments, risk, initiating user and scope, signature and timestamps. Validity is capped at five minutes. Maintenance runs approximately every minute. Durable terminal records are removed after their expiry is more than 24 hours old; offline terminal records have a shorter bounded local retention. Database outages can delay maintenance.
- **Operational logs and temporary files:** redacted operational records and short-lived execution/media files. File logs rotate at 10 MB with five backups per process. Retention varies with hosting, logs and backup configuration.

Secrets are scrubbed from model-visible tool results, final text, previews and generated download bytes. This is a protective control, not a reason to submit credentials or a guarantee that every possible secret format is recognized. Operator backups and third-party copies have separate retention.

## User controls

`/forget` deletes the existing episodic-memory rows associated with your Discord user ID. It does **not** delete Discord messages, server lore, metrics, XP, reminders, moderation records, already submitted provider data or backups. It does not permanently opt you out of future memory extraction; later conversations can create new facts, and already-running extraction jobs may need operator attention.

`/privacy` gives a brief disclosure. `/model status` and `/agent status` show configuration, and approval previews let the initiating user or a Discord administrator review, approve or deny mutating actions. Do not approve an action you do not understand; large argument payloads can be downloaded using **Review arguments**.

For broader deletion, retention changes, correction or an instance-specific privacy request, contact the bot/server operator through that community's published support channel. Operators should provide a contact, disclose enabled providers and data locations, limit access, set retention and maintain deletion procedures appropriate to their deployment.
