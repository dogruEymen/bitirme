import asyncio
import json
import math
from types import SimpleNamespace

import pytest

from backend.app.evaluation.clustering_metrics import evaluate_clustering_records
from backend.app.evaluation.report_writer import write_evaluation_report
from backend.app.evaluation.retrieval_metrics import (
    evaluate_retrieval_questions,
    load_golden_questions,
    score_retrieval,
    summarize_retrieval_results,
)
from backend.app.evaluation.schemas import GoldenQuestion
from backend.app.schemas.retrieval import RetrievedArticle
from backend.app.schemas.source import SourceReference
from scripts.run_evaluation import main as run_evaluation_main


def test_retrieval_metric_math_and_duplicate_deduplication():
    scores = score_retrieval(
        expected_article_ids=[1, 2],
        retrieved_article_ids=[3, 1, 1, 2],
        top_k=3,
    )

    expected_dcg = (1 / math.log2(2 + 1)) + (1 / math.log2(3 + 1))
    expected_idcg = (1 / math.log2(1 + 1)) + (1 / math.log2(2 + 1))

    assert scores["retrieved_article_ids"] == [3, 1, 2]
    assert scores["hit_at_k"] is True
    assert scores["recall_at_k"] == 1.0
    assert scores["precision_at_k"] == pytest.approx(2 / 3)
    assert scores["mrr"] == pytest.approx(1 / 2)
    assert scores["ndcg_at_k"] == pytest.approx(expected_dcg / expected_idcg)


def test_empty_expected_set_raises_validation_error():
    with pytest.raises(ValueError, match="expected_article_ids"):
        GoldenQuestion(id="bad", question="paper?", expected_article_ids=[])

    with pytest.raises(ValueError, match="expected_article_ids"):
        score_retrieval([], [1], top_k=5)


def test_clustering_evaluator_skips_when_fewer_than_two_clusters():
    result = evaluate_clustering_records(
        [
            SimpleNamespace(embedding=[1.0, 0.0], cluster_id=1),
            SimpleNamespace(embedding=[0.9, 0.1], cluster_id=1),
        ]
    )

    assert result.cluster_count == 1
    assert result.cluster_assignment_coverage == 1.0
    assert result.silhouette_score is None
    assert result.skipped_reason == "At least two non-outlier clusters are required."


def test_clustering_outlier_ratio_handles_minus_one_label():
    result = evaluate_clustering_records(
        [
            SimpleNamespace(embedding=[1.0, 0.0], cluster_id=1),
            SimpleNamespace(embedding=[0.9, 0.1], cluster_id=1),
            SimpleNamespace(embedding=[0.0, 1.0], cluster_id=2),
            SimpleNamespace(embedding=[0.1, 0.9], cluster_id=2),
            SimpleNamespace(embedding=[0.5, 0.5], cluster_id=-1),
        ],
        pairwise_sample_limit=10,
    )

    assert result.outlier_count == 1
    assert result.clustered_article_count == 4
    assert result.cluster_count == 2
    assert result.outlier_ratio == pytest.approx(0.2)
    assert result.cluster_assignment_coverage == pytest.approx(0.8)
    assert result.avg_intra_cluster_cosine_similarity is not None
    assert result.avg_centroid_similarity is not None


def test_retrieval_evaluator_scores_fake_retrieval_service():
    question = GoldenQuestion(
        id="q1",
        question="Find papers about RAG",
        expected_article_ids=[10],
        top_k=3,
    )

    class FakeEmbeddingService:
        def embed_query(self, query: str):
            assert query
            return [0.1, 0.2]

    class FakeRetrievalService:
        def retrieve(self, query_embedding, filters, top_k, sort_by, query_text):
            assert query_embedding == [0.1, 0.2]
            assert query_text == "Find papers about RAG"
            assert top_k == 3
            assert sort_by == "relevance"
            return [
                _retrieved_article(30),
                _retrieved_article(10),
                _retrieved_article(10),
            ]

    results = asyncio.run(
        evaluate_retrieval_questions(
            db=SimpleNamespace(),
            questions=[question],
            top_k=5,
            embedding_service=FakeEmbeddingService(),
            retrieval_service=FakeRetrievalService(),
        )
    )

    assert len(results) == 1
    assert results[0].retrieved_article_ids == [30, 10]
    assert results[0].hit_at_k is True
    assert results[0].mrr == pytest.approx(0.5)
    assert results[0].uses_rag is True
    assert results[0].source_count == 3
    assert results[0].rewritten_query == "Find papers about RAG"
    assert results[0].sort_by == "relevance"


