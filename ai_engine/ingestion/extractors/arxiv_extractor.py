import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import AsyncIterator, List, Optional
import urllib.parse
import asyncio
import calendar
import logging

from .base import BaseExtractor
from ..schemas import RawArticleSchema
from ..state_manager import load_state

logger = logging.getLogger(__name__)


class ArxivExtractor(BaseExtractor):
    BASE_URL = "https://export.arxiv.org/api/query"
    REQUEST_SIZE = 500
    REQUEST_ATTEMPTS = 6
    REQUEST_TIMEOUT = httpx.Timeout(90.0, connect=20.0)
    
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
        if isinstance(saved_state, dict):
            current_date = saved_state.get("current_date", "2000-01-01")
            current_start = int(saved_state.get("start_offset", 0) or 0)
        else:
            current_date = "2000-01-01"
            current_start = 0

        return datetime.strptime(current_date, "%Y-%m-%d"), current_start

    def _next_month(self, value: datetime) -> datetime:
        if value.month == 12:
            return datetime(value.year + 1, 1, 1)
        return datetime(value.year, value.month + 1, 1)

    def _build_query(self, query: str) -> str:
        base_query = "cat:cs.*"
        if query.strip():
            encoded_query = urllib.parse.quote(query.strip())
            base_query = f"all:{encoded_query}+AND+cat:cs.*"
        return base_query

    def _retry_delay(self, attempt: int, response: Optional[httpx.Response] = None) -> int:
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after and retry_after.isdigit():
            return min(int(retry_after), 120)
        return min(10 * attempt, 60)

    async def _get_with_retries(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.REQUEST_ATTEMPTS + 1):
            try:
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
                if attempt == self.REQUEST_ATTEMPTS:
                    return response

                delay = self._retry_delay(attempt, response)
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
            "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
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

        while fetched_count < max_results:
            year = current_dt.year
            month = current_dt.month
            _, last_day = calendar.monthrange(year, month)

            start_date_str = f"{year:04d}{month:02d}010000"
            end_date_str = f"{year:04d}{month:02d}{last_day:02d}2359"
            chunk_size = min(self.REQUEST_SIZE, max_results - fetched_count)

            search_param = f"{base_query}+AND+submittedDate:[{start_date_str}+TO+{end_date_str}]"
            url = f"{self.BASE_URL}?search_query={search_param}&start={current_start}&max_results={chunk_size}&sortBy=submittedDate&sortOrder=ascending"

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
                current_dt = self._next_month(current_dt)
                if current_dt > datetime.now():
                    break
                current_start = 0
                await asyncio.sleep(3)
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

            await asyncio.sleep(3.5)

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
