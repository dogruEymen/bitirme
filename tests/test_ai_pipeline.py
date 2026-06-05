import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from ai_engine.clustering.ClusterFunctions import Cluster
from ai_engine.data_hygiene import (
    build_embedding_text,
    build_representation_text,
    clean_paper_records,
    get_category_family,
    light_clean_text,
    normalize_title_for_dedup,
)
from ai_engine.ingestion.extractors.arxiv_extractor import ArxivExtractor
from ai_engine.ingestion.extractors.openalex_extractor import OpenAlexExtractor
from ai_engine.ingestion.loader import (
    _article_to_row,
    _articles_to_insert_rows,
    _dedupe_rows_by_external_id,
    _is_computer_science_article,
)
from ai_engine.ingestion.schemas import RawArticleSchema
from backend.app.services.digest_service import DigestService
from backend.app.services import embedding_service as embedding_service_module
from backend.app.services.embedding_service import EmbeddingService, resolve_embedding_device
from database.models.ArticleData import Article
from run_kaggle_arxiv_ingest import _sampling_candidate, kaggle_record_to_article, sample_kaggle_articles


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


def test_ingestion_skips_articles_without_abstract_text():
    missing_abstract = RawArticleSchema(
        source="arxiv",
        external_id="1234.5678",
        title="A CS Paper",
        abstract_text="   ",
        primary_category="cs.CL",
        categories="cs.CL",
    )
    with_abstract = RawArticleSchema(
        source="arxiv",
        external_id="9876.5432",
        title="Another CS Paper",
        abstract_text="This paper has an abstract.",
        primary_category="cs.AI",
        categories="cs.AI",
    )

    rows = _articles_to_insert_rows([missing_abstract, with_abstract], ingestion_run_id="run-1")

    assert [row["external_id"] for row in rows] == ["9876.5432"]


def test_ingestion_skips_arxiv_articles_without_cs_category_prefix():
    non_cs_article = RawArticleSchema(
        source="arxiv",
        external_id="9876.5432",
        title="A Physics Paper",
        abstract_text="This paper has an abstract.",
        primary_category="physics.optics",
        categories="physics.optics",
        metadata_json={"is_computer_science": True},
    )

    rows = _articles_to_insert_rows([non_cs_article], ingestion_run_id="run-1")

    assert rows == []


def test_kaggle_arxiv_record_maps_to_existing_ingestion_schema():
    record = {
        "id": "2401.00001",
        "submitter": "Alice Example",
        "authors": "Alice Example, Bob Example",
        "title": "A Kaggle Snapshot Paper\nwith Whitespace",
        "comments": "10 pages",
        "journal-ref": "ExampleConf 2024",
        "doi": "10.1234/example",
        "categories": "cs.CL cs.AI math.CO",
        "license": "http://creativecommons.org/licenses/by/4.0/",
        "abstract": "  This paper has an abstract.  ",
        "versions": [{"version": "v1", "created": "Mon, 1 Jan 2024 12:00:00 GMT"}],
        "update_date": "2024-01-02",
        "authors_parsed": [["Example", "Alice", ""], ["Example", "Bob", ""]],
    }

    article = kaggle_record_to_article(record)
    rows = _articles_to_insert_rows([article], ingestion_run_id="run-1")

    assert article.external_id == "2401.00001"
    assert article.title == "A Kaggle Snapshot Paper with Whitespace"
    assert article.primary_category == "cs.CL"
    assert article.categories == "cs.CL, cs.AI, math.CO"
    assert article.publish_date == datetime(2024, 1, 1, 12, 0, 0)
    assert rows[0]["external_id"] == "2401.00001"
    assert rows[0]["metadata_json"]["arxiv_categories"] == ["cs.CL", "cs.AI", "math.CO"]


def test_kaggle_sampling_candidate_rejects_missing_doi_and_pdf():
    article = RawArticleSchema(
        source="arxiv",
        external_id="2401.00001",
        title="A CS Paper",
        abstract_text="Abstract",
        publish_date=datetime(2024, 1, 1),
        primary_category="cs.CL",
        categories="cs.CL",
        doi=None,
        pdf_url=None,
    )

    accepted, month = _sampling_candidate(article, start_year=2016, end_year=2026)

    assert accepted is False
    assert month is None


def test_kaggle_sampling_selects_at_most_requested_records_per_month(tmp_path):
    input_path = tmp_path / "arxiv.json"
    records = [
        {
            "id": f"2401.0000{idx}",
            "title": f"Paper {idx}",
            "abstract": "Abstract",
            "categories": "cs.CL",
            "versions": [{"created": "Mon, 1 Jan 2024 12:00:00 GMT"}],
        }
        for idx in range(5)
    ]
    input_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    selected, stats = sample_kaggle_articles(
        input_path,
        samples_per_month=2,
        start_year=2024,
        end_year=2024,
        random_seed=7,
    )

    assert len(selected) == 2
    assert stats["eligible_count"] == 5
    assert stats["month_counts"]["2024-01"] == 2


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


