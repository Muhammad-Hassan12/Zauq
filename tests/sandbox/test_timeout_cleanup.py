"""Tests for sandbox timeout handling and container cleanup in Zauq v4.

Verifies:
- Timed out code triggers process kill
- Explicit 'docker rm -f <container_name>' cleanup is invoked
- Result contains timed_out=True and exit_code=-1
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from backend.sandbox.code_runner import execute_code_docker


@pytest.mark.asyncio
async def test_sandbox_timeout_triggers_cleanup():
    """Verify that a timeout triggers container kill and explicit docker rm -f cleanup."""
    mock_proc = AsyncMock()
    # communicate() raises TimeoutError
    mock_proc.stdout.read = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.stderr.read = AsyncMock(return_value=b'')
    mock_proc.returncode = 0
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()

    cleanup_mock = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("backend.sandbox.code_runner._cleanup_container", cleanup_mock):
            res = await execute_code_docker("import time; time.sleep(100)", "python", timeout=0.1)

    assert res["success"] is False
    assert res["timed_out"] is True
    assert res["exit_code"] == -1
    assert "timed out" in res["stderr"].lower()
    cleanup_mock.assert_awaited_once_with(res["execution_id"])
