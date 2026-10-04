from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands import stats_slash


@pytest.mark.asyncio
async def test_statistics_distinguish_unknown_cost_and_report_tool_counts(monkeypatch):
    response = MagicMock(status_code=200)
    response.json.return_value = {
        'total_requests': 2, 'total_mcp_calls': 1, 'total_search_calls': 3,
        'unknown_usage_requests': 1, 'unknown_cost_requests': 2,
        'total_estimated_cost_usd': None, 'source': 'in_memory',
        'window': 'last 1000 requests in this process',
    }
    client = AsyncMock()
    client.get.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(stats_slash, 'api_client', MagicMock(return_value=context))
    interaction = MagicMock(guild_id=123)
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    cog = stats_slash.StatsSlash(MagicMock())
    await cog.server_stats.callback(cog, interaction)
    embed = interaction.followup.send.call_args.kwargs['embed']
    fields = {field.name: field.value for field in embed.fields}
    assert 'MCP: 1' in fields['Tools'] and 'Search: 3' in fields['Tools']
    assert fields['Estimated Model Cost'].startswith('Unknown')
    assert 'unknown usage: 1' in fields['Reported Tokens']
    assert 'last 1000' in embed.footer.text
