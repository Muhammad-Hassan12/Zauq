import base64
import logging
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.logging_config import RedactingFormatter
from backend.parsers.file_parser import extract_generated_files
from backend.models.tool_schemas import to_gemini_tools
from backend.tools.base import ToolSpec


def test_download_bytes_and_preview_share_redaction(monkeypatch):
    secret = 'test-configured-secret-0123456789'
    monkeypatch.setattr(settings,'INTERNAL_API_KEY',secret)
    text, files = extract_generated_files(f'<zauq_file filename="a.txt">{secret}</zauq_file>')
    assert secret not in text
    assert secret not in base64.b64decode(files[0]['bytes_b64']).decode()
    assert base64.b64decode(files[0]['bytes_b64']).decode() == files[0]['content']


def test_logging_redacts_message_and_traceback(monkeypatch):
    secret = 'test-configured-secret-0123456789'
    monkeypatch.setattr(settings,'INTERNAL_API_KEY',secret)
    import sys
    try:
        raise ValueError(secret)
    except ValueError:
        record = logging.LogRecord('test',40,'file',1,'error %s',(secret,),sys.exc_info())
    formatted = RedactingFormatter().format(record)
    assert secret not in formatted
    assert '[REDACTED_SECRET]' in formatted


def test_runner_blank_credentials_require_explicit_dev(monkeypatch):
    from backend.sandbox.runner_service import app
    monkeypatch.setattr(settings,'INTERNAL_API_KEY','')
    monkeypatch.setattr(settings,'DEVELOPMENT_MODE',False)
    assert TestClient(app).get('/status').status_code == 503


def test_backend_blank_credentials_require_explicit_dev(monkeypatch):
    from backend.main import app
    monkeypatch.setattr(settings, 'INTERNAL_API_KEY', '')
    monkeypatch.setattr(settings, 'DEVELOPMENT_MODE', False)
    client = TestClient(app)
    assert client.get('/api/model/providers').status_code == 503
    assert client.get('/health').status_code == 200


def test_gemini_complex_schema_preserves_unions_and_refs():
    schema = {'type':'object','$defs':{'value':{'anyOf':[{'type':'string'},{'type':'null'}]}},'properties':{'value':{'$ref':'#/$defs/value'}},'additionalProperties':False}
    declaration = to_gemini_tools([ToolSpec('mcp.docs.lookup','lookup',schema)])[0]['functionDeclarations'][0]
    assert declaration['parametersJsonSchema'] == schema
    assert 'parameters' not in declaration
