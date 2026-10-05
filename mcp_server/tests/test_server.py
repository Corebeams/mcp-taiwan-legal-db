"""server.py tool-level validation tests."""

import importlib
import sys

import pytest

import mcp_server.server as server


@pytest.mark.asyncio
async def test_search_judgments_rejects_non_positive_max_results():
    result = await server.search_judgments(keyword="契約", max_results=0)
    assert result["success"] is False
    assert "max_results" in result["error"]


@pytest.mark.asyncio
async def test_search_regulations_rejects_negative_offset():
    result = await server.search_regulations("法", offset=-1)
    assert result["success"] is False
    assert "offset" in result["error"]


@pytest.mark.asyncio
async def test_search_law_changes_exposes_filter_options_to_mcp_clients():
    tools = await server.mcp.list_tools()
    tool = next(item for item in tools if item.name == "search_law_changes")
    properties = tool.model_dump(mode="json", by_alias=True)["inputSchema"]["properties"]

    expected_options = {
        "categories": {
            "central_laws",
            "treaties",
            "cross_strait_agreements",
            "constitutional_court_new",
            "grand_justices_old",
            "supreme_court_civil_precedents",
            "supreme_court_criminal_precedents",
            "supreme_administrative_court_precedents",
        },
        "search_items": {"law_name", "article_content"},
        "valid_statuses": {"current", "repealed"},
    }
    for name, expected in expected_options.items():
        array_schema = next(
            branch for branch in properties[name]["anyOf"] if branch.get("type") == "array"
        )
        assert set(array_schema["items"]["enum"]) == expected


def test_updater_import_bootstraps_ssl_setup():
    """驗證 updater 獨立 import 時會觸發 inject_os_trust_store（非只檢查 module 存在）"""
    import mcp_server.ssl_setup as ssl_setup

    ssl_setup._INJECTED = False
    sys.modules.pop("mcp_server.updater", None)

    importlib.import_module("mcp_server.updater")

    assert ssl_setup._INJECTED is True
