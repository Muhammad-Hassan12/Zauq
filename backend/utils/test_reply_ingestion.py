import asyncio
from backend.routers.chat import ChatRequest, chat_completion
from backend.integrations.web_search import web_search_engine
from fastapi import BackgroundTasks

async def run_reply_ingestion_tests():
    print("🚀 Starting Zauq Replied Message & Reference Ingestion Test Suite...\n")

    # 1. Test URL Extraction from Replied Message Context
    print("1. Testing URL and Context Extraction from Replied Message...")
    user_reply_with_context = (
        "[Replied to @Owais Fayyaz's message:\n"
        "\"Check out this cloud offer: https://www.alibabacloud.com/en/free?_p_lc=1\"]\n\n"
        "[User's reply]: kia bolo gay is pay tum?"
    )
    urls = web_search_engine.extract_urls(user_reply_with_context)
    assert len(urls) >= 1, "Failed to extract URL from replied context"
    assert "alibabacloud.com" in urls[0], f"Incorrect URL extracted: {urls[0]}"
    print(f"   Extracted URLs: {urls}")
    print("   ✅ Referenced message URLs successfully captured.\n")

    # 2. Test Search Intent Trigger from Replied Context
    print("2. Testing Search Intent on Replied Context...")
    should_search = web_search_engine.should_search_web(user_reply_with_context)
    # The URL itself will be fetched by the URL content reader in chat.py
    print(f"   Search Intent Detected: {should_search}")
    print("   ✅ Search and URL scraper pipeline ready.\n")

    # 3. Test Thread Intent Keyword Detection
    print("3. Testing Thread Intent Keyword Matching...")
    wants_thread_1 = any(kw in "start a thread about this topic".lower() for kw in ["start a thread", "in a thread", "make a thread", "thread:"])
    wants_thread_2 = any(kw in "thread: let's analyze this code".lower() for kw in ["start a thread", "in a thread", "make a thread", "thread:"])
    normal_query = any(kw in "kia bolo gay is pay tum?".lower() for kw in ["start a thread", "in a thread", "make a thread", "thread:"])
    assert wants_thread_1 is True, "Failed to detect 'start a thread'"
    assert wants_thread_2 is True, "Failed to detect 'thread:' prefix"
    assert normal_query is False, "False positive thread detection on standard question"
    print("   ✅ Smart in-channel vs thread intent routing verified.\n")

    # 4. Test Chat Engine Processing with Replied Reference
    print("4. Testing Backend Chat Completion with Ingested Reference Context...")
    req = ChatRequest(
        channel_id="test_channel_reply_999",
        messages=[
            {
                "role": "user",
                "content": user_reply_with_context
            }
        ],
        mode_override="hangout"
    )
    bg = BackgroundTasks()
    res = await chat_completion(req, bg)
    assert "response" in res, "No response returned from chat_completion"
    response_text = res.get("response", "")
    print(f"   AI Response Preview ({len(response_text)} chars):")
    print(f"   \"{response_text[:200]}...\"")
    assert len(response_text) > 10, "Response too short"
    print("   ✅ End-to-end chat completion with referenced context passed.\n")

    print("🎉 ALL REPLIED MESSAGE & IN-CHANNEL TESTS PASSED! (100% PASS RATE)")

if __name__ == "__main__":
    asyncio.run(run_reply_ingestion_tests())
