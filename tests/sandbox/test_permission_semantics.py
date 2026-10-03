"""Tests for sandbox permission semantics in Zauq v4.

Verifies:
- Explicit allow_code_exec=False ALWAYS blocks execution, even if channel operating_mode is 'dev'
- Explicit allow_code_exec=True allows execution
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from backend.routers.sandbox import run_code, CodeExecRequest
from backend.memory.db import db_helper


@pytest.mark.asyncio
async def test_permission_dev_mode_with_allow_exec_false_is_forbidden():
    """Channel in Dev Mode with allow_code_exec=False must be strictly rejected (403)."""
    # Mock channel profile with dev mode but allow_code_exec=False
    mock_profile = {
        "channel_id": "test-ch",
        "operating_mode": "dev",
        "allow_code_exec": False,
    }

    with patch.object(db_helper, "get_channel_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_profile

        req = CodeExecRequest(
            code="print('should not run')",
            language="python",
            channel_id="test-ch",
        )

        with pytest.raises(HTTPException) as exc_info:
            await run_code(req)

        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_permission_allow_exec_true_proceeds():
    """Channel with allow_code_exec=True successfully executes."""
    mock_profile = {
        "channel_id": "test-ch",
        "operating_mode": "hangout",
        "allow_code_exec": True,
    }

    mock_exec = AsyncMock(return_value={"success": True, "stdout": "hello\n", "exit_code": 0})

    with patch.object(db_helper, "get_channel_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_profile
        with patch("backend.routers.sandbox.execute_code", mock_exec):
            req = CodeExecRequest(
                code="print('hello')",
                language="python",
                channel_id="test-ch",
            )
            res = await run_code(req)

    assert res["success"] is True
    assert res["stdout"] == "hello\n"
