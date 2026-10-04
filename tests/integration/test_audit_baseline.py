from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock
import pytest
from backend.routers import admin, model
from backend.config import settings
from backend.version import ZAUQ_VERSION


@pytest.mark.asyncio
async def test_forget_deletes_database_memories(monkeypatch):
    db = MagicMock()
    db.table.return_value.delete.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[{}])
    monkeypatch.setattr(admin.db_helper, 'supabase', db)
    result = await admin.purge_user_data('123')
    assert result['deleted_memories_count'] == 1
    db.table.assert_called_with('user_memories')
    db.table.return_value.delete.return_value.eq.assert_called_with('user_id', '123')


@pytest.mark.asyncio
async def test_live_info_uses_current_settings(monkeypatch):
    monkeypatch.setattr(model, 'get_model_status', AsyncMock(return_value={}))
    monkeypatch.setattr(model.db_helper, 'get_channel_profile', AsyncMock(return_value=None))
    info = await model.get_full_system_info('123')
    assert info['engine']['version'] == ZAUQ_VERSION
    assert info['limits']['sandbox_timeout_s'] == settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS
    assert 'Serper' in info['capabilities']['web_search']
