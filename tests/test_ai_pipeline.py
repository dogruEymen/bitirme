from datetime import UTC, datetime
from types import SimpleNamespace

from ai_engine.clustering.ClusterFunctions import Cluster
from ai_engine.data_hygiene import (
    build_embedding_text,
    build_representation_text,
    clean_paper_records,
    get_category_family,
    light_clean_text,
    normalize_title_for_dedup,
)
from ai_engine.ingestion.extractors.openalex_extractor import OpenAlexExtractor
from ai_engine.ingestion.loader import _article_to_row, _dedupe_rows_by_external_id, _is_computer_science_article
from ai_engine.ingestion.schemas import RawArticleSchema
from backend.app.services.digest_service import DigestService
from backend.app.services.embedding_service import EmbeddingService
from database.models.ArticleData import Article


def test_ingestion_normalizes_explicit_columns_and_metadata_json():
    article = RawArticleSchema(
        source="arxiv",
        external_id="1234.5678",
        title="A RAG Paper",
        abstract_text="Abstract",
        publish_date=datetime(2026, 5, 1, tzinfo=UTC),
        updated_date=datetime(2026, 5, 2, tzinfo=UTC),
        authors="Alice, Bob",
        url="https://example.test/paper",
        pdf_url="https://example.test/paper.pdf",
        primary_category="cs.CL",
        categories="cs.CL, cs.AI",
        doi="10.1234/rag",
        citation_count=7,
        venue="ExampleConf",
        metadata_json={"source_payload_version": "v1", "arxiv_comment": "12 pages"},
    )

    row = _article_to_row(article, ingestion_run_id="run-1")

    assert row["source"] == "arxiv"
    assert row["external_id"] == "1234.5678"
    assert row["doi"] == "10.1234/rag"
    assert row["citation_count"] == 7
    assert row["ingestion_run_id"] == "run-1"
    assert row["metadata_json"]["authors_list"] == ["Alice", "Bob"]
    assert row["metadata_json"]["categories_list"] == ["cs.CL", "cs.AI"]
    assert row["metadata_json"]["has_pdf"] is True
    assert row["metadata_json"]["publish_year"] == 2026
    assert row["metadata_json"]["publish_month"] == 5
    assert row["metadata_json"]["arxiv_comment"] == "12 pages"


def test_ingestion_accepts_only_computer_science_articles():
    cs_article = RawArticleSchema(
        source="arxiv",
        external_id="1234.5678",
        title="A CS Paper",
        primary_category="cs.CL",
        categories="cs.CL, cs.AI",
    )
    openalex_cs_article = RawArticleSchema(
        source="openalex",
        external_id="W1",
        title="An OpenAlex CS Paper",
        metadata_json={"is_computer_science": True},
    )
    non_cs_article = RawArticleSchema(
        source="arxiv",
        external_id="9876.5432",
        title="A Physics Paper",
        primary_category="physics.optics",
        categories="physics.optics",
    )

    assert _is_computer_science_article(cs_article) is True
    assert _is_computer_science_article(openalex_cs_article) is True
    assert _is_computer_science_article(non_cs_article) is False


def test_ingestion_deduplicates_rows_by_external_id_before_upsert():
    rows = [
        {"external_id": "1234.5678", "title": "Older"},
        {"external_id": "9876.5432", "title": "Other"},
        {"external_id": "1234.5678", "title": "Newer"},
    ]

    deduped = _dedupe_rows_by_external_id(rows)

    assert deduped == [
        {"external_id": "1234.5678", "title": "Newer"},
        {"external_id": "9876.5432", "title": "Other"},
    ]


def test_openalex_fetch_url_filters_computer_science_and_publication_date():
    extractor = OpenAlexExtractor()

    url = extractor._build_works_url("retrieval augmented generation", "cursor with spaces", 200)

    assert "filter=concepts.id%3AC41008148%2Cfrom_publication_date%3A2000-01-01" in url
    assert "search=retrieval+augmented+generation" in url
    assert "cursor=cursor+with+spaces" in url


def test_openalex_rejects_publications_before_2000():
    extractor = OpenAlexExtractor()

    assert extractor._is_supported_publication_date(datetime(2000, 1, 1)) is True
    assert extractor._is_supported_publication_date(datetime(1999, 12, 31)) is False


def test_embedding_text_is_deterministic_and_hash_changes_with_metadata():
    text = EmbeddingService.document_text(
        title="A RAG Paper",
        abstract="Abstract",
        source="arxiv",
        venue="ExampleConf",
        primary_category="cs.CL",
        publish_date=datetime(2026, 5, 1),
    )
    changed_text = EmbeddingService.document_text(
        title="A RAG Paper",
        abstract="Abstract",
        source="openalex",
        venue="ExampleConf",
        primary_category="cs.CL",
        publish_date=datetime(2026, 5, 1),
    )

    assert text == "A RAG Paper. A RAG Paper. Abstract"
    assert EmbeddingService.text_hash(text) == EmbeddingService.text_hash(text)
    assert EmbeddingService.text_hash(text) == EmbeddingService.text_hash(changed_text)


def test_data_hygiene_prepares_embedding_and_representation_texts():
    abstract = (
        "In this paper, we propose a $\\alpha$ method for retrieval augmented generation. "
        "Our results show strong improvements over baselines with extensive experiments."
    )

    assert normalize_title_for_dedup(" A&nbsp;RAG: Paper! ") == "a rag paper"
    assert light_clean_text("A $\\alpha$ {test}\n paper") == "A test paper"
    assert build_embedding_text("RAG Survey", abstract).startswith("RAG Survey. RAG Survey.")
    assert "we propose" not in build_representation_text("RAG Survey", abstract)
    assert get_category_family("cs.CL") == "cs"
    assert get_category_family("quant-ph") == "physics"


def test_data_hygiene_filters_short_duplicates_and_marks_surveys():
    long_abstract = " ".join(["retrieval"] * 120)
    result = clean_paper_records(
        [
            {
                "source": "arxiv",
                "external_id": "1",
                "title": "A Reliable RAG Survey",
                "abstract": long_abstract,
                "primary_category": "cs.CL",
                "categories": "cs.CL",
                "lang": "en",
            },
            {
                "source": "arxiv",
                "external_id": "1",
                "title": "Duplicate by ID",
                "abstract": long_abstract,
                "primary_category": "cs.CL",
                "categories": "cs.CL",
                "lang": "en",
            },
            {
                "source": "arxiv",
                "external_id": "2",
                "title": "Tiny",
                "abstract": long_abstract,
                "primary_category": "cs.CL",
                "categories": "cs.CL",
                "lang": "en",
            },
            {
                "source": "arxiv",
                "external_id": "3",
                "title": "Non English Paper",
                "abstract": long_abstract,
                "primary_category": "cs.CL",
                "categories": "cs.CL",
                "lang": "tr",
            },
        ]
    )

    assert len(result.clean_records) == 1
    assert result.clean_records[0]["is_survey"] is True
    assert result.clean_records[0]["category_family"] == "cs"
    assert result.clean_records[0]["embedding_text"]
    assert result.clean_records[0]["representation_text"]
    assert [record["duplicate_reason"] for record in result.duplicate_records] == ["duplicate_arxiv_id"]
    assert {record["removal_reason"] for record in result.removed_records} == {
        "title_too_short_or_empty",
        "non_english_or_unknown_language",
    }


def test_cluster_representatives_are_centroid_ranked_and_metadata_contains_scores():
    articles = [
        SimpleNamespace(id=1, embedding=[1.0, 0.0], primary_category="cs.CL", categories=None, source="arxiv", publish_date=datetime(2026, 5, 1)),
        SimpleNamespace(id=2, embedding=[0.9, 0.1], primary_category="cs.CL", categories=None, source="arxiv", publish_date=datetime(2026, 5, 2)),
        SimpleNamespace(id=3, embedding=[0.0, 1.0], primary_category="cs.AI", categories=None, source="openalex", publish_date=datetime(2026, 5, 3)),
    ]

    representatives = Cluster._representative_article_ids(articles)
    scores = Cluster._representative_article_scores(articles)
    metadata = Cluster._cluster_metadata(["rag", "retrieval"], articles, representatives, scores)

    assert representatives[0] == 2
    assert metadata["representative_article_ids"] == representatives
    assert str(representatives[0]) in metadata["representative_article_scores"]
    assert metadata["source_distribution"] == {"arxiv": 2, "openalex": 1}


