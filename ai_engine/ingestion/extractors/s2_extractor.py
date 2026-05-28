import httpx
from datetime import datetime
from typing import List, Optional
import urllib.parse

from .base import BaseExtractor
from ..schemas import RawArticleSchema

class SemanticScholarExtractor(BaseExtractor):
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper"
    
    @property
    def source_name(self) -> str:
        return "semanticscholar"

    def _parse_date(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    def _parse_entry(self, entry: dict) -> RawArticleSchema:
        """Parses a Semantic Scholar JSON entry into a RawArticleSchema."""
        external_id = entry.get("paperId", "")
        title = entry.get("title") or "Untitled"
        abstract_text = entry.get("abstract")
        
        publish_date = self._parse_date(entry.get("publicationDate"))
                
        authors_list = []
        for author in entry.get("authors", []):
            name = author.get("name")
            if name:
                authors_list.append(name)
        authors = ", ".join(authors_list)

        pdf_url = None
        open_access = entry.get("openAccessPdf")
        if open_access and isinstance(open_access, dict):
            pdf_url = open_access.get("url")
        
        primary_category = None
        fields_of_study = entry.get("s2FieldsOfStudy", [])
        if fields_of_study and len(fields_of_study) > 0:
            primary_category = fields_of_study[0].get("category")

        categories_list = []
        for field in fields_of_study or []:
            category = field.get("category")
            if category and category not in categories_list:
                categories_list.append(category)
        for field in entry.get("fieldsOfStudy", []) or []:
            if field and field not in categories_list:
                categories_list.append(field)

        external_ids = entry.get("externalIds") or {}
        publication_venue = entry.get("publicationVenue") or {}
        journal = entry.get("journal") or {}
        venue = publication_venue.get("name") or entry.get("venue") or journal.get("name")

        return RawArticleSchema(
            source=self.source_name,
            external_id=external_id,
            title=title,
            abstract_text=abstract_text,
            publish_date=publish_date,
            updated_date=None,
            authors=authors,
            url=entry.get("url"),
            pdf_url=pdf_url,
            primary_category=primary_category,
            categories=", ".join(categories_list) or None,
            doi=external_ids.get("DOI"),
            citation_count=entry.get("citationCount"),
            venue=venue,
            metadata_json={
                "source_payload_version": "v1",
                "is_computer_science": any(
                    category.lower() == "computer science"
                    for category in categories_list
                ),
                "semantic_scholar_paper_id": external_id,
                "external_ids": external_ids,
                "publication_venue_id": publication_venue.get("id"),
            },
        )

    async def fetch_articles(self, query: str, max_results: int = 10) -> List[RawArticleSchema]:
        encoded_query = urllib.parse.quote(query)
        fields = "paperId,title,abstract,authors,openAccessPdf,publicationDate,s2FieldsOfStudy,fieldsOfStudy,externalIds,url,citationCount,venue,journal,publicationVenue"
        articles = []
        
        for offset in range(0, max_results, 100):
            chunk_size = min(100, max_results - offset)
            url = f"{self.BASE_URL}/search?query={encoded_query}&limit={chunk_size}&offset={offset}&fields={fields}&fieldsOfStudy=Computer+Science"
            
            headers = {"User-Agent": "Academic Literature Platform/1.0 (mailto:contact@example.com)"}
            
            success = False
            for attempt in range(3):
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                    response = await client.get(url)
                    if response.status_code == 429:
                        import asyncio
                        await asyncio.sleep(5) # 5 saniye bekle ve tekrar dene
                        continue
                    response.raise_for_status()
                    success = True
                    break
                    
            if not success:
                break # Rate limit aşılamadı, sayfalama durdurulur
                
            data = response.json()
            results = data.get("data", [])
            
            if not results:
                break
                
            for entry in results:
                if entry.get("title"):
                    articles.append(self._parse_entry(entry))
                    
            if len(results) < chunk_size:
                break # Son sayfaya ulaştık
                
            import asyncio
            await asyncio.sleep(3) # S2 API'sine saygılı olmak için her sayfa arası 3 sn bekle
            
        return articles[:max_results]

    async def fetch_article_by_id(self, article_id: str) -> Optional[RawArticleSchema]:
        fields = "paperId,title,abstract,authors,openAccessPdf,publicationDate,s2FieldsOfStudy,fieldsOfStudy,externalIds,url,citationCount,venue,journal,publicationVenue"
        url = f"{self.BASE_URL}/{article_id}?fields={fields}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()

        data = response.json()
        return self._parse_entry(data)
