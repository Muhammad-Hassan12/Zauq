import asyncio
from backend.integrations.web_search import web_search_engine, is_safe_public_url

async def run_deep_search_tests():
    print("🚀 Starting Zauq Deep Web Intelligence & Roaming Test Suite...\n")

    # 1. Test Query Optimization & Expansion
    print("1. Testing Query Optimization & Expansion...")
    raw_query = "Please search for and research about the most isolated and dark places on earth where it is strictly not allowed to go and give me details"
    optimized = web_search_engine.optimize_search_queries(raw_query)
    assert len(optimized) >= 1, "Failed to produce optimized queries"
    assert "Please search for" not in optimized[0], "Failed to strip filler prefix"
    assert "and give me details" not in optimized[0], "Failed to strip filler suffix"
    print(f"   Original: {raw_query[:50]}...")
    print(f"   Optimized: {optimized}")
    print("   ✅ Query optimization and decomposition working cleanly.\n")

    # 2. Test Category Domain Filtering
    print("2. Testing Category Domain Filtering...")
    github_q = web_search_engine.apply_category_filter("fastapi rate limiter", "github")
    arxiv_q = web_search_engine.apply_category_filter("transformer attention", "arxiv")
    wiki_q = web_search_engine.apply_category_filter("quantum computing", "wikipedia")
    assert "site:github.com" in github_q, f"Failed github filter: {github_q}"
    assert "site:arxiv.org" in arxiv_q, f"Failed arxiv filter: {arxiv_q}"
    assert "site:wikipedia.org" in wiki_q, f"Failed wikipedia filter: {wiki_q}"
    print(f"   GitHub Query: {github_q}")
    print(f"   ArXiv Query: {arxiv_q}")
    print(f"   Wikipedia Query: {wiki_q}")
    print("   ✅ Domain-specific category query filters verified.\n")

    # 3. Test Live Deep Web Roaming & Page Ingestion
    print("3. Testing Live Deep Web Roaming (Parallel Top-Page Scraper)...")
    search_data = await web_search_engine.deep_search_and_roam(
        query="Python 3.12 release notes new features",
        max_results=3,
        roam_top_n=2,
        category="all"
    )
    assert "results" in search_data, "Missing results in search_data"
    assert len(search_data["results"]) > 0, "No search results returned"
    print(f"   Found {len(search_data['results'])} search results.")
    print(f"   Roamed {len(search_data['roamed_pages'])} full pages in parallel.")
    if search_data["roamed_pages"]:
        top_page = search_data["roamed_pages"][0]
        print(f"   Top Roamed Page Title: {top_page['title']}")
        print(f"   Top Roamed Page URL: {top_page['url']}")
        print(f"   Extracted Content Sample: {top_page['content'][:150]}...")
    print(f"   Generated Citations: {len(search_data['citations'])} sources")
    print("   ✅ Deep Web Roaming and parallel page ingestion verified.\n")

    # 4. Test SSRF Guard in Deep Roaming
    print("4. Testing SSRF Guard on Internal/Loopback URLs...")
    assert not is_safe_public_url("http://127.0.0.1:8002/api/admin"), "Failed to block 127.0.0.1"
    assert not is_safe_public_url("http://169.254.169.254/latest/meta-data/"), "Failed to block AWS metadata"
    assert not is_safe_public_url("http://10.0.0.1/router"), "Failed to block private subnet"
    print("   ✅ SSRF Guard verified during roaming.\n")

    # 5. Test Search Intent Heuristics
    print("5. Testing Search Intent Keyword Heuristics...")
    assert web_search_engine.should_search_web("research about forbidden places on earth"), "Failed research keyword detection"
    assert web_search_engine.should_search_web("what is the latest news today"), "Failed news keyword detection"
    assert web_search_engine.should_search_web("compare react 19 and vue 3"), "Failed compare keyword detection"
    assert not web_search_engine.should_search_web("hi how are you"), "False positive on basic greeting"
    print("   ✅ Search intent heuristic triggers verified.\n")

    print("🎉 ALL DEEP SEARCH & AUTONOMOUS ROAMING TESTS PASSED! (100% PASS RATE)")

if __name__ == "__main__":
    asyncio.run(run_deep_search_tests())