def test_cluster_scope_defaults_to_arxiv_computer_science_categories():
    arxiv_cs = SimpleNamespace(source="arxiv", primary_category="cs.CL", categories="cs.CL, cs.AI")
    arxiv_cs_from_categories = SimpleNamespace(source="arxiv", primary_category=None, categories="math.CO, cs.DS")
    arxiv_math = SimpleNamespace(source="arxiv", primary_category="math.CO", categories="math.CO")
    arxiv_missing_category = SimpleNamespace(source="arxiv", primary_category=None, categories=None)
    openalex_free_text = SimpleNamespace(
        source="openalex",
        primary_category="Natural Language Processing Techniques",
        categories="Computer science, Machine learning",
        metadata_json={"is_computer_science": True},
    )

    assert Cluster._article_in_clustering_scope(arxiv_cs) is True
    assert Cluster._article_in_clustering_scope(arxiv_cs_from_categories) is True
    assert Cluster._article_in_clustering_scope(arxiv_math) is False
    assert Cluster._article_in_clustering_scope(arxiv_missing_category) is False
    assert Cluster._article_in_clustering_scope(openalex_free_text) is False
    assert Cluster._article_in_clustering_scope(openalex_free_text, include_openalex=True) is True


def test_cluster_keyword_quality_rejects_stopword_dominated_topics():
    stopword_keywords = ["the", "of", "and", "to", "in", "is", "for", "we", "that", "this"]
    mixed_keywords = ["retrieval", "augmented generation", "language model", "the", "of"]

    assert Cluster._valid_cluster_keywords(stopword_keywords) is False
    assert Cluster._valid_cluster_keywords(mixed_keywords) is True
    assert Cluster._clean_keywords(stopword_keywords) == []
    assert Cluster._clean_keywords(mixed_keywords) == [
        "retrieval",
        "augmented generation",
        "language model",
    ]


def test_cluster_topic_model_uses_stopword_vectorizer_ctfidf_and_clustering_params():
    topic_model = Cluster._build_topic_model(min_topic_size=50)

    assert topic_model.min_topic_size == 50
    assert topic_model.nr_topics is None
    assert "paper" in topic_model.vectorizer_model.get_params()["stop_words"]
    assert topic_model.vectorizer_model.get_params()["ngram_range"] == (1, 2)
    assert topic_model.vectorizer_model.get_params()["min_df"] == 2
    assert topic_model.vectorizer_model.get_params()["max_df"] == 1.0
    assert topic_model.ctfidf_model.reduce_frequent_words is True
    assert topic_model.umap_model.n_neighbors == 10
    assert topic_model.hdbscan_model.min_cluster_size == 50
    assert topic_model.hdbscan_model.min_samples == 1


def test_digest_score_uses_centrality_recency_and_citation_count():
    older = Article(id=1, title="Older", citation_count=100, publish_date=datetime(2025, 1, 1))
    newer = Article(id=2, title="Newer", citation_count=5, publish_date=datetime(2026, 1, 1))
    central = Article(id=3, title="Central", citation_count=1, publish_date=datetime(2024, 1, 1))
    centrality_scores = {central.id: 0.95, newer.id: 0.5, older.id: 0.1}

    ranked = sorted(
        [older, newer, central],
        key=lambda article: DigestService._article_digest_score(article, centrality_scores),
        reverse=True,
    )
    payload = DigestService._article_digest_score_payload(central, centrality_scores)

    assert ranked[0].id == central.id
    assert ranked[1].id == newer.id
    assert payload["centrality"] == 0.95
    assert payload["citation"] > 0
