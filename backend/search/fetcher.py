from __future__ import annotations
import socket
import ipaddress
import urllib.parse
import asyncio
import logging
import httpx
import re
from backend.search.models import FetchResult
from backend.config import settings

logger = logging.getLogger("zauq.search.fetcher")

# Semaphore shared across all concurrent fetch calls
_FETCH_SEM: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _FETCH_SEM
    if _FETCH_SEM is None:
        concurrency = getattr(settings, "WEB_FETCH_CONCURRENCY", 3)
        _FETCH_SEM = asyncio.Semaphore(concurrency)
    return _FETCH_SEM


from backend.security.ssrf import is_safe_public_url
from backend.security.ssrf import is_safe_ip_address


async def _bounded_get(url: str, timeout: float) -> tuple[int, dict, str]:
    """Resolve once, connect to that public IP, and cap bytes before decoding.

    Original Host/SNI are retained for virtual hosting and certificate checks.
    Proxy environment variables cannot bypass this transport boundary.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid public URL')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, port, 0, socket.SOCK_STREAM)
    ips = [a[4][0] for a in addresses]
    if not ips or any(not is_safe_ip_address(ipaddress.ip_address(ip)) for ip in ips):
        raise ValueError('Restricted destination')
    target = httpx.URL(url).copy_with(host=ips[0])
    headers = {'Host': parsed.netloc, 'User-Agent': _USER_AGENT, 'Accept-Encoding': 'identity'}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False, verify=True) as client:
        async with client.stream('GET', target, headers=headers, extensions={'sni_hostname': parsed.hostname}) as response:
            if response.status_code != 200:
                return response.status_code, dict(response.headers), ''
            if response.headers.get('content-encoding', 'identity').lower() not in ('identity', ''):
                raise ValueError('Compressed downloads are not accepted')
            limit = min(max(settings.WEB_FETCH_MAX_BYTES, 1), 2000000)
            length = response.headers.get('content-length')
            if length and int(length) > limit:
                raise ValueError('Download exceeds byte limit')
            body = bytearray()
            async for chunk in response.aiter_raw(chunk_size=8192):
                if len(body) + len(chunk) > limit:
                    raise ValueError('Download exceeds byte limit')
                body.extend(chunk)
            return response.status_code, dict(response.headers), body.decode('utf-8', errors='replace')


# Fetch implementation

_USER_AGENT = "Mozilla/5.0 (compatible; Zauq-Bot/4.0)"
_JINA_BASE = "https://r.jina.ai/"


async def _fetch_via_jina(url: str, max_chars: int) -> str | None:
    """Try to fetch readable content via Jina Reader. Returns None on failure."""
    jina_url = f"{_JINA_BASE}{url}"
    try:
        status, _, body = await _bounded_get(jina_url, 3.5)
        if status == 200 and len(body.strip()) > 50:
            return body.strip()[:max_chars]
    except Exception as exc:
        logger.debug(f"Jina failed for '{url}': {exc}")
    return None


async def _fetch_direct(url: str, max_chars: int) -> str | None:
    """
    SSRF-safe direct HTTP fetch with manual redirect tracking.
    Returns clean text or None on failure.
    """
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    current_url = url
    try:
        for _ in range(3):  # max 3 redirects, each re-validated
            if not is_safe_public_url(current_url):
                logger.warning(f"Direct fetch blocked SSRF redirect to '{current_url}'")
                return None
            status, response_headers, body = await _bounded_get(current_url, 6.0)
            if status in (301, 302, 303, 307, 308):
                location = response_headers.get('location')
                if location:
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue
                break
            if status == 200:
                html = re.sub(r"<(script|style).*?</\1>", "", body, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()
                return text[:max_chars] or None
            break
    except Exception as exc:
        logger.debug(f"Direct fetch failed for '{url}': {exc}")
    return None


async def fetch_url(
    url: str,
    max_chars: int = 8000,
) -> FetchResult:
    """
    Fetch readable text from a public URL.

    Pipeline:
      1. SSRF check
      2. Jina Reader
      3. Safe direct HTTP fallback

    Always returns a FetchResult — never raises.
    Uses a semaphore to cap parallel fetch concurrency.
    """
    url = url.strip()
    max_chars = max(100, min(max_chars, 12000))

    if not (url.startswith("http://") or url.startswith("https://")):
        return FetchResult(url=url, success=False, error="Invalid scheme (must be http/https)", method="blocked")

    if not is_safe_public_url(url):
        logger.warning(f"Fetcher blocked SSRF attempt: '{url}'")
        return FetchResult(url=url, success=False, error="URL resolves to private/restricted address", method="blocked")

    sem = _get_semaphore()
    async with sem:
        # Try Jina first
        jina_text = await _fetch_via_jina(url, max_chars)
        if jina_text:
            return FetchResult(url=url, success=True, content=jina_text, method="jina")

        # Fallback: direct HTTP
        direct_text = await _fetch_direct(url, max_chars)
        if direct_text:
            return FetchResult(url=url, success=True, content=direct_text, method="direct")

    return FetchResult(url=url, success=False, error="All fetch methods failed", method="direct")


async def fetch_urls_parallel(
    urls: list[str],
    max_chars_per_page: int = 8000,
    max_pages: int | None = None,
) -> list[FetchResult]:
    """
    Fetch multiple URLs concurrently (bounded by the shared semaphore).
    """
    limit = max_pages or settings.WEB_FETCH_MAX_PAGES
    targets = urls[:limit]
    tasks = [fetch_url(u, max_chars=max_chars_per_page) for u in targets]
    return list(await asyncio.gather(*tasks, return_exceptions=False))
