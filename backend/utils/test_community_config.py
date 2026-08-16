import asyncio
import httpx
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"

async def run_tests():
    print("🚀 Starting Community Configuration & RBAC Tests...")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Test Model Status default
        res = await client.get(f"{BACKEND_URL}/api/model/status?channel_id=test_chan_1&guild_id=test_guild_1")
        assert res.status_code == 200, f"Status failed: {res.text}"
        data = res.json()
        print("✅ Default Model Status:", data.get("provider"), data.get("model_name"), "Scope:", data.get("scope"))

        # 2. Test Set Server Default Model
        set_server_payload = {
            "guild_id": "test_guild_1",
            "scope": "server",
            "tier": 1,
            "provider": "google",  # Test 'google' alias normalization
            "model_name": "gemini-2.5-pro",
            "updated_by": "TestAdmin"
        }
        res = await client.post(f"{BACKEND_URL}/api/model/set", json=set_server_payload)
        assert res.status_code == 200, f"Set server model failed: {res.text}"
        print("✅ Server Default Model Set:", res.json())

        # 3. Test Channel Inheritance of Server Default
        res = await client.get(f"{BACKEND_URL}/api/model/status?channel_id=test_chan_1&guild_id=test_guild_1")
        data = res.json()
        assert data.get("model_name") == "gemini-2.5-pro", f"Expected gemini-2.5-pro, got {data.get('model_name')}"
        assert data.get("is_server_default") is True, "Expected is_server_default == True"
        print("✅ Channel inherits Server Default:", data.get("model_name"), "Scope:", data.get("scope"))

        # 4. Test Channel-Specific Override
        set_channel_payload = {
            "channel_id": "test_chan_1",
            "guild_id": "test_guild_1",
            "scope": "channel",
            "tier": 1,
            "provider": "digitalocean",
            "model_name": "glm-5.2",
            "updated_by": "DevLead"
        }
        res = await client.post(f"{BACKEND_URL}/api/model/set", json=set_channel_payload)
        assert res.status_code == 200, f"Set channel model failed: {res.text}"
        print("✅ Channel Override Set:", res.json())

        # 5. Verify Channel has Override while Another Channel inherits Server Default
        res_ch1 = await client.get(f"{BACKEND_URL}/api/model/status?channel_id=test_chan_1&guild_id=test_guild_1")
        res_ch2 = await client.get(f"{BACKEND_URL}/api/model/status?channel_id=test_chan_2&guild_id=test_guild_1")
        assert res_ch1.json().get("model_name") == "glm-5.2", "Chan 1 should have override glm-5.2"
        assert res_ch1.json().get("is_channel_override") is True, "Chan 1 should be channel override"
        assert res_ch2.json().get("model_name") == "gemini-2.5-pro", "Chan 2 should inherit server default gemini-2.5-pro"
        print("✅ Channel 1 has override (glm-5.2) and Channel 2 has server default (gemini-2.5-pro)")

        # 6. Test Channel Reset
        res = await client.post(f"{BACKEND_URL}/api/model/reset?channel_id=test_chan_1")
        assert res.status_code == 200, f"Reset failed: {res.text}"
        res_after_reset = await client.get(f"{BACKEND_URL}/api/model/status?channel_id=test_chan_1&guild_id=test_guild_1")
        assert res_after_reset.json().get("model_name") == "gemini-2.5-pro", "After reset, Chan 1 should inherit server default"
        print("✅ Channel 1 reset successfully and reverted to server default gemini-2.5-pro")

        # 7. Test Admin Set Role
        res = await client.post(f"{BACKEND_URL}/api/admin/set_role", json={"guild_id": "test_guild_1", "role_id": "1234567890"})
        assert res.status_code == 200, f"Set role failed: {res.text}"
        cfg_res = await client.get(f"{BACKEND_URL}/api/admin/config?guild_id=test_guild_1")
        assert cfg_res.json().get("admin_role_id") == "1234567890", "Admin role ID mismatch"
        print("✅ Admin Role Set and verified in config:", cfg_res.json().get("admin_role_id"))

        # Clean up test guild
        await client.post(f"{BACKEND_URL}/api/admin/set_role", json={"guild_id": "test_guild_1", "role_id": None})
        print("🎉 ALL COMMUNITY & RBAC TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())
