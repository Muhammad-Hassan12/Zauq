import re
import socket
import ipaddress
import urllib.parse
import httpx
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("zauq.web_search")

def is_safe_public_url(url: str) -> bool:
    """
    Validates that a URL uses http/https and does not resolve to private,
    loopback, link-local, multicast, or reserved IP ranges (SSRF protection).
    """
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        # Explicitly block known localhost names
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "local", "metadata.google.internal"):
            return False

        # Resolve hostname to all associated IPs and verify each
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False

        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception as e:
        logger.debug(f"URL safety check failed for {url}: {e}")
        return False

class WebSearchEngine:
    """
    Universal Web Search and URL Content Reader for Zauq.
    Provides DuckDuckGo live search, Jina Reader URL scraping, and search query extraction.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    async def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Performs a web search via DuckDuckGo HTML endpoint without requiring an API key.
        Returns a list of dicts: [{"title": ..., "url": ..., "snippet": ...}]
        """
        results = []
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                    headers=self.headers
                )
                if response.status_code != 200:
                    logger.warning(f"DuckDuckGo search returned status {response.status_code}")
                    return results

                html = response.text

                # Parse search result blocks from DuckDuckGo HTML
                result_blocks = re.findall(
                    r'<a class="result__url" href="([^"]+)".*?<a class="result__snippet[^"]*"[^>]*>(.*?)</a>',
                    html,
                    re.DOTALL
                )

                titles = re.findall(r'<a class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)

                for idx, (raw_url, snippet_html) in enumerate(result_blocks[:max_results]):
                    # Clean snippet
                    snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
                    snippet = snippet.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&lt;", "<").replace("&gt;", ">")

                    # Clean title
                    title = f"Result {idx+1}"
                    if idx < len(titles):
                        title = re.sub(r"<[^>]+>", "", titles[idx]).strip()
                        title = title.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'")

                    # Extract actual URL from DuckDuckGo redirect
                    actual_url = raw_url
                    if "uddg=" in raw_url:
                        match = re.search(r"uddg=([^&]+)", raw_url)
                        if match:
                            actual_url = urllib.parse.unquote(match.group(1))

                    if actual_url and snippet:
                        results.append({
                            "title": title,
                            "url": actual_url,
                            "snippet": snippet
                        })

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed for '{query}': {e}")

        return results

    async def fetch_url_content(self, target_url: str, max_chars: int = 8000) -> str:
        """
        Fetches and extracts clean readable markdown text from a webpage using Jina Reader (free API).
        Fallback to direct text extraction if Jina is unavailable.
        Strict SSRF validation is enforced before any outbound HTTP request.
        """
        target_url = target_url.strip()
        if not (target_url.startswith("http://") or target_url.startswith("https://")):
            return "[Invalid URL: Must start with http:// or https://]"

        # SSRF Security Check: Verify target URL does not point to internal/private networks
        if not is_safe_public_url(target_url):
            logger.warning(f"Blocked potential SSRF access attempt to target: {target_url}")
            return "[Access Denied: URL resolves to private or restricted network address]"

        # Method 1: Jina Reader (https://r.jina.ai/<url>)
        jina_url = f"https://r.jina.ai/{target_url}"
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                res = await client.get(jina_url, headers={"User-Agent": "Zauq-Bot/3.0"})
                if res.status_code == 200 and len(res.text.strip()) > 50:
                    text = res.text.strip()
                    if len(text) > max_chars:
                        text = text[:max_chars] + "\n... [Webpage Content Truncated for Length]"
                    return text
        except Exception as jina_err:
            logger.info(f"Jina reader fallback for {target_url}: {jina_err}")

        # Method 2: Direct HTTP scrape fallback with safe redirect resolution
        try:
            current_url = target_url
            for _ in range(3):  # Max 3 redirects
                if not is_safe_public_url(current_url):
                    return "[Access Denied: Redirected to restricted network address]"

                async with httpx.AsyncClient(timeout=6.0, follow_redirects=False) as client:
                    res = await client.get(current_url, headers=self.headers)
                    if res.status_code in (301, 302, 303, 307, 308):
                        location = res.headers.get("Location")
                        if location:
                            current_url = urllib.parse.urljoin(current_url, location)
                            continue
                        break

                    if res.status_code == 200:
                        # Strip scripts and styles
                        html = re.sub(r"<(script|style).*?</\1>", "", res.text, flags=re.DOTALL | re.IGNORECASE)
                        # Strip HTML tags
                        plain_text = re.sub(r"<[^>]+>", " ", html)
                        # Clean whitespace
                        plain_text = re.sub(r"\s+", " ", plain_text).strip()
                        if len(plain_text) > max_chars:
                            plain_text = plain_text[:max_chars] + "\n... [Webpage Content Truncated for Length]"
                        return plain_text if plain_text else "[Webpage contained no readable text]"
                    break
        except Exception as e:
            return f"[Failed to fetch webpage content: {str(e)}]"

        return "[Unable to retrieve content from URL]"

    def apply_category_filter(self, query: str, category: str = "all") -> str:
        """Appends domain-specific filters to search query based on category."""
        category = (category or "all").lower().strip()
        cleaned_q = query.strip()

        if category == "github":
            return f"site:github.com {cleaned_q}"
        elif category == "arxiv":
            return f"site:arxiv.org {cleaned_q}"
        elif category == "docs":
            return f"(site:docs.python.org OR site:developer.mozilla.org OR site:fastapi.tiangolo.com OR site:devdocs.io) {cleaned_q}"
        elif category == "wikipedia":
            return f"site:wikipedia.org {cleaned_q}"
        elif category == "news":
            return f"(site:news.ycombinator.com OR site:reuters.com OR site:techcrunch.com) {cleaned_q}"
        return cleaned_q

    def optimize_search_queries(self, raw_query: str, max_queries: int = 3) -> List[str]:
        """
        Cleans conversational filler and decomposes complex queries into 1-3 targeted search queries.
        """
        if not raw_query:
            return []

        # Remove conversational filler
        filler_patterns = [
            r'^(?:please\s+)?(?:can\s+you\s+)?(?:search\s+(?:for|about|the\s+web\s+for)?|research\s+about|look\s+up|find\s+information\s+on|tell\s+me\s+about|what\s+do\s+you\s+know\s+about)\s+',
            r'(?:,\s*)?(?:research\s+about\s+it\s+and\s+tell\s+me|tell\s+me\s+more|give\s+me\s+details|explain\s+in\s+detail|and\s+give\s+citations)[\.\!\?]*$'
        ]
        cleaned = raw_query.strip()
        for p in filler_patterns:
            cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE).strip()

        queries = [cleaned] if cleaned else [raw_query.strip()]

        # Generate a concise keyword variant for search engines if the query is long
        words = cleaned.split()
        if len(words) > 6:
            stop_words = {"a", "an", "the", "in", "on", "at", "of", "for", "to", "and", "or", "is", "are", "where", "it", "strictly", "not", "allowed"}
            keywords = [w for w in words if w.lower() not in stop_words and len(w) > 2]
            if keywords and len(keywords) >= 3:
                keyword_query = " ".join(keywords[:7])
                if keyword_query not in queries:
                    queries.append(keyword_query)

        return queries[:max_queries]

    async def deep_search_and_roam(
        self,
        query: str,
        max_results: int = 5,
        roam_top_n: int = 2,
        category: str = "all"
    ) -> Dict[str, Any]:
        """
        Autonomous Deep Web Roaming Engine:
        1. Formulates category-filtered search queries.
        2. Retrieves top search results from DuckDuckGo.
        3. Concurrently visits & reads the top N result webpages in parallel using Jina / SSRF-safe scraper.
        4. Synthesizes rich distilled page context with clickable markdown citations.
        """
        import asyncio

        optimized_queries = self.optimize_search_queries(query)
        primary_query = optimized_queries[0] if optimized_queries else query
        filtered_query = self.apply_category_filter(primary_query, category)

        search_results = await self.search_duckduckgo(filtered_query, max_results=max_results)
        
        # If filtered query returned no results and category wasn't 'all', fallback to unfiltered query
        if not search_results and category != "all":
            search_results = await self.search_duckduckgo(primary_query, max_results=max_results)

        roamed_pages = []
        citations = []

        if search_results:
            # Build citations list
            for idx, r in enumerate(search_results[:5]):
                title = r.get("title", f"Source {idx+1}")
                url = r.get("url", "")
                if url:
                    clean_title = (title[:60] + "...") if len(title) > 60 else title
                    citations.append(f"• [{clean_title}]({url})")

            # Deep Roaming: Fetch full content of top N URLs in parallel
            if roam_top_n > 0:
                target_urls = [r["url"] for r in search_results[:roam_top_n] if r.get("url") and is_safe_public_url(r.get("url"))]
                if target_urls:
                    fetch_tasks = [self.fetch_url_content(u, max_chars=3500) for u in target_urls]
                    page_contents = await asyncio.gather(*fetch_tasks, return_exceptions=True)

                    for idx, content in enumerate(page_contents):
                        if isinstance(content, str) and len(content.strip()) > 100 and not content.startswith("[Failed") and not content.startswith("[Access"):
                            roamed_pages.append({
                                "title": search_results[idx].get("title", f"Source {idx+1}"),
                                "url": target_urls[idx],
                                "content": content.strip()
                            })

        # Assemble rich context text block for LLM prompt
        context_blocks = []
        if roamed_pages:
            context_blocks.append("### 📑 Full-Page Web Research Context:")
            for p in roamed_pages:
                context_blocks.append(f"--- Source: {p['title']} ({p['url']}) ---\n{p['content']}\n")
        elif search_results:
            context_blocks.append("### 🌐 Live Web Search Snippets:")
            for r in search_results[:4]:
                context_blocks.append(f"• **{r['title']}** ({r['url']}):\n  {r['snippet']}")

        context_text = "\n".join(context_blocks)

        return {
            "query": query,
            "optimized_query": primary_query,
            "category": category,
            "results": search_results,
            "roamed_pages": roamed_pages,
            "context_text": context_text,
            "citations": citations
        }

    def extract_urls(self, text: str) -> List[str]:
        """Extracts all http/https URLs from a text string."""
        if not text:
            return []
        pattern = r'https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s()<>]*)*'
        return re.findall(pattern, text)

    def should_search_web(self, query: str) -> bool:
        """
        Intelligent heuristic check if a user query requires live web search.
        Matches explicit search requests ('search for', 'look up', 'find out', 'browse')
        as well as real-time, factual, or research intents.
        """
        if not query or len(query.strip()) < 3:
            return False

        q_lower = query.lower()

        # 1. Explicit search commands in chat prompt
        explicit_search_triggers = [
            "search", "look up", "find info", "find information", "find out",
            "browse the web", "check online", "google it", "google for",
            "search the web", "search online", "search for", "look on the web",
            "look online", "search up", "research about", "research on"
        ]
        if any(trigger in q_lower for trigger in explicit_search_triggers):
            return True

        # 2. Real-time & temporal news/events keywords
        temporal_keywords = [
            "latest", "news", "today", "yesterday", "tonight", "this week",
            "this month", "current", "release", "version", "price", "weather",
            "score", "match", "stock", "update", "released", "what happened",
            "recent", "who won", "upcoming", "schedule", "newest", "changelog"
        ]
        if any(kw in q_lower for kw in temporal_keywords):
            return True

        # 3. Deep Research & Factual Inquiry Triggers
        research_keywords = [
            "research", "investigate", "compare", "benchmark", "analysis",
            "sources", "facts", "forbidden", "places on earth", "who created",
            "when did", "documentation", "github repo", "arxiv paper",
            "is it true that", "who is the current", "what is the current",
            "who is the new", "status of"
        ]
        if any(kw in q_lower for kw in research_keywords):
            return True

        return False

web_search_engine = WebSearchEngine()
