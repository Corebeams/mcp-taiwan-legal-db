"""Search amendment notices through the Ministry of Justice integrated search."""

import logging
import re
from datetime import date, datetime
from typing import Literal
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from mcp_server.tools._errors import error_response

LawChangeCategory = Literal[
    "central_laws",
    "treaties",
    "cross_strait_agreements",
    "constitutional_court_new",
    "grand_justices_old",
    "supreme_court_civil_precedents",
    "supreme_court_criminal_precedents",
    "supreme_administrative_court_precedents",
]
LawChangeSearchItem = Literal["law_name", "article_content"]
LawChangeStatus = Literal["current", "repealed"]

LAW_SEARCH_URL = "https://law.moj.gov.tw/Law/LawSearchAll.aspx"
LAW_BASE_URL = "https://law.moj.gov.tw"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_MAX_RESULTS = 200

_CATEGORIES: dict[str, tuple[str, str]] = {
    "central_laws": ("chk5", "L"),
    "treaties": ("chk6", "C"),
    "cross_strait_agreements": ("chk7", "A"),
    "constitutional_court_new": ("chk8", "B5"),
    "grand_justices_old": ("chk1", "B1"),
    "supreme_court_civil_precedents": ("chk2", "B2"),
    "supreme_court_criminal_precedents": ("chk3", "B3"),
    "supreme_administrative_court_precedents": ("chk4", "B4"),
}
_SEARCH_ITEMS: dict[str, tuple[str, str]] = {
    "law_name": ("chkItem1", "A1"),
    "article_content": ("chkItem2", "A2"),
}
_STATUSES: dict[str, tuple[str, str]] = {
    "current": ("chkState1", "FN"),
    "repealed": ("chkState2", "FY"),
}
_ROC_DATE_RE = re.compile(r"民國\s*(\d{1,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
logger = logging.getLogger(__name__)


def _selected_options(name: str, selected: list[str] | None, options: dict) -> list[str]:
    if selected is None:
        return list(options)
    values = list(dict.fromkeys(selected))
    if not values:
        raise ValueError(f"{name} 至少須選擇一項")
    unknown = sorted(set(values) - options.keys())
    if unknown:
        raise ValueError(f"{name} 包含不支援的選項：{', '.join(unknown)}")
    return values


def _parse_input_date(value: str) -> tuple[date, str]:
    raw = value.strip()
    try:
        if re.fullmatch(r"\d{7}", raw):
            roc_year = int(raw[:3])
            parsed = date(roc_year + 1911, int(raw[3:5]), int(raw[5:7]))
        else:
            parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("日期須使用 YYYY-MM-DD 或民國七碼格式（例如 1150924）") from exc

    roc_year = parsed.year - 1911
    if not 1 <= roc_year <= 999:
        raise ValueError("日期須介於民國 1 年至 999 年")
    return parsed, f"{roc_year:03d}{parsed.month:02d}{parsed.day:02d}"


def _change_date(text: str) -> tuple[str | None, str | None]:
    match = _ROC_DATE_RE.search(text)
    if not match:
        return None, None
    roc_year, month, day = (int(value) for value in match.groups())
    changed = date(roc_year + 1911, month, day)
    return changed.isoformat(), f"民國 {roc_year:03d} 年 {month:02d} 月 {day:02d} 日"


def _result_link(row, page_url: str):
    links = row.select("a[href]")
    for link in links:
        label = link.get_text(" ", strip=True)
        if label and label.upper() != "EN" and "本法規有附件" not in label:
            return link
    return links[0] if links else None


def _parse_result_page(html: str, page_url: str) -> tuple[list[dict], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.tab-result")
    if not tables:
        raise ValueError("法務部查詢結果頁格式不符，請稍後重試或檢查官方網站是否改版")

    results: list[dict] = []
    for table in tables:
        heading = table.find_previous(["h2", "h3", "h4", "strong", "b"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        category = heading_text.split(">")[0].strip() if heading_text else ""

        for row in table.select("tr"):
            if row.find("th"):
                continue
            cells = row.find_all("td", recursive=False)
            row_text = row.get_text(" ", strip=True)
            if not cells or not row_text:
                continue

            link = _result_link(row, page_url)
            title = link.get_text(" ", strip=True) if link else ""
            if not title:
                continue

            href = link.get("href", "")
            absolute_url = urljoin(page_url, href)
            query = parse_qs(urlparse(absolute_url).query)
            pcode = (query.get("pcode") or query.get("PCODE") or [None])[0]
            if pcode:
                absolute_url = f"{LAW_BASE_URL}/LawClass/LawAll.aspx?PCode={pcode}"

            changed, changed_roc = _change_date(row_text)
            item = {
                "category": category,
                "title": title,
                "change_date": changed,
                "change_date_roc": changed_roc,
                "source_url": absolute_url,
                "summary": row_text,
            }
            if pcode:
                item["pcode"] = pcode
            results.append(item)

    next_page = soup.select_one("a#hlPage[href]")
    next_url = urljoin(page_url, next_page["href"]) if next_page else None
    return results, next_url


class LawChangeSearchClient:
    """Query amendment notices and related records from LawSearchAll.aspx."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(
        self,
        *,
        keyword: str = "",
        date_from: str = "",
        date_to: str = "",
        document_number: str = "",
        categories: list[str] | None = None,
        search_items: list[str] | None = None,
        valid_statuses: list[str] | None = None,
        max_results: int = 100,
    ) -> dict:
        query = {
            "keyword": keyword.strip(),
            "date_from": date_from.strip(),
            "date_to": date_to.strip(),
            "document_number": document_number.strip(),
            "categories": categories,
            "search_items": search_items,
            "valid_statuses": valid_statuses,
            "max_results": max_results,
        }
        try:
            if max_results <= 0:
                raise ValueError("max_results 必須大於 0")
            if max_results > _MAX_RESULTS:
                raise ValueError(f"max_results 不可大於 {_MAX_RESULTS}")

            selected_categories = _selected_options("categories", categories, _CATEGORIES)
            selected_items = _selected_options("search_items", search_items, _SEARCH_ITEMS)
            selected_statuses = _selected_options("valid_statuses", valid_statuses, _STATUSES)

            if bool(query["date_from"]) != bool(query["date_to"]):
                raise ValueError("期間查詢須同時提供 date_from 與 date_to")
            start_date = _parse_input_date(query["date_from"]) if query["date_from"] else None
            end_date = _parse_input_date(query["date_to"]) if query["date_to"] else None
            if start_date and end_date and start_date[0] > end_date[0]:
                raise ValueError("date_from 不可晚於 date_to")
            if not (query["keyword"] or start_date or query["document_number"]):
                raise ValueError("須提供 keyword、完整期間或 document_number 其中一項")
        except ValueError as exc:
            return error_response(str(exc), query=query)

        query["categories"] = selected_categories
        query["search_items"] = selected_items
        query["valid_statuses"] = selected_statuses

        try:
            form_response = await self._client.get(LAW_SEARCH_URL)
            form_response.raise_for_status()
            form = BeautifulSoup(form_response.text, "html.parser").find("form", id="form1")
            if form is None:
                raise ValueError("無法取得法務部查詢表單，官方網站可能已改版")

            form_data = {
                field["name"]: field.get("value", "")
                for field in form.select('input[type="hidden"][name]')
            }
            for key, (control_id, value) in _CATEGORIES.items():
                if key in selected_categories:
                    form_data[f"ctl00$cp_content${control_id}"] = value
            for key, (control_id, value) in _SEARCH_ITEMS.items():
                if key in selected_items:
                    form_data[f"ctl00$cp_content${control_id}"] = value
            for key, (control_id, value) in _STATUSES.items():
                if key in selected_statuses:
                    form_data[f"ctl00$cp_content${control_id}"] = value

            if query["keyword"]:
                form_data["ctl00$cp_content$WordSelect_tbKey1"] = query["keyword"]
            if start_date and end_date:
                form_data["ctl00$cp_content$tbxDateS"] = start_date[1]
                form_data["ctl00$cp_content$tbxDateE"] = end_date[1]
            if query["document_number"]:
                form_data["ctl00$cp_content$tbWordNum"] = query["document_number"]
            form_data["ctl00$cp_content$btnExec"] = "送出查詢"

            response = await self._client.post(
                LAW_SEARCH_URL,
                data=form_data,
                headers={"Referer": str(form_response.url)},
            )
            response.raise_for_status()
            search_url = str(response.url)
            results: list[dict] = []
            seen: set[tuple[str, str]] = set()
            has_more = False
            visited_pages: set[str] = set()

            while True:
                page_results, next_url = _parse_result_page(response.text, str(response.url))
                for item in page_results:
                    identity = (item["title"], item["source_url"])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    results.append(item)
                    if len(results) >= max_results:
                        break

                if len(results) >= max_results:
                    has_more = next_url is not None
                    break
                if not next_url or next_url in visited_pages:
                    break
                if urlparse(next_url).hostname != urlparse(LAW_SEARCH_URL).hostname:
                    raise ValueError("查詢結果分頁連結不在法務部官方網域")

                visited_pages.add(next_url)
                response = await self._client.get(next_url)
                response.raise_for_status()

            return {
                "success": True,
                "query": query,
                "total_count": len(results),
                "results": results,
                "has_more": has_more,
                "source_url": search_url,
                "timestamp": datetime.now().isoformat(),
            }
        except httpx.TimeoutException:
            logger.exception("法規異動查詢逾時")
            return error_response("查詢法務部全國法規資料庫逾時，請稍後重試", query=query)
        except httpx.HTTPError:
            logger.exception("法規異動查詢 HTTP 失敗")
            return error_response("查詢法務部全國法規資料庫失敗，請稍後重試", query=query)
        except Exception:
            logger.exception("法規異動查詢發生未預期錯誤")
            return error_response(
                "查詢法規異動時發生未預期錯誤，請查看 server log", query=query
            )