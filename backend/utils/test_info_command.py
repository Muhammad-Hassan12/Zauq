import asyncio
from backend.version import ZAUQ_VERSION
from backend.config import settings
from backend.routers.model import get_full_system_info

async def run_info_tests():
    print("🚀 Starting Zauq System Specifications & /info Test Suite...\n")

    # 1. Test get_full_system_info endpoint
    print("1. Testing /api/model/info endpoint execution...")
    info_data = await get_full_system_info(channel_id="test_channel_123", guild_id="test_guild_456")
    
    assert "engine" in info_data, "Missing engine specs"
    assert "model" in info_data, "Missing model specs"
    assert "persona" in info_data, "Missing persona specs"
    assert "limits" in info_data, "Missing limits specs"
    assert "capabilities" in info_data, "Missing capabilities specs"
    print("   ✅ All top-level specification categories present.\n")

    # 2. Verify Engine & Attribution
    engine = info_data["engine"]
    assert engine["version"] == ZAUQ_VERSION
    assert info_data["limits"]["sandbox_timeout_s"] == settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS
    assert engine["name"] == "Zauq (ذوق)", f"Incorrect name: {engine['name']}"
    assert "Syed Muhammad Hassan" in engine["creator"], f"Incorrect creator: {engine['creator']}"
    assert "Apache" in engine["license"], f"Incorrect license: {engine['license']}"
    print(f"   Engine: {engine['name']} v{engine['version']}")
    print(f"   Creator: {engine['creator']}")
    print(f"   License: {engine['license']}")
    print("   ✅ Engine identity & Apache 2.0 attribution verified.\n")

    # 3. Verify Model Routing & Tokens Bounds
    model = info_data["model"]
    limits = info_data["limits"]
    assert limits["input_tokens_max"] == 30000, f"Incorrect input limit: {limits['input_tokens_max']}"
    assert limits["output_tokens_max"] == 65536, f"Incorrect output limit: {limits['output_tokens_max']}"
    assert limits["history_window"] == 8, f"Incorrect history limit: {limits['history_window']}"
    print(f"   Active Provider: {model['provider']}")
    print(f"   Active Model: {model['model_name']}")
    print(f"   Input Token Limit: {limits['input_tokens_max']:,} tokens (~120k chars)")
    print(f"   Output Token Limit: {limits['output_tokens_max']:,} tokens (~250k chars)")
    print(f"   History Window: {limits['history_window']} messages")
    print("   ✅ Token limits and model routing verified.\n")

    # 4. Verify Capabilities Subsystems
    caps = info_data["capabilities"]
    assert "Serper" in caps["web_search"], "Missing Serper in search status"
    assert "19 Voices" in caps["voice_tts"], "Missing 19 voices in TTS"
    assert "pgvector" in caps["memory"], "Missing pgvector in memory"
    print(f"   Search Subsystem: {caps['web_search']}")
    print(f"   Voice Subsystem: {caps['voice_tts']}")
    print(f"   Memory Subsystem: {caps['memory']}")
    print("   ✅ Intelligence subsystems verified.\n")

    print("🎉 ALL /info SPECIFICATION TESTS PASSED! (100% PASS RATE)")

if __name__ == "__main__":
    asyncio.run(run_info_tests())
