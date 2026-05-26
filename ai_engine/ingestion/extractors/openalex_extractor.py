import httpx
from datetime import datetime
from typing import List, Optional
import urllib.parse

from .base import BaseExtractor
from ..schemas import RawArticleSchema
from ..state_manager import load_state, save_state

class OpenAlexExtractor(BaseExtractor):
    BASE_URL = "https://api.openalex.org/works"
    
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

    def _parse_entry(self, entry: dict) -> RawArticleSchema:
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
            venue=venue
        )

    async def fetch_articles(self, query: str, max_results: int = 10) -> List[RawArticleSchema]:
        articles = []
        
        # State dosyasından kalınan cursor'ı oku
        saved_cursor = load_state("openalex")
        cursor = saved_cursor if saved_cursor else "*"
        
        search_param = ""
        if query.strip():
            encoded_query = urllib.parse.quote(query)
            search_param = f"&search={encoded_query}"
            
        while len(articles) < max_results:
            chunk_size = min(200, max_results - len(articles))
            url = f"{self.BASE_URL}?filter=concepts.id:C41008148{search_param}&per-page={chunk_size}&cursor={cursor}"
            
            headers = {"User-Agent": "mailto:contact@example.com"}
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(url)
                response.raise_for_status()

            data = response.json()
            results = data.get("results", [])
            
            if not results:
                break
                
            for entry in results:
                if entry.get("title"): # Skip entries without titles
                    articles.append(self._parse_entry(entry))
            
            new_cursor = data.get("meta", {}).get("next_cursor")
            if not new_cursor:
                break
            cursor = new_cursor
            
            # State'i kaydet
            save_state("openalex", cursor)
            
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
