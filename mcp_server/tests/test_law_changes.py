"""Tests for the Ministry of Justice law-change search client."""

from urllib.parse import parse_qs

import httpx
import pytest

from mcp_server.tools.law_changes import LAW_SEARCH_URL, LawChangeSearchClient


_FORM = """
<form id="form1">
  <input type="hidden" name="__VIEWSTATE" value="state">
  <input type="hidden" name="__EVENTVALIDATION" value="validation">
</form>
"""
_PAGE_ONE = """
<strong>中央法規 &gt; 法規名稱</strong>
<table class="tab-result">
  <tr><th>序號</th><th>法規名稱</th></tr>
  <tr><td>1.</td><td><a href="../Hot/AddHotLaw.ashx?pcode=B0000001&amp;cur=Ln">民法</a> (民國 115 年 09 月 23 日)</td></tr>
</table>
<a id="hlPage" href="/Law/LawSearchResult.aspx?page=2">下一頁</a>
"""
_PAGE_TWO = """
<strong>中央法規 &gt; 法規名稱</strong>
<table class="tab-result">
  <tr><th>序號</th><th>法規名稱</th></tr>
  <tr><td>2.</td><td><a href="../Hot/AddHotLaw.ashx?pcode=N0030001&amp;cur=Ln">勞動基準法</a> (民國 115 年 09 月 24 日)</td></tr>
</table>
"""


def _mocked_client(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    return http, LawChangeSearchClient(http)


@pytest.mark.asyncio
async def test_search_defaults_all_filters_and_follows_result_pages():
    post_data = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("LawSearchAll.aspx"):
            return httpx.Response(200, text=_FORM, request=request)
        if request.method == "POST":
            post_data.update(parse_qs(request.content.decode()))
            return httpx.Response(200, text=_PAGE_ONE, request=request)
        return httpx.Response(200, text=_PAGE_TWO, request=request)

    http, client = _mocked_client(handler)
    try:
        result = await client.search(date_from="2026-09-23", date_to="1150924")
    finally:
        await http.aclose()

    for control_id, value in {
        "chk5": "L",
        "chk6": "C",
        "chk7": "A",
        "chk8": "B5",
        "chk1": "B1",
        "chk2": "B2",
        "chk3": "B3",
        "chk4": "B4",
        "chkItem1": "A1",
        "chkItem2": "A2",
        "chkState1": "FN",
        "chkState2": "FY",
    }.items():
        assert post_data[f"ctl00$cp_content${control_id}"] == [value]
    assert post_data["ctl00$cp_content$tbxDateS"] == ["1150923"]
    assert post_data["ctl00$cp_content$tbxDateE"] == ["1150924"]
    assert result["success"] is True
    assert result["total_count"] == 2
    assert result["has_more"] is False
    assert result["results"][0]["category"] == "中央法規"
    assert result["results"][0]["change_date"] == "2026-09-23"
    assert result["results"][0]["source_url"] == (
        "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=B0000001"
    )


@pytest.mark.asyncio
async def test_search_sends_only_selected_filters():
    post_data = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=_FORM, request=request)
        post_data.update(parse_qs(request.content.decode()))
        return httpx.Response(200, text=_PAGE_TWO, request=request)

    http, client = _mocked_client(handler)
    try:
        result = await client.search(
            keyword="民法",
            categories=["central_laws"],
            search_items=["law_name"],
            valid_statuses=["repealed"],
        )
    finally:
        await http.aclose()

    assert result["success"] is True
    assert post_data["ctl00$cp_content$chk5"] == ["L"]
    assert post_data["ctl00$cp_content$chkItem1"] == ["A1"]
    assert post_data["ctl00$cp_content$chkState2"] == ["FY"]
    assert "ctl00$cp_content$chk6" not in post_data
    assert "ctl00$cp_content$chkItem2" not in post_data
    assert "ctl00$cp_content$chkState1" not in post_data
    assert post_data["ctl00$cp_content$WordSelect_tbKey1"] == ["民法"]


@pytest.mark.asyncio
async def test_search_rejects_invalid_or_incomplete_period_without_request():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=_FORM, request=request)

    http, client = _mocked_client(handler)
    try:
        result = await client.search(date_from="1150924")
        assert result["success"] is False
        assert "同時提供" in result["error"]

        result = await client.search(date_from="1150931", date_to="1151001")
        assert result["success"] is False
        assert "日期須使用" in result["error"]
    finally:
        await http.aclose()

    assert requests == []


@pytest.mark.asyncio
async def test_search_requires_a_keyword_period_or_document_number():
    http, client = _mocked_client(
        lambda request: httpx.Response(200, text=_FORM, request=request)
    )
    try:
        result = await client.search()
    finally:
        await http.aclose()

    assert result["success"] is False
    assert "須提供" in result["error"]