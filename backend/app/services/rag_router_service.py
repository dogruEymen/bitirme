import json
import re
from datetime import date, timedelta

from backend.app.core.config import settings
from backend.app.schemas.retrieval import RetrievalFilters, RouteDecision
from backend.app.services.conversation_memory_service import ConversationMemory
from backend.app.services.ollama_service import OllamaService, get_ollama_service


RAG_KEYWORDS = (
    "paper",
    "papers",
    "makale",
    "makaleler",
    "article",
    "articles",
    "yayın",
    "publication",
    "cluster",
    "topic",
    "abstract",
    "özet",
    "veritabanı",
    "bu sistemde",
    "kaynak",
    "arxiv",
    "doi",
    "son yayın",
    "haftalık",
    "aylık",
    "trend",
    "önceki makale",
    "bunlar",
    "ikinci makale",
    "bu cluster",
    "önceki cevap",
    "onceki cevap",
    "pdf",
    "atıf",
    "citation",
)

class RagRouterService:
    def __init__(self, ollama_service: OllamaService | None = None):
        self.ollama_service = ollama_service or get_ollama_service()

    async def route(self, message: str, memory: ConversationMemory) -> RouteDecision:
        prompt = self._build_prompt(message, memory)
        raw_response = await self.ollama_service.generate_async(prompt)
        try:
            decision = RouteDecision.model_validate(self._parse_json_object(raw_response))
            return self._normalize_decision(decision, message, memory.previous_sources)
        except Exception:
            return self.fallback_route(message, memory.previous_sources)

    def fallback_route(self, message: str, previous_sources: list[dict] | None = None) -> RouteDecision:
        normalized = message.lower().strip()
        previous_sources = previous_sources or []
        article_ids = self._referenced_previous_article_ids(normalized, previous_sources)
        use_rag = bool(article_ids)

        if not use_rag and self._is_no_rag_message(normalized):
            use_rag = False
        elif any(keyword in normalized for keyword in RAG_KEYWORDS):
            use_rag = True

        filters = self._extract_filters(message, normalized, article_ids)

        top_k = self._extract_top_k(normalized)
        if article_ids:
            top_k = max(top_k, min(len(article_ids), 10))

        return RouteDecision(
            use_rag=use_rag,
            reason="Deterministic fallback route decision.",
            rewritten_query=message,
            filters=filters,
            top_k=top_k,
            sort_by=self._extract_sort_by(normalized),
        )

    def _build_prompt(self, message: str, memory: ConversationMemory) -> str:
        today = date.today().isoformat()
        return f"""
You are a routing component for an academic literature RAG system. Do not answer the user.
Return only strict JSON with these keys: use_rag, reason, rewritten_query, filters, top_k, sort_by.

Use RAG only when the user asks about papers stored in this system, clusters, citations, sources, PDFs, DOI, abstracts, trends, or follow-up questions about previously cited papers.
Do not use RAG for general educational questions such as "RAG nedir?" or "LLM nedir?".

Current date: {today}
Default top_k: {settings.RAG_TOP_K}
Supported sort_by values:
- "relevance": semantic relevance, default.
- "publish_date_desc": newest papers first. Use this when the user asks for latest/newest/recent papers, "son yayınlar", or "yayın tarihi en yeni".

Filters schema:
{{
  "source": null,
  "cluster_id": null,
  "primary_category": null,
  "categories_any": [],
  "venue": null,
  "doi": null,
  "has_pdf": null,
  "min_citation_count": null,
  "publish_date_from": null,
  "publish_date_to": null,
  "article_ids": []
}}

Conversation memory:
{memory.as_prompt_block() or "No prior context."}

User message:
{message}
""".strip()

    def _normalize_decision(
        self,
        decision: RouteDecision,
        message: str,
        previous_sources: list[dict],
    ) -> RouteDecision:
        if not decision.rewritten_query:
            decision.rewritten_query = message
        decision.top_k = max(1, min(decision.top_k or settings.RAG_TOP_K, 10))
        if decision.sort_by not in {"relevance", "publish_date_desc"}:
            decision.sort_by = "relevance"
        if decision.filters.source:
            decision.filters.source = decision.filters.source.lower()

        normalized = message.lower().strip()
        if self._is_no_rag_message(normalized):
            decision.use_rag = False
        article_ids = self._referenced_previous_article_ids(normalized, previous_sources)
        if article_ids:
            decision.use_rag = True
            decision.filters.article_ids = article_ids
            decision.top_k = max(decision.top_k, min(len(article_ids), 10))

        fallback_filters = self._extract_filters(message, normalized, decision.filters.article_ids)
        decision.filters = self._merge_filters(decision.filters, fallback_filters)
        fallback_sort = self._extract_sort_by(normalized)
        if fallback_sort != "relevance":
            decision.sort_by = fallback_sort
        return decision

    def _extract_filters(self, message: str, normalized: str, article_ids: list[int]) -> RetrievalFilters:
        filters = RetrievalFilters(article_ids=article_ids)
        self._extract_source_filter(normalized, filters)
        self._extract_cluster_filter(normalized, filters)
        self._extract_category_filter(message, filters)
        self._extract_doi_filter(message, filters)
        self._extract_pdf_filter(normalized, filters)
        self._extract_citation_filter(normalized, filters)
        self._extract_time_range_filter(normalized, filters)
        return filters

    @staticmethod
    def _merge_filters(primary: RetrievalFilters, fallback: RetrievalFilters) -> RetrievalFilters:
        data = primary.model_dump()
        fallback_data = fallback.model_dump()
        for key, value in fallback_data.items():
            current = data.get(key)
            if current in (None, [], "") and value not in (None, [], ""):
                data[key] = value
        return RetrievalFilters.model_validate(data)

    @staticmethod
    def _extract_source_filter(message: str, filters: RetrievalFilters) -> None:
        if "arxiv" in message:
            filters.source = "arxiv"
        elif "openalex" in message:
            filters.source = "openalex"
        elif "semantic scholar" in message or "semanticscholar" in message:
            filters.source = "semanticscholar"

    @staticmethod
    def _extract_cluster_filter(message: str, filters: RetrievalFilters) -> None:
        cluster_match = re.search(r"\bcluster\s*(?:id)?\s*[:#-]?\s*(\d+)\b", message)
        if cluster_match:
            filters.cluster_id = int(cluster_match.group(1))

    @staticmethod
    def _extract_category_filter(message: str, filters: RetrievalFilters) -> None:
        categories = re.findall(r"\bcs\.[A-Za-z]{2}\b", message)
        if categories:
            normalized_categories = []
            for category in categories:
                prefix, suffix = category.split(".", maxsplit=1)
                normalized_categories.append(f"{prefix.lower()}.{suffix.upper()}")
            filters.primary_category = normalized_categories[0]
            filters.categories_any = normalized_categories

    @staticmethod
    def _extract_doi_filter(message: str, filters: RetrievalFilters) -> None:
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", message, flags=re.IGNORECASE)
        if doi_match:
            filters.doi = doi_match.group(0).rstrip(".,;")

    @staticmethod
    def _extract_pdf_filter(message: str, filters: RetrievalFilters) -> None:
        if "pdf" in message:
            filters.has_pdf = True

    @staticmethod
    def _extract_citation_filter(message: str, filters: RetrievalFilters) -> None:
        citation_match = re.search(r"(?:en az|minimum|min|>=)\s*(\d+)\s*(?:citation|citations|atıf)", message)
        if citation_match:
            filters.min_citation_count = int(citation_match.group(1))

    @staticmethod
    def _extract_time_range_filter(message: str, filters: RetrievalFilters) -> None:
        today = date.today()
        days_match = re.search(r"(?:son|last)\s+(\d+)\s+(?:gün|gun|days?)", message)
        if days_match:
            days = max(1, int(days_match.group(1)))
            filters.publish_date_from = (today - timedelta(days=days)).isoformat()
            filters.publish_date_to = today.isoformat()
            return

        if any(phrase in message for phrase in ("son hafta", "last week", "son 1 hafta")):
            filters.publish_date_from = (today - timedelta(days=7)).isoformat()
            filters.publish_date_to = today.isoformat()
            return

        if any(phrase in message for phrase in ("son ay", "son 1 ay", "last month", "son 30 gün", "son 30 gun", "last 30 days")):
            filters.publish_date_from = (today - timedelta(days=30)).isoformat()
            filters.publish_date_to = today.isoformat()
            return

        year_match = re.search(r"\b(20\d{2}|19\d{2})\b", message)
        if year_match:
            year = int(year_match.group(1))
            filters.publish_date_from = date(year, 1, 1).isoformat()
            filters.publish_date_to = date(year, 12, 31).isoformat()

    @staticmethod
    def _extract_top_k(message: str) -> int:
        top_match = re.search(r"\b(?:top|ilk)\s+(\d{1,2})\b", message)
        if top_match:
            return max(1, min(int(top_match.group(1)), 10))

        count_match = re.search(r"\b(\d{1,2})\s+(?:makale|paper|papers|article|articles)\b", message)
        if count_match:
            return max(1, min(int(count_match.group(1)), 10))

        return settings.RAG_TOP_K

    @staticmethod
    def _extract_sort_by(message: str) -> str:
        newest_phrases = (
            "en yeni",
            "son yayın",
            "son yayin",
            "son makale",
            "latest",
            "newest",
            "most recent",
            "publication date",
            "yayın tarihi",
            "yayin tarihi",
        )
        if any(phrase in message for phrase in newest_phrases):
            return "publish_date_desc"
        return "relevance"

    @staticmethod
    def _parse_json_object(raw_response: str) -> dict:
        text = raw_response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(text[start : end + 1])

    @staticmethod
    def _is_no_rag_message(message: str) -> bool:
        normalized = message.strip(" ?!.")
        exact_no_rag = {"selam", "merhaba", "nasılsın", "bana python anlat", "uygulamayı nasıl kullanırım"}
        if normalized in exact_no_rag:
            return True
        return normalized.startswith("rag nedir") or normalized.startswith("llm nedir")

    @staticmethod
    def _referenced_previous_article_ids(message: str, previous_sources: list[dict]) -> list[int]:
        if not previous_sources:
            return []

        source_id_match = re.search(r"\bs\s*(\d+)\b", message, flags=re.IGNORECASE)
        if source_id_match:
            wanted_source_id = f"S{source_id_match.group(1)}"
            for source in previous_sources:
                if str(source.get("source_id", "")).upper() == wanted_source_id:
                    article_id = source.get("article_id")
                    return [int(article_id)] if article_id is not None else []

        ordinal_map = {
            "ilk": 0,
            "birinci": 0,
            "1.": 0,
            "ikinci": 1,
            "2.": 1,
            "üçüncü": 2,
            "ucuncu": 2,
            "3.": 2,
        }
        for token, index in ordinal_map.items():
            if token in message and index < len(previous_sources):
                article_id = previous_sources[index].get("article_id")
                return [int(article_id)] if article_id is not None else []

        if any(
            phrase in message
            for phrase in (
                "bunlar",
                "bu makaleler",
                "bu kaynaklar",
                "bu kaynakların",
                "önceki kaynak",
                "onceki kaynak",
                "önceki cevap",
                "onceki cevap",
                "önceki cevaptaki",
                "onceki cevaptaki",
            )
        ):
            return [
                int(source["article_id"])
                for source in previous_sources
                if source.get("article_id") is not None
            ]

        if any(phrase in message for phrase in ("önceki makale", "onceki makale", "bu makale")):
            article_id = previous_sources[-1].get("article_id")
            return [int(article_id)] if article_id is not None else []
        return []
