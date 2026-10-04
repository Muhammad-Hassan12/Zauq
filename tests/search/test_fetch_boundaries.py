import socket
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
import pytest
from backend.search import fetcher
from backend.config import settings
from backend.search.providers.serper import SerperProvider
from backend.search.service import extract_urls


@pytest.mark.asyncio
async def test_transport_pins_public_ip_and_limits_download(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a: [(2,1,6,'',('93.184.216.34',443))])
    monkeypatch.setattr(settings, 'WEB_FETCH_MAX_BYTES', 10)
    seen = {}
    class Response:
        status_code = 200
        headers = {}
        async def aiter_raw(self, **kwargs):
            yield b'12345678'
            yield b'12345678'
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            seen.update(url=url, **kwargs)
            yield Response()
    monkeypatch.setattr(fetcher.httpx, 'AsyncClient', lambda **kw: Client())
    with pytest.raises(ValueError, match='byte limit'):
        await fetcher._bounded_get('https://example.com/page', 1)
    assert seen['url'].host == '93.184.216.34'
    assert seen['headers']['Host'] == 'example.com'
    assert seen['extensions']['sni_hostname'] == 'example.com'


@pytest.mark.asyncio
async def test_private_second_resolution_never_connects(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a: [(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError, match='Restricted'):
        await fetcher._bounded_get('https://example.com',1)


@pytest.mark.asyncio
async def test_search_unavailability_is_explicit():
    result = await SerperProvider(api_key='').search('test')
    assert result.error and not result.results


def test_reply_urls_exclude_markdown_delimiters():
    assert extract_urls('[source](https://example.com/page) "https://a.com/x"') == ['https://example.com/page','https://a.com/x']


def test_startup_registers_web_tools():
    import backend.main
    from backend.tools.registry import tool_registry
    assert tool_registry.get('web.search')
    assert tool_registry.get('web.fetch')
