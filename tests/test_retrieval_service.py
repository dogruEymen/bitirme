import sqlite3
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from backend.app.schemas.retrieval import RetrievalFilters
from backend.app.services import retrieval_service as retrieval_service_module
from backend.app.services.retrieval_service import (
    BM25Retriever,
    CrossEncoderReranker,
    RetrievalCandidate,
    _apply_filters,
    _format_candidate_results,
    _deduplicate_and_rerank,
    _deduplicate_preserving_order,
    _extract_keyword_terms,
    _format_results,
    _keyword_score,
    _reciprocal_rank_fusion,
    _sanitize_fts_query,
    check_bm25_index_status,
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


def test_rrf_merges_duplicate_article_from_vector_and_bm25():
    article = Article(id=1, source="arxiv", external_id="same", title="Hybrid Retrieval")
    vector = RetrievalCandidate(article=article, retrieval_source="vector", vector_score=0.8, vector_rank=2)
    bm25 = RetrievalCandidate(article=article, retrieval_source="bm25", bm25_score=4.0, bm25_rank=1)

    fused = _reciprocal_rank_fusion([vector], [bm25], rrf_k=60)

    assert len(fused) == 1
    assert fused[0].retrieval_source == "both"
    assert fused[0].vector_rank == 2
    assert fused[0].bm25_rank == 1
    assert fused[0].fusion_score > 0


def test_cross_encoder_reranker_promotes_relevant_candidate(monkeypatch):
    class FakeModel:
        def predict(self, pairs):
            return [10.0 if "Correct" in document else 0.1 for _, document in pairs]

    monkeypatch.setattr(retrieval_service_module, "get_reranker_model", lambda: FakeModel())

    wrong = RetrievalCandidate(
        article=Article(id=1, source="arxiv", external_id="wrong", title="Wrong Paper", abstract_text="Noise"),
        retrieval_source="vector",
        fusion_score=0.9,
    )
    correct = RetrievalCandidate(
        article=Article(id=2, source="arxiv", external_id="correct", title="Correct Paper", abstract_text="Answer"),
        retrieval_source="vector",
        fusion_score=0.1,
    )

    reranked, failed = CrossEncoderReranker().rerank("question", [wrong, correct])

    assert failed is False
    assert [candidate.article.id for candidate in reranked] == [2, 1]
    assert reranked[0].reranker_score == 10.0


def test_cross_encoder_reranker_falls_back_on_failure(monkeypatch):
    def fail():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(retrieval_service_module, "get_reranker_model", fail)
    candidates = [
        RetrievalCandidate(
            article=Article(id=1, source="arxiv", external_id="first", title="First"),
            retrieval_source="vector",
            fusion_score=0.9,
        ),
        RetrievalCandidate(
            article=Article(id=2, source="arxiv", external_id="second", title="Second"),
            retrieval_source="vector",
            fusion_score=0.1,
        ),
    ]

    reranked, failed = CrossEncoderReranker().rerank("question", candidates)

    assert failed is True
    assert reranked == candidates


def test_format_candidate_results_exposes_reranker_score():
    candidate = RetrievalCandidate(
        article=Article(id=1, source="arxiv", external_id="paper", title="Reranked Paper"),
        retrieval_source="vector",
        fusion_score=0.2,
        reranker_score=7.5,
    )

    result = _format_candidate_results([candidate])[0]

    assert result.source.score == 7.5
    assert result.source.fusion_score == 0.2
    assert result.source.reranker_score == 7.5


def test_sanitize_fts_query_keeps_acronyms_and_drops_stopwords():
    query = _sanitize_fts_query("Which paper introduced MACE for LLM inference?")

    assert '"mace"' in query
    assert '"llm"' in query
    assert "paper" not in query


def test_bm25_retriever_prioritizes_title_match(tmp_path):
    index_path = tmp_path / "articles_bm25.sqlite"
    with sqlite3.connect(index_path) as conn:
        conn.execute(
            """
            CREATE VIRTUAL TABLE articles_fts USING fts5(
                article_id UNINDEXED,
                title,
                abstract_text,
                source UNINDEXED,
                primary_category UNINDEXED,
                categories UNINDEXED,
                cluster_id UNINDEXED,
                doi UNINDEXED,
                venue UNINDEXED,
                publish_date UNINDEXED,
                tokenize = 'porter unicode61'
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO articles_fts (
                article_id, title, abstract_text, source, primary_category,
                categories, cluster_id, doi, venue, publish_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "MACE: A Hybrid LLM Serving System", "Edge inference and fine tuning.", "arxiv", "", "", "", "", "", ""),
                (2, "Efficient Serving Systems", "A general LLM inference survey.", "arxiv", "", "", "", "", "", ""),
            ],
        )

    articles = {
        1: Article(id=1, source="arxiv", external_id="mace", title="MACE: A Hybrid LLM Serving System"),
        2: Article(id=2, source="arxiv", external_id="other", title="Efficient Serving Systems"),
    }

    class FakeQuery:
        def filter(self, *args):
            return self

        def all(self):
            return list(articles.values())

    class FakeDb:
        def query(self, *args):
            return FakeQuery()

    results = BM25Retriever(FakeDb(), index_path=index_path).search("MACE LLM", RetrievalFilters(), limit=2)

    assert [candidate.article.id for candidate in results][:1] == [1]
    assert results[0].bm25_rank == 1
    assert results[0].bm25_score is not None


def test_bm25_retriever_missing_index_returns_empty(tmp_path):
    class FakeDb:
        pass

    results = BM25Retriever(FakeDb(), index_path=tmp_path / "missing.sqlite").search(
        "MACE LLM",
        RetrievalFilters(),
        limit=2,
    )

    assert results == []


def test_bm25_index_status_detects_stale_metadata(tmp_path, monkeypatch):
    index_path = tmp_path / "articles_bm25.sqlite"
    with sqlite3.connect(index_path) as conn:
        conn.execute("CREATE TABLE index_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO index_metadata(key, value) VALUES (?, ?)",
            ("source_db_fingerprint", "articles:1:embedded:1:max_id:1"),
        )

    monkeypatch.setattr(
        retrieval_service_module,
        "_source_db_fingerprint",
        lambda db: "articles:2:embedded:2:max_id:2",
    )

    assert check_bm25_index_status(object(), index_path) == "stale"


def test_bm25_index_status_reports_missing(tmp_path):
    assert check_bm25_index_status(object(), tmp_path / "missing.sqlite") == "missing"
