import httpx
from datetime import datetime
from typing import List, Optional
import urllib.parse

from .base import BaseExtractor
from ..schemas import RawArticleSchema
from ..state_manager import load_state

class OpenAlexExtractor(BaseExtractor):
    BASE_URL = "https://api.openalex.org/works"
    COMPUTER_SCIENCE_CONCEPT_ID = "C41008148"
    MIN_PUBLICATION_DATE = "2000-01-01"
    MIN_PUBLICATION_DATETIME = datetime(2000, 1, 1)
    FILTER_SIGNATURE = f"concepts.id:{COMPUTER_SCIENCE_CONCEPT_ID};from_publication_date:{MIN_PUBLICATION_DATE}"

    def __init__(self):
        self._state_checkpoint = None
    
    @property
    def source_name(self) -> str:
        return "openalex"

    def _parse_date(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).replace(tzinfo=None)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value.rstrip("Z"), fmt)
            except ValueError:
                continue
        return None

    def _doi_value(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return value.replace("https://doi.org/", "").replace("http://doi.org/", "")

    def _nested(self, data: dict, *keys):
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _build_works_url(self, query: str, cursor: str, per_page: int) -> str:
        filters = [
            f"concepts.id:{self.COMPUTER_SCIENCE_CONCEPT_ID}",
            f"from_publication_date:{self.MIN_PUBLICATION_DATE}",
        ]
        params = {
            "filter": ",".join(filters),
            "per-page": str(per_page),
            "cursor": cursor,
        }
        if query.strip():
            params["search"] = query.strip()
        return f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"

    def _is_supported_publication_date(self, publish_date: Optional[datetime]) -> bool:
        return publish_date is None or publish_date >= self.MIN_PUBLICATION_DATETIME

    def _reconstruct_abstract(self, inverted_index: dict) -> Optional[str]:
        """
        OpenAlex returns abstracts as an inverted index (word -> [positions]).
        This helper reconstructs the original string.
        """
        if not inverted_index:
            return None
            
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
                
        # Sort by position
        word_positions.sort(key=lambda x: x[0])
        return " ".join([word for _, word in word_positions])

    def get_state_checkpoint(self):
        return self._state_checkpoint

    def _is_computer_science_entry(self, entry: dict) -> bool:
        for concept in entry.get("concepts", []) or []:
            concept_id = (concept.get("id") or "").split("/")[-1]
            display_name = (concept.get("display_name") or "").lower()
            if concept_id == self.COMPUTER_SCIENCE_CONCEPT_ID or display_name == "computer science":
                return True

        for topic in entry.get("topics", []) or []:
            for key in ("display_name", "subfield", "field", "domain"):
                value = topic.get(key)
                if isinstance(value, dict):
                    value = value.get("display_name")
                if isinstance(value, str) and value.lower() == "computer science":
                    return True

        return False

    def _parse_entry(self, entry: dict, is_computer_science: Optional[bool] = None) -> RawArticleSchema:
        """Parses an OpenAlex JSON entry into a RawArticleSchema."""
        external_id = entry.get("id", "").split("/")[-1]
        title = entry.get("title") or entry.get("display_name") or "Untitled"
        
        abstract_index = entry.get("abstract_inverted_index")
        abstract_text = self._reconstruct_abstract(abstract_index)
        
        publish_date = self._parse_date(entry.get("publication_date"))
        updated_date = self._parse_date(entry.get("updated_date"))
                
        authors_list = []
        for authorship in entry.get("authorships", []):
            author_name = authorship.get("author", {}).get("display_name")
            if author_name:
                authors_list.append(author_name)
        authors = ", ".join(authors_list)

        pdf_url = (
            self._nested(entry, "best_oa_location", "pdf_url")
            or self._nested(entry, "primary_location", "pdf_url")
            or self._nested(entry, "open_access", "oa_url")
        )
        url = (
            self._nested(entry, "primary_location", "landing_page_url")
            or self._nested(entry, "best_oa_location", "landing_page_url")
            or entry.get("doi")
            or entry.get("id")
        )
        
        primary_category = None
        primary_topic = entry.get("primary_topic")
        if primary_topic:
            primary_category = primary_topic.get("display_name")

        categories_list = []
        for topic in entry.get("topics", []) or []:
            display_name = topic.get("display_name")
            if display_name and display_name not in categories_list:
                categories_list.append(display_name)
        for concept in entry.get("concepts", []) or []:
            display_name = concept.get("display_name")
            if display_name and display_name not in categories_list:
                categories_list.append(display_name)
        if primary_category and primary_category not in categories_list:
            categories_list.insert(0, primary_category)

        venue = self._nested(entry, "primary_location", "source", "display_name")
        if not venue:
            venue = self._nested(entry, "best_oa_location", "source", "display_name")

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
            doi=self._doi_value(entry.get("doi")),
            citation_count=entry.get("cited_by_count"),
            venue=venue,
            metadata_json={
                "source_payload_version": "v1",
                "is_computer_science": (
                    self._is_computer_science_entry(entry)
                    if is_computer_science is None
                    else is_computer_science
                ),
                "openalex_id": entry.get("id"),
                "openalex_work_id": external_id,
                "open_access_status": self._nested(entry, "open_access", "oa_status"),
                "publication_type": entry.get("type"),
            },
        )

    async def fetch_articles(self, query: str, max_results: int = 10) -> List[RawArticleSchema]:
        articles = []
        
        saved_cursor = load_state("openalex")
        if isinstance(saved_cursor, dict) and saved_cursor.get("filter_signature") == self.FILTER_SIGNATURE:
            cursor = saved_cursor.get("cursor") or "*"
        else:
            cursor = "*"
        
        while len(articles) < max_results:
            chunk_size = min(200, max_results - len(articles))
            url = self._build_works_url(query, cursor, chunk_size)
            
            headers = {"User-Agent": "mailto:contact@example.com"}
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(url)
                response.raise_for_status()

            data = response.json()
            results = data.get("results", [])
            
            if not results:
                break
                
            for entry in results:
                publish_date = self._parse_date(entry.get("publication_date"))
                if not entry.get("title"):
                    continue
                if not self._is_computer_science_entry(entry):
                    continue
                if not self._is_supported_publication_date(publish_date):
                    continue
                articles.append(self._parse_entry(entry, is_computer_science=True))
            
            new_cursor = data.get("meta", {}).get("next_cursor")
            if not new_cursor:
                break
            cursor = new_cursor
            self._state_checkpoint = {
                "cursor": cursor,
                "filter_signature": self.FILTER_SIGNATURE,
                "last_external_id": articles[-1].external_id if articles else None,
                "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            
            import asyncio
            await asyncio.sleep(1) # OpenAlex'i yormamak için sayfa arası bekle
            
        return articles

    async def fetch_article_by_id(self, article_id: str) -> Optional[RawArticleSchema]:
        # article_id should be something like W2741809807
        url = f"{self.BASE_URL}/{article_id}"
        
        headers = {"User-Agent": "mailto:contact@example.com"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()

        data = response.json()
        return self._parse_entry(data)
