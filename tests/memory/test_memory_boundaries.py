from datetime import datetime
from unittest.mock import MagicMock

import pytest
from backend.memory.db import db_helper


@pytest.mark.asyncio
async def test_memory_timestamps_are_values_not_sql_expressions(monkeypatch):
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{'access_count':2}]
    client.table.return_value.select.return_value.lt.return_value.gt.return_value.execute.return_value.data = []
    monkeypatch.setattr(db_helper,'supabase',client)
    await db_helper.reinforce_memory('m')
    payload = client.table.return_value.update.call_args.args[0]
    assert datetime.fromisoformat(payload['last_accessed_at']).tzinfo is not None
    await db_helper.decay_old_memories()
    cutoff = client.table.return_value.select.return_value.lt.call_args.args[1]
    assert datetime.fromisoformat(cutoff).tzinfo is not None
