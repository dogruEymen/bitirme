import httpx
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import AsyncIterator, List, Optional
import urllib.parse
import asyncio
import calendar
import logging
import time

from .base import BaseExtractor
from ..schemas import RawArticleSchema
from ..state_manager import load_state

logger = logging.getLogger(__name__)


class ArxivExtractor(BaseExtractor):
    BASE_URL = "https://export.arxiv.org/api/query"
    REQUEST_SIZE = 500
    REQUEST_ATTEMPTS = 6
    REQUEST_TIMEOUT = httpx.Timeout(90.0, connect=20.0)
    CURSOR_DIRECTION = "backward"
    EARLIEST_CURSOR_DATE = datetime(2000, 1, 1)
    MONTHLY_OFFSET_LIMIT = 3000
    DEFAULT_RATE_LIMIT_DELAY = 180
    REQUEST_INTERVAL_SECONDS = 3.0
    RATE_LIMIT_HEADERS = (
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "RateLimit-Limit",
        "RateLimit-Remaining",
        "RateLimit-Reset",
    )

    def __init__(self):
        self._last_request_monotonic: Optional[float] = None
    
    @property
    def source_name(self) -> str:
        return "arxiv"

    def _parse_arxiv_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None

    def _text(self, entry: ET.Element, path: str, namespace: dict) -> Optional[str]:
        elem = entry.find(path, namespace)
        if elem is None or elem.text is None:
            return None
        return elem.text.replace("\n", " ").strip()

    def _initial_cursor(self) -> tuple[datetime, int]:
        saved_state = load_state("arxiv")
        if isinstance(saved_state, dict) and saved_state.get("cursor_direction") == self.CURSOR_DIRECTION:
            current_date = saved_state.get("current_date")
            current_start = int(saved_state.get("start_offset", 0) or 0)
            if current_date:
                return datetime.strptime(current_date, "%Y-%m-%d"), current_start

        return self._current_month_start(), 0

    def _current_month_start(self) -> datetime:
        now = datetime.now(UTC)
        return datetime(now.year, now.month, 1)

    def _previous_month(self, value: datetime) -> datetime:
        if value.month == 1:
            return datetime(value.year - 1, 12, 1)
        return datetime(value.year, value.month - 1, 1)

    def _monthly_request_size(self, fetched_count: int, max_results: int, current_start: int) -> int:
        monthly_remaining = self.MONTHLY_OFFSET_LIMIT - current_start
        if monthly_remaining <= 0:
            return 0
        return min(self.REQUEST_SIZE, max_results - fetched_count, monthly_remaining)

    def _request_wait_seconds(self, now_monotonic: float) -> float:
        if self._last_request_monotonic is None:
            return 0.0
        elapsed = now_monotonic - self._last_request_monotonic
        return max(0.0, self.REQUEST_INTERVAL_SECONDS - elapsed)

    async def _respect_request_interval(self) -> None:
        wait_seconds = self._request_wait_seconds(time.monotonic())
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        self._last_request_monotonic = time.monotonic()

    def _build_query(self, query: str) -> str:
        base_query = "cat:cs.*"
        if query.strip():
            encoded_query = urllib.parse.quote(query.strip())
            base_query = f"all:{encoded_query}+AND+cat:cs.*"
        return base_query

    def _retry_delay(self, attempt: int, response: Optional[httpx.Response] = None) -> int:
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after and retry_after.isdigit():
            return max(1, int(retry_after))
        if retry_after:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                delay = (retry_at - datetime.now(UTC)).total_seconds()
                return max(1, int(delay))
            except (TypeError, ValueError):
                logger.warning("arXiv Retry-After header parse edilemedi: %s", retry_after)
        if response is not None and response.status_code == 429:
            return self.DEFAULT_RATE_LIMIT_DELAY
        return min(10 * attempt, 60)

    def _rate_limit_details(self, response: httpx.Response) -> dict:
        details = {
            header: response.headers[header]
            for header in self.RATE_LIMIT_HEADERS
            if header in response.headers
        }
        if response.text:
            details["body_excerpt"] = response.text.replace("\n", " ").strip()[:300]
        return details

    async def _get_with_retries(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.REQUEST_ATTEMPTS + 1):
            try:
                await self._respect_request_interval()
                response = await client.get(url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == self.REQUEST_ATTEMPTS:
                    break

                delay = self._retry_delay(attempt)
                logger.warning(
                    "arXiv istegi basarisiz oldu (%s/%s): %s. %s sn sonra tekrar denenecek.",
                    attempt,
                    self.REQUEST_ATTEMPTS,
                    exc.__class__.__name__,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                details = self._rate_limit_details(response) if response.status_code == 429 else {}
                if attempt == self.REQUEST_ATTEMPTS:
                    if details:
                        logger.error("arXiv 429 rate limit bilgisi: %s", details)
                    return response

                delay = self._retry_delay(attempt, response)
                if response.status_code == 429:
                    logger.warning(
                        "arXiv HTTP 429 dondu (%s/%s). %s sn sonra tekrar denenecek. Rate limit bilgisi: %s",
                        attempt,
                        self.REQUEST_ATTEMPTS,
                        delay,
                        details or "header yok",
                    )
                else:
                    logger.warning(
                        "arXiv HTTP %s dondu (%s/%s). %s sn sonra tekrar denenecek.",
                        response.status_code,
                        attempt,
                        self.REQUEST_ATTEMPTS,
                        delay,
                    )
                await asyncio.sleep(delay)
                continue

            return response

        raise RuntimeError(
            f"arXiv request failed after {self.REQUEST_ATTEMPTS} attempts"
        ) from last_error

    def _checkpoint(
        self,
        current_dt: datetime,
        next_start: int,
        last_article: Optional[RawArticleSchema],
    ) -> dict:
        checkpoint = {
            "current_date": current_dt.strftime("%Y-%m-%d"),
            "start_offset": next_start,
            "cursor_direction": self.CURSOR_DIRECTION,
            "sort_order": "submittedDate_desc",
            "updated_at": (
                datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
            ),
        }
        if last_article is not None:
            checkpoint["last_external_id"] = last_article.external_id
            checkpoint["last_publish_date"] = (
                last_article.publish_date.isoformat()
                if last_article.publish_date
                else None
            )
            checkpoint["last_title"] = last_article.title[:200]
        return checkpoint

    def _parse_entry(self, entry: ET.Element, namespace: dict) -> RawArticleSchema:
        """Parses an Atom entry from arXiv into a RawArticleSchema."""
        url = self._text(entry, "atom:id", namespace)
        external_id = url.split("/")[-1] if url else ""
        title = self._text(entry, "atom:title", namespace) or "Untitled"
        abstract_text = self._text(entry, "atom:summary", namespace)
        
        publish_date = self._parse_arxiv_datetime(self._text(entry, "atom:published", namespace))
        updated_date = self._parse_arxiv_datetime(self._text(entry, "atom:updated", namespace))
                
        authors = ", ".join([
            author_name
            for author in entry.findall("atom:author", namespace)
            if (author_name := self._text(author, "atom:name", namespace))
        ])
        
        pdf_url = None
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href")
                break

        categories_list = [
            category.attrib.get("term")
            for category in entry.findall("atom:category", namespace)
            if category.attrib.get("term")
        ]
                
        primary_category = None
        primary_category_elem = entry.find("arxiv:primary_category", namespace)
        if primary_category_elem is not None:
            primary_category = primary_category_elem.attrib.get("term")
        if primary_category is None and categories_list:
            primary_category = categories_list[0]

        doi = self._text(entry, "arxiv:doi", namespace)
        venue = self._text(entry, "arxiv:journal_ref", namespace)

        return RawArticleSchema(
            source=self.source_name,
            external_id=external_id,
            title=title,
            abstract_text=abstract_text,
            publish_date=publish_date,
            updated_date=updated_date,
            authors=authors,
            url=url,
            pdf_url=pdf_url,
            primary_category=primary_category,
            categories=", ".join(categories_list) or None,
            doi=doi,
            citation_count=None,
            venue=venue,
            metadata_json={
                "source_payload_version": "v1",
                "is_computer_science": any(
                    category.lower().startswith("cs.")
                    for category in categories_list
                ),
                "arxiv_id": external_id,
                "arxiv_primary_category": primary_category,
                "arxiv_categories": categories_list,
            },
        )

    async def fetch_articles(self, query: str, max_results: int = 10) -> List[RawArticleSchema]:
        articles = []
        async for batch, _checkpoint in self.fetch_article_batches(
            query,
            max_results=max_results,
            batch_size=max_results,
        ):
            articles.extend(batch)
        return articles

    async def fetch_article_batches(
        self,
        query: str,
        max_results: int = 10,
        batch_size: int = 2000,
    ) -> AsyncIterator[tuple[List[RawArticleSchema], dict]]:
        articles: List[RawArticleSchema] = []
        fetched_count = 0
        current_dt, current_start = self._initial_cursor()
        base_query = self._build_query(query)
        pending_checkpoint: Optional[dict] = None

        while fetched_count < max_results and current_dt >= self.EARLIEST_CURSOR_DATE:
            year = current_dt.year
            month = current_dt.month
            _, last_day = calendar.monthrange(year, month)

            start_date_str = f"{year:04d}{month:02d}010000"
            end_date_str = f"{year:04d}{month:02d}{last_day:02d}2359"
            chunk_size = self._monthly_request_size(fetched_count, max_results, current_start)
            if chunk_size <= 0:
                current_dt = self._previous_month(current_dt)
                current_start = 0
                continue

            search_param = f"{base_query}+AND+submittedDate:[{start_date_str}+TO+{end_date_str}]"
            url = (
                f"{self.BASE_URL}?search_query={search_param}"
                f"&start={current_start}&max_results={chunk_size}"
                "&sortBy=submittedDate&sortOrder=descending"
            )

            response = None
            async with httpx.AsyncClient(
                timeout=self.REQUEST_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "Academic Literature Platform/1.0"},
            ) as client:
                response = await self._get_with_retries(client, url)

            if response is None:
                raise RuntimeError("arXiv response was not received")
            if response.status_code != 200:
                raise RuntimeError(
                    f"arXiv returned HTTP {response.status_code}: {response.text[:300]}"
                )

            namespace = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom"
            }
            try:
                root = ET.fromstring(response.text)
            except ET.ParseError as exc:
                raise RuntimeError(f"arXiv returned invalid XML: {exc}") from exc

            entries = root.findall("atom:entry", namespace)

            if not entries:
                current_dt = self._previous_month(current_dt)
                current_start = 0
                continue

            page_articles: List[RawArticleSchema] = []
            for entry in entries:
                page_articles.append(self._parse_entry(entry, namespace))

            articles.extend(page_articles)
            fetched_count += len(page_articles)
            current_start += len(entries)
            pending_checkpoint = self._checkpoint(
                current_dt,
                current_start,
                page_articles[-1] if page_articles else None,
            )

            if len(articles) >= batch_size and pending_checkpoint is not None:
                yield articles, pending_checkpoint
                articles = []
                pending_checkpoint = None

        if articles and pending_checkpoint is not None:
            yield articles, pending_checkpoint

    async def fetch_article_by_id(self, article_id: str) -> Optional[RawArticleSchema]:
        url = f"{self.BASE_URL}?id_list={article_id}"
        
        async with httpx.AsyncClient(
            timeout=self.REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Academic Literature Platform/1.0"},
        ) as client:
            response = await self._get_with_retries(client, url)
            response.raise_for_status()

        namespace = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom"
        }
        root = ET.fromstring(response.text)
        entries = root.findall("atom:entry", namespace)
        
        if not entries:
            return None
            
        return self._parse_entry(entries[0], namespace)
