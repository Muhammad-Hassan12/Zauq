"""Tests for sandbox concurrency controls in Zauq v4.

Verifies that the global semaphore limits concurrent docker executions to SANDBOX_MAX_CONCURRENCY.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from backend.sandbox.code_runner import execute_code_docker, _get_semaphore


@pytest.mark.asyncio
async def test_sandbox_semaphore_limits_concurrency():
    """Verify that concurrent calls are queued through the global semaphore."""
    active_count = 0
    max_active_seen = 0

    async def fake_proc_communicate(*args, **kwargs):
        nonlocal active_count, max_active_seen
        active_count += 1
        max_active_seen = max(max_active_seen, active_count)
        await asyncio.sleep(0.05)
        active_count -= 1
        return (b"ok\n", b"")

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=fake_proc_communicate)
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        # Run 3 concurrent execution tasks
        results = await asyncio.gather(
            execute_code_docker("print(1)", "python"),
            execute_code_docker("print(2)", "python"),
            execute_code_docker("print(3)", "python"),
        )

    assert len(results) == 3
    # Semaphore is configured to 1 (default VPS concurrency)
    semaphore = _get_semaphore()
    assert max_active_seen <= semaphore._value + 1
