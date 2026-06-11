from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from backend.app.schemas.retrieval import RetrievalFilters
from backend.app.services.retrieval_service import (
    _apply_filters,
    _deduplicate_and_rerank,
    _deduplicate_preserving_order,
    _extract_keyword_terms,
    _format_results,
    _keyword_score,
)
from database.models.ArticleData import Article


def compile_filtered_sql(filters: RetrievalFilters):
    statement = _apply_filters(select(Article), filters)
    compiled = statement.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def test_source_filter_is_applied():
    sql, params = compile_filtered_sql(RetrievalFilters(source="arxiv"))

    assert "articles.source" in sql
    assert params["source_1"] == "arxiv"


def test_date_range_filter_is_applied():
    sql, params = compile_filtered_sql(
        RetrievalFilters(publish_date_from="2026-01-01", publish_date_to="2026-05-28")
    )

    assert "articles.publish_date >=" in sql
    assert "articles.publish_date <=" in sql
    assert params


def test_category_filter_is_applied():
    sql, params = compile_filtered_sql(RetrievalFilters(primary_category="cs.CL", categories_any=["cs.CL"]))

    assert "articles.primary_category" in sql
    assert "articles.categories" in sql
    assert params["primary_category_1"] == "cs.CL"


def test_has_pdf_filter_is_applied():
    sql, params = compile_filtered_sql(RetrievalFilters(has_pdf=True))

    assert "articles.pdf_url IS NOT NULL" in sql
    assert params["metadata_json_1"] == "has_pdf"


def test_empty_result_returns_empty_list():
    assert _format_results(_deduplicate_and_rerank([])) == []


def test_publish_date_sorted_results_keep_database_order():
    older = Article(id=1, source="arxiv", external_id="old", title="Older", publish_date=datetime(2025, 1, 1))
    newer = Article(id=2, source="arxiv", external_id="new", title="Newer", publish_date=datetime(2026, 1, 1))

    results = _format_results(_deduplicate_preserving_order([newer, older]))

    assert [result.source.title for result in results] == ["Newer", "Older"]
    assert results[0].source.vector_score is None


def test_returned_sources_include_citation_metadata_and_score():
    article = Article(
        id=1,
        source="arxiv",
        external_id="1234.5678",
        title="Retrieval Paper",
        abstract_text="Abstract",
        doi="10.1234/rag",
        url="https://example.test/paper",
        authors="Alice",
        publish_date=datetime(2026, 5, 28),
        cluster_id=7,
        citation_count=42,
    )

    result = _format_results(_deduplicate_and_rerank([(article, 0.2)]))[0]

    assert result.source.source_id == "S1"
    assert result.source.article_id == 1
    assert result.source.title == "Retrieval Paper"
    assert result.source.doi == "10.1234/rag"
    assert result.source.url == "https://example.test/paper"
    assert result.source.score is not None


def test_keyword_only_result_does_not_get_perfect_vector_score():
    article = Article(
        id=1,
        source="arxiv",
        external_id="keyword",
        title="MACE: A Hybrid LLM Serving System",
        abstract_text="MACE colocates inference and fine-tuning on edge servers.",
    )
    result = _format_results(_deduplicate_and_rerank([(article, None, 8.0)]))[0]

    assert result.source.vector_score is None
    assert result.source.score is not None
    assert result.source.score < 1.0


def test_keyword_terms_keep_named_system_and_drop_generic_words():
    terms = _extract_keyword_terms(
        "Uc sunucularda inference ve fine-tuning yuruten MACE adlı hibrit LLM sistemini hangi makale onermektedir?"
    )

    assert "mace" in terms
    assert "llm" in terms
    assert "adli" not in terms
    assert "makale" not in terms
    assert "hangi" not in terms


def test_keyword_score_prioritizes_named_system_matches():
    matching = Article(
        id=1,
        source="arxiv",
        external_id="mace",
        title="MACE: A Hybrid LLM Serving System",
        abstract_text="MACE colocates inference and fine-tuning on edge servers.",
    )
    unrelated = Article(
        id=2,
        source="arxiv",
        external_id="other",
        title="Efficient LLM Serving",
        abstract_text="This paper discusses serving systems.",
    )
    terms = ["mace", "llm", "inference"]

    assert _keyword_score(matching, terms) > _keyword_score(unrelated, terms)
