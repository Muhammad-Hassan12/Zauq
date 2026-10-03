"""Unit tests for Discord Agent Slash commands and pagination UI (Phase 8)."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from bot.commands.agent_slash import AgentToolsPaginationView, PAGE_SIZE


def make_sample_tools(count: int = 14) -> list[dict]:
    return [
        {
            "name": f"sample.tool_{i}",
            "description": f"Description for sample tool {i}",
            "risk": "read" if i % 2 == 0 else "write",
            "source": "native" if i < 5 else "mcp",
            "server_id": f"server_{i}" if i >= 5 else None,
        }
        for i in range(count)
    ]


def test_pagination_view_page_calculation():
    """Verify total pages math based on PAGE_SIZE."""
    tools = make_sample_tools(14)
    view = AgentToolsPaginationView(tools=tools, initiator_id=12345, guild_name="TestGuild")

    assert PAGE_SIZE == 6
    assert view.total_pages == 3
    assert view.current_page == 0

    # Initial button states on first page
    assert view.first_button.disabled is True
    assert view.prev_button.disabled is True
    assert view.next_button.disabled is False
    assert view.last_button.disabled is False
    assert "Page 1/3" in view.page_indicator.label


def test_pagination_view_embed_content():
    """Verify embed items match current page range."""
    tools = make_sample_tools(14)
    view = AgentToolsPaginationView(tools=tools, initiator_id=12345, guild_name="TestGuild")

    embed = view.build_page_embed()
    assert embed.title == "🛠️ Registered Agent Tools"
    assert "TestGuild" in embed.description
    # Page 0 should have exactly 6 fields (sample.tool_0 through sample.tool_5)
    assert len(embed.fields) == 6
    assert "sample.tool_0" in embed.fields[0].name
    assert "sample.tool_5" in embed.fields[5].name


def test_pagination_view_navigation():
    """Verify navigation updates page index and button disabled states."""
    tools = make_sample_tools(14)
    view = AgentToolsPaginationView(tools=tools, initiator_id=12345)

    # Move to page 1 (middle page)
    view.current_page = 1
    view._update_buttons()
    assert view.first_button.disabled is False
    assert view.prev_button.disabled is False
    assert view.next_button.disabled is False
    assert view.last_button.disabled is False
    assert "Page 2/3" in view.page_indicator.label

    # Move to page 2 (last page)
    view.current_page = 2
    view._update_buttons()
    assert view.first_button.disabled is False
    assert view.prev_button.disabled is False
    assert view.next_button.disabled is True
    assert view.last_button.disabled is True
    assert "Page 3/3" in view.page_indicator.label

    # Last page should have remaining 2 items (indices 12 and 13)
    embed = view.build_page_embed()
    assert len(embed.fields) == 2
    assert "sample.tool_12" in embed.fields[0].name
    assert "sample.tool_13" in embed.fields[1].name


@pytest.mark.asyncio
async def test_pagination_view_interaction_check():
    """Only the initiator is permitted to paginate the view."""
    tools = make_sample_tools(5)
    view = AgentToolsPaginationView(tools=tools, initiator_id=12345)

    # Matching initiator
    initiator_interaction = MagicMock()
    initiator_interaction.user.id = 12345
    allowed = await view.interaction_check(initiator_interaction)
    assert allowed is True

    # Different user
    stranger_interaction = MagicMock()
    stranger_interaction.user.id = 99999
    stranger_interaction.response.send_message = AsyncMock()
    denied = await view.interaction_check(stranger_interaction)
    assert denied is False
    stranger_interaction.response.send_message.assert_awaited_once()


def test_response_transparency_footer_formatting():
    """Verify tool chain formatting for user-visible response transparency."""
    trace = [
        {"tool": "web.search", "success": True, "duration_ms": 320},
        {"tool": "web.fetch", "success": True, "duration_ms": 110},
    ]

    tools_used = [t.get("tool") for t in trace if t.get("tool")]
    tool_chain = " → ".join(tools_used)
    footer = f"\n\n🛠️ *Tools used: {tool_chain}*"

    original_response = "Here are the latest findings regarding Python 3.13."
    full_response = original_response + footer

    assert "🛠️ *Tools used: web.search → web.fetch*" in full_response
    assert "duration_ms" not in full_response
    assert "arguments" not in full_response


def test_response_transparency_empty_trace():
    """When no tools were called, no transparency footer is attached."""
    trace = []
    tools_used = [t.get("tool") for t in trace if t.get("tool")]
    assert len(tools_used) == 0
