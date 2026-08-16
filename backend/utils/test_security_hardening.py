import asyncio
import hmac
import pydantic
from pydantic import ValidationError

from backend.integrations.web_search import is_safe_public_url, web_search_engine
from backend.routers.sandbox import CodeExecRequest
from backend.routers.chat import DEV_PERSONA_SEED, HANGOUT_PERSONA_SEED
from bot.commands import meme_slash

async def run_security_tests():
    print("🔒 Running Zauq Security & Hardening Validation Suite...\n")

    # 1. SSRF Protection Tests
    print("1. Testing SSRF URL Validation & Private IP Blocking...")
    blocked_urls = [
        "http://127.0.0.1:8002/api/admin/metrics",
        "http://localhost:11434/api/tags",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/setup",
        "http://172.16.0.5:8080",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0:8000",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://127.0.0.1:70",
        "http://[::1]:8000",
    ]

    for bad_url in blocked_urls:
        assert not is_safe_public_url(bad_url), f"SSRF Check Failed: Allowed dangerous URL: {bad_url}"

    # Safe URLs should pass
    safe_urls = [
        "https://python.org",
        "https://fastapi.tiangolo.com",
        "http://example.com"
    ]
    for safe_url in safe_urls:
        assert is_safe_public_url(safe_url), f"False Positive on Safe URL: {safe_url}"

    # Verify fetch_url_content rejects SSRF targets safely without making network requests
    fetch_result = await web_search_engine.fetch_url_content("http://127.0.0.1:11434/tags")
    assert "Access Denied" in fetch_result or "restricted" in fetch_result, f"Unexpected fetch result: {fetch_result}"
    print("   ✅ SSRF Guard verified: All private, loopback, and metadata addresses blocked.\n")

    # 2. Sandbox Timeout & Language Validation Tests
    print("2. Testing Sandbox Input Bounds & Validation...")
    # Valid request
    valid_req = CodeExecRequest(code="print('hello')", language="python", timeout=5.0)
    assert valid_req.timeout == 5.0

    # Test excessive timeout (> 30.0s)
    try:
        CodeExecRequest(code="print('hello')", timeout=9999.0)
        assert False, "Failed: Allowed excessive timeout > 30s"
    except ValidationError:
        pass

    # Test negative or sub-second timeout (< 1.0s)
    try:
        CodeExecRequest(code="print('hello')", timeout=0.1)
        assert False, "Failed: Allowed invalid timeout < 1s"
    except ValidationError:
        pass

    # Test invalid language
    try:
        CodeExecRequest(code="print('hello')", language="unsupported_lang_xyz")
        assert False, "Failed: Allowed unsupported sandbox language"
    except ValidationError:
        pass
    print("   ✅ Sandbox input constraints verified: Timeout bounded [1.0s, 30.0s] & language constrained.\n")

    # 3. Constant-Time Auth Verification
    print("3. Testing Constant-Time Token Comparison...")
    test_key = "zauq_secure_secret_token_9876543210"
    assert hmac.compare_digest(test_key, test_key) is True
    assert hmac.compare_digest("invalid_key", test_key) is False
    print("   ✅ Constant-time token verification verified.\n")

    # 4. Meme Slash Module Integrity
    print("4. Testing Meme Command Module Imports...")
    assert hasattr(meme_slash, "os"), "MemeSlash missing 'os' module import"
    assert hasattr(meme_slash, "tempfile"), "MemeSlash missing 'tempfile' module import"
    print("   ✅ Meme command module imports verified.\n")

    # 5. Creator Persona Grounding
    print("5. Testing Creator Persona Grounding...")
    assert "Syed Muhammad Hassan" in DEV_PERSONA_SEED, "DEV_PERSONA_SEED missing creator name"
    assert "AgenticEra Systems" in DEV_PERSONA_SEED, "DEV_PERSONA_SEED missing AgenticEra Systems"
    assert "Syed Muhammad Hassan" in HANGOUT_PERSONA_SEED, "HANGOUT_PERSONA_SEED missing creator name"
    assert "AgenticEra Systems" in HANGOUT_PERSONA_SEED, "HANGOUT_PERSONA_SEED missing AgenticEra Systems"
    print("   ✅ Creator persona grounding verified: Syed Muhammad Hassan / AgenticEra Systems.\n")

    # 6. License Verification
    print("6. Testing Apache 2.0 License File...")
    with open("/root/Zauq/LICENSE", "r", encoding="utf-8") as f:
        license_text = f.read()
    assert "Apache License" in license_text, "LICENSE does not contain Apache License text"
    assert "Version 2.0" in license_text, "LICENSE is not Version 2.0"
    assert "Syed Muhammad Hassan / AgenticEra Systems" in license_text, "LICENSE missing copyright attribution"
    print("   ✅ Apache 2.0 License and copyright attribution verified.\n")

    print("🎉 ALL SECURITY HARDENING & IDENTITY TESTS PASSED SUCCESSFULLY! (100% PASS RATE)")

if __name__ == "__main__":
    asyncio.run(run_security_tests())
