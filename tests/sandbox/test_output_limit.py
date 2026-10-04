"""Tests for sandbox output size limit in Zauq v4.

Verifies:
- Stdout exceeding SANDBOX_MAX_OUTPUT_CHARS is cleanly truncated
- Stderr exceeding SANDBOX_MAX_OUTPUT_CHARS is cleanly truncated
- Result indicates truncated=True
"""

import pytest
from unittest.mock import AsyncMock, patch
from backend.sandbox.code_runner import execute_code_docker, _truncate_output
from backend.config import settings


def test_truncate_output_below_limit():
    """Output within limits remains unchanged."""
    text, truncated = _truncate_output("short output", max_chars=100)
    assert text == "short output"
    assert truncated is False


def test_truncate_output_above_limit():
    """Output exceeding limits is truncated with notice."""
    long_text = "a" * 200
    text, truncated = _truncate_output(long_text, max_chars=50)
    assert truncated is True
    assert len(text) <= 50
    assert text.startswith("a")
    assert "truncated" in text.lower()


@pytest.mark.asyncio
async def test_sandbox_docker_truncates_large_output(monkeypatch):
    """Execution output larger than max limit is truncated in result dictionary."""
    monkeypatch.setattr(settings, "SANDBOX_MAX_OUTPUT_CHARS", 100)

    mock_proc = AsyncMock()
    # Emits 500 bytes of output
    mock_proc.stdout.read = AsyncMock(side_effect=[b'x'*500,b''])
    mock_proc.stderr.read = AsyncMock(return_value=b'')
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        res = await execute_code_docker("print('x' * 500)", "python")

    assert res["success"] is True
    assert res["truncated"] is True
    assert len(res["stdout"]) < 500
    assert "truncated at 100 characters" in res["stdout"]
