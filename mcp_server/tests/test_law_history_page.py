"""整部法規沿革必須即時讀取全國法規資料庫 LawHistory.aspx。"""

import httpx
import pytest

import mcp_server.server as server
from mcp_server.tools.regulations import RegulationClient, _parse_law_history_page


_HISTORY_PAGE = """<html><body>
  <a id="hlLawName">勞動基準法</a>
  <div class="well law-reg">
    <div class="law-reg-content law-content law-history">
      <div class="row"><div class="col-data text-pre">
        12. 中華民國一百十五年九月三十日總統令修正公布第 16 條條文
      </div></div>
    </div>
  </div>
</body></html>"""


def test_parse_law_history_page_extracts_official_name_and_entries():
    result = _parse_law_history_page(
        _HISTORY_PAGE,
        "N0030001",
        "https://law.moj.gov.tw/LawClass/LawHistory.aspx?pcode=N0030001",
    )

    assert result == {
        "success": True,
        "pcode": "N0030001",
        "law_name": "勞動基準法",
        "history": "12. 中華民國一百十五年九月三十日總統令修正公布第 16 條條文",
        "source_url": "https://law.moj.gov.tw/LawClass/LawHistory.aspx?pcode=N0030001",
    }


@pytest.mark.asyncio
async def test_get_law_history_page_uses_pcode_and_reports_http_errors():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=_HISTORY_PAGE, request=request)

    client = RegulationClient.__new__(RegulationClient)
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    result = await client.get_law_history_page("n0030001")
    await client.close()

    assert result["success"] is True
    assert requests[0].url.path.endswith("/LawHistory.aspx")
    assert requests[0].url.params["pcode"] == "N0030001"

    failed_client = RegulationClient.__new__(RegulationClient)
    failed_client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, request=request),
        ),
    )
    failed = await failed_client.get_law_history_page("N0030001")
    await failed_client.close()
    assert failed["success"] is False
    assert "error" in failed


@pytest.mark.asyncio
async def test_query_regulation_returns_live_history_metadata(monkeypatch):
    class FakeRegulationClient:
        async def get_outline(self, pcode):
            return {
                "success": True,
                "law": {"name": "舊法規名稱", "pcode": pcode},
                "structure": [],
            }

        async def get_law_history_page(self, pcode):
            return {
                "success": True,
                "history": "修正公布第 16 條",
                "law_name": "勞動基準法",
                "pcode": pcode,
                "source_url": (
                    "https://law.moj.gov.tw/LawClass/LawHistory.aspx"
                    f"?pcode={pcode}"
                ),
            }

    monkeypatch.setattr(server, "reg_client", FakeRegulationClient())
    result = await server.query_regulation(pcode="N0030001", include_history=True)

    assert result["history_available"] is True
    assert result["history"] == "修正公布第 16 條"
    assert result["history_source_url"].endswith("pcode=N0030001")
    assert result["law"]["name"] == "勞動基準法"