def test_retrieval_evaluator_can_force_rag_for_router_isolation():
    question = GoldenQuestion(
        id="q1",
        question="Explain this without retrieval",
        expected_article_ids=[10],
        top_k=1,
    )

    class FakeEmbeddingService:
        def embed_query(self, query: str):
            return [0.1, 0.2]

    class FakeRetrievalService:
        def retrieve(self, query_embedding, filters, top_k, sort_by, query_text):
            assert query_text == "Explain this without retrieval"
            return [_retrieved_article(10)]

    results = asyncio.run(
        evaluate_retrieval_questions(
            db=SimpleNamespace(),
            questions=[question],
            top_k=1,
            embedding_service=FakeEmbeddingService(),
            retrieval_service=FakeRetrievalService(),
            force_rag=True,
        )
    )

    assert results[0].uses_rag is True
    assert results[0].hit_at_k is True
    assert "Forced RAG" in results[0].route_reason


def test_retrieval_evaluator_can_disable_keyword_branch():
    question = GoldenQuestion(
        id="q1",
        question="Find papers about dense retrieval",
        expected_article_ids=[10],
        top_k=1,
    )

    class FakeEmbeddingService:
        def embed_query(self, query: str):
            return [0.1, 0.2]

    class FakeRetrievalService:
        def retrieve(self, query_embedding, filters, top_k, sort_by, query_text):
            assert query_text is None
            return [_retrieved_article(10)]

    results = asyncio.run(
        evaluate_retrieval_questions(
            db=SimpleNamespace(),
            questions=[question],
            top_k=1,
            embedding_service=FakeEmbeddingService(),
            retrieval_service=FakeRetrievalService(),
            force_rag=True,
            use_keyword=False,
        )
    )

    assert results[0].hit_at_k is True


def test_report_writer_creates_summary_json_and_retrieval_csv(tmp_path):
    result = asyncio.run(
        evaluate_retrieval_questions(
            db=SimpleNamespace(),
            questions=[
                GoldenQuestion(
                    id="q1",
                    question="Find papers about RAG",
                    expected_article_ids=[10],
                    top_k=2,
                )
            ],
            top_k=2,
            embedding_service=SimpleNamespace(embed_query=lambda query: [0.1, 0.2]),
            retrieval_service=SimpleNamespace(
                retrieve=lambda query_embedding, filters, top_k, sort_by, query_text: [_retrieved_article(10)]
            ),
        )
    )
    summary = summarize_retrieval_results(result)

    run_dir = write_evaluation_report(
        output_root=tmp_path,
        run_id="test-run",
        suite="retrieval",
        retrieval_results=result,
        retrieval_summary=summary,
    )

    assert (run_dir / "summary.json").exists()
    assert (run_dir / "retrieval_results.csv").exists()
    csv_text = (run_dir / "retrieval_results.csv").read_text(encoding="utf-8")
    assert "rewritten_query" in csv_text
    assert "filters" in csv_text
    payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert payload["retrieval"]["summary"]["question_count"] == 1


def test_load_golden_questions_rejects_malformed_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed golden questions JSON"):
        load_golden_questions(path)

    assert run_evaluation_main(["--suite", "retrieval", "--golden-file", str(path)]) == 2


def _retrieved_article(article_id: int) -> RetrievedArticle:
    return RetrievedArticle(
        source=SourceReference(
            source_id=f"S{article_id}",
            article_id=article_id,
            title=f"Paper {article_id}",
        ),
        abstract_text="Abstract",
    )