def test_arxiv_cursor_defaults_to_current_month_when_state_is_old_format(monkeypatch):
    monkeypatch.setattr(
        "ai_engine.ingestion.extractors.arxiv_extractor.load_state",
        lambda source: {"current_date": "2017-11-01", "start_offset": 2000},
    )

    current_dt, current_start = ArxivExtractor()._initial_cursor()
    now = datetime.now(UTC)

    assert current_dt == datetime(now.year, now.month, 1)
    assert current_start == 0


def test_arxiv_cursor_resumes_backward_checkpoint(monkeypatch):
    monkeypatch.setattr(
        "ai_engine.ingestion.extractors.arxiv_extractor.load_state",
        lambda source: {
            "current_date": "2026-05-01",
            "start_offset": 500,
            "cursor_direction": "backward",
        },
    )

    current_dt, current_start = ArxivExtractor()._initial_cursor()

    assert current_dt == datetime(2026, 5, 1)
    assert current_start == 500


def test_arxiv_month_cursor_moves_backward():
    extractor = ArxivExtractor()

    assert extractor._previous_month(datetime(2026, 5, 1)) == datetime(2026, 4, 1)
    assert extractor._previous_month(datetime(2026, 1, 1)) == datetime(2025, 12, 1)


def test_arxiv_monthly_request_size_stops_at_offset_limit():
    extractor = ArxivExtractor()

    assert extractor._monthly_request_size(fetched_count=0, max_results=10000, current_start=0) == 500
    assert extractor._monthly_request_size(fetched_count=0, max_results=10000, current_start=2990) == 10
    assert extractor._monthly_request_size(fetched_count=0, max_results=10000, current_start=3000) == 0


def test_arxiv_request_wait_seconds_enforces_three_second_interval():
    extractor = ArxivExtractor()

    assert extractor._request_wait_seconds(now_monotonic=100.0) == 0.0

    extractor._last_request_monotonic = 100.0

    assert extractor._request_wait_seconds(now_monotonic=101.0) == 2.0
    assert extractor._request_wait_seconds(now_monotonic=103.0) == 0.0


def test_arxiv_retry_delay_uses_retry_after_header():
    extractor = ArxivExtractor()
    response = httpx.Response(429, headers={"Retry-After": "240"})

    assert extractor._retry_delay(attempt=1, response=response) == 240


def test_arxiv_rate_limit_details_include_headers_and_body_excerpt():
    extractor = ArxivExtractor()
    response = httpx.Response(
        429,
        headers={"Retry-After": "240", "X-RateLimit-Limit": "1200"},
        text="Too many requests. Try again later.",
    )

    details = extractor._rate_limit_details(response)

    assert details["Retry-After"] == "240"
    assert details["X-RateLimit-Limit"] == "1200"
    assert details["body_excerpt"] == "Too many requests. Try again later."


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


def test_embedding_device_auto_prefers_mps_when_cuda_is_missing(monkeypatch):
    monkeypatch.setattr(embedding_service_module.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(embedding_service_module, "_mps_is_available", lambda: True)

    assert resolve_embedding_device("auto") == "mps"


def test_embedding_device_auto_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(embedding_service_module.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(embedding_service_module, "_mps_is_available", lambda: False)

    assert resolve_embedding_device("auto") == "cpu"


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


def test_cluster_topic_model_uses_stopword_vectorizer_ctfidf_and_clustering_params(monkeypatch):
    monkeypatch.delenv("CLUSTERING_HDBSCAN_JOBS", raising=False)

    topic_model = Cluster._build_topic_model(
        min_topic_size=50,
        hardware_profile="m4-pro-24gb",
        threads=8,
    )

    assert topic_model.min_topic_size == 50
    assert topic_model.nr_topics is None
    assert "paper" in topic_model.vectorizer_model.get_params()["stop_words"]
    assert topic_model.vectorizer_model.get_params()["ngram_range"] == (1, 2)
    assert topic_model.vectorizer_model.get_params()["min_df"] == 2
    assert topic_model.vectorizer_model.get_params()["max_df"] == 1.0
    assert topic_model.ctfidf_model.reduce_frequent_words is True
    assert topic_model.umap_model.n_neighbors == 10
    assert topic_model.umap_model.low_memory is True
    assert topic_model.hdbscan_model.min_cluster_size == 50
    assert topic_model.hdbscan_model.min_samples == 1
    assert topic_model.hdbscan_model.core_dist_n_jobs == 6


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
