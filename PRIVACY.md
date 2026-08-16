# Privacy Policy & Data Handling Disclosure — Zauq Bot

**Effective Date:** July 2026  
**Provider:** Hassan / AgenticEra Systems  

## 1. Overview
Zauq is an AI assistant powered by a hybrid multi-provider architecture designed to serve technical assistance (Dev Mode) and interactive server conversation (Hangout Mode). This document outlines what data is processed, stored, and how privacy is maintained.

## 2. Information We Process
When interacting with Zauq in a Discord server, the bot processes:
- **Message Content:** Text content of messages sent in channels where Zauq is tagged or active.
- **User Metadata:** Discord User IDs and Usernames to associate preferences and episodic memory.
- **Guild & Channel Identifiers:** Server and channel IDs to maintain channel-specific configuration modes and model selection preferences.

## 3. External AI Processing
Depending on the model tier explicitly configured for a channel using `/model set`, your message prompt and relevant conversation history are transmitted to:
1. **Google Gemini API** (Tier 1 Primary) — Processed under Google Generative AI API privacy terms.
2. **DigitalOcean Gradient Serverless Inference** (Tier 1 Alternative) — Processed under DigitalOcean API policies.
3. **Self-Hosted Ollama / Qwen3.5-4B** (Tier 2 Local) — Processed entirely on local infrastructure (Contabo VPS). No external third-party transmission.
4. **Kaggle T4 Tunneled Model** (Tier 3 Batch) — Processed on self-managed Kaggle T4 worker instance via secure Cloudflare tunnel.

> **Zero Model Training Guarantee:** Message content is strictly used to generate immediate model responses and manage conversation context. **No user messages are sent to third parties for fine-tuning or model training.**

## 4. Data Storage & Vector Memory
- **Episodic User Memories:** Facts explicitly provided by users (e.g. preferences, past interactions) are extracted asynchronously and stored as vector embeddings in a private Supabase database (`user_memories` table).
- **Retention Period:** Stored indefinitely until manual server/user deletion request.

## 5. User Controls & Data Deletion
Users have full rights over their stored data:
- To permanently delete all stored episodic memory associated with your Discord User ID, use the **`/forget`** slash command directly in any channel where Zauq is active. This is irreversible and processed immediately.
- Server administrators can reconfigure or reset channel profiles and stored lore at any time.

---
*AgenticEra Systems*
