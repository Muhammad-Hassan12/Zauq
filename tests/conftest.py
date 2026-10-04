"""Hermetic defaults must be established before test modules import settings."""
import os
import ipaddress
import socket

import pytest

os.environ['ZAUQ_ENV_FILE'] = '/dev/null'
os.environ['DEVELOPMENT_MODE'] = 'true'
for key in ('GEMINI_API_KEY','ANTHROPIC_API_KEY','QWEN_API_KEY','DEEPSEEK_API_KEY',
            'SERPER_API_KEY','DO_MODEL_ACCESS_KEY','SUPABASE_URL','SUPABASE_KEY',
            'DISCORD_BOT_TOKEN','INTERNAL_API_KEY','KAGGLE_TUNNEL_URL'):
    os.environ[key] = ''


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch):
    from backend.memory.db import db_helper
    monkeypatch.setattr(db_helper, 'supabase', None)
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guard(original, sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            try:
                local = ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                local = address[0] == 'localhost'
            if not local:
                raise AssertionError('External network connections are forbidden in tests; use a mock or loopback fixture.')
        return original(sock,address)
    monkeypatch.setattr(socket.socket,'connect',lambda sock,address:guard(original_connect,sock,address))
    monkeypatch.setattr(socket.socket,'connect_ex',lambda sock,address:guard(original_connect_ex,sock,address))
