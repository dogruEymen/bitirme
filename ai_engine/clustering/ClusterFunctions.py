import argparse
import contextlib
import csv
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass


@dataclass(frozen=True)
class ClusteringRuntimeProfile:
    name: str
    thread_count: int
    hdbscan_jobs: int
    low_memory: bool


def _system_memory_gb() -> float | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    return (pages * page_size) / (1024**3)


def _bounded_thread_count(default: int, requested: int | None = None) -> int:
    cpu_count = os.cpu_count() or default
    value = requested or default
    return max(1, min(value, cpu_count))


def _env_int(name: str) -> int | None:
    raw_value = os.getenv(name)
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def resolve_runtime_profile(
    hardware_profile: str | None = None,
    threads: int | None = None,
) -> ClusteringRuntimeProfile:
    profile_name = (hardware_profile or os.getenv("CLUSTERING_HARDWARE_PROFILE") or "auto").strip().lower()
    requested_threads = threads or _env_int("CLUSTERING_THREADS")

    if profile_name == "auto":
        is_apple_silicon = platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}
        memory_gb = _system_memory_gb()
        if is_apple_silicon and (memory_gb is None or 20 <= memory_gb <= 36):
            profile_name = "m4-pro-24gb"
        else:
            profile_name = "balanced"

    if profile_name in {"m4", "m4-pro", "m4-pro-24gb", "apple-silicon-24gb"}:
        thread_count = _bounded_thread_count(default=8, requested=requested_threads)
        return ClusteringRuntimeProfile(
            name="m4-pro-24gb",
            thread_count=thread_count,
            hdbscan_jobs=_bounded_thread_count(default=6, requested=_env_int("CLUSTERING_HDBSCAN_JOBS")),
            low_memory=_env_bool("CLUSTERING_LOW_MEMORY", True),
        )

    if profile_name in {"memory-saver", "memory_saver"}:
        thread_count = _bounded_thread_count(default=4, requested=requested_threads)
        return ClusteringRuntimeProfile(
            name="memory-saver",
            thread_count=thread_count,
            hdbscan_jobs=_bounded_thread_count(default=2, requested=_env_int("CLUSTERING_HDBSCAN_JOBS")),
            low_memory=True,
        )

    if profile_name == "balanced":
        thread_count = _bounded_thread_count(default=6, requested=requested_threads)
        return ClusteringRuntimeProfile(
            name="balanced",
            thread_count=thread_count,
            hdbscan_jobs=_bounded_thread_count(default=4, requested=_env_int("CLUSTERING_HDBSCAN_JOBS")),
            low_memory=_env_bool("CLUSTERING_LOW_MEMORY", True),
        )

    raise ValueError(
        "Unsupported clustering hardware profile "
        f"'{profile_name}'. Use one of: auto, m4-pro-24gb, balanced, memory-saver."
    )


def _apply_import_time_thread_limits():
    profile = resolve_runtime_profile()
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ.setdefault(variable, str(profile.thread_count))


_apply_import_time_thread_limits()

from backend.app.services.ollama_service import get_ollama_service
import numpy as np
from bertopic import BERTopic
from bertopic.vectorizers import ClassTfidfTransformer
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
from sqlalchemy import and_, or_
from umap import UMAP
from ai_engine.data_hygiene import build_representation_text, valid_title_and_abstract
from database.models.ClusterData import Cluster as ClusterModel
from database.models.ArticleData import Article
from database.db import SessionLocal
from datetime import UTC, datetime
from collections import Counter

try:
    from threadpoolctl import threadpool_limits
except Exception:
    threadpool_limits = None

DEFAULT_CLEAN_PAPER_CSVS = [
    PROJECT_ROOT / "exports/data_hygiene/clean_papers.csv",
    PROJECT_ROOT / "exports/data_hygiene_openalex/clean_papers.csv",
]
DEFAULT_BERTOPIC_OUTPUT_DIR = PROJECT_ROOT / "exports/bertopic"
CUSTOM_ACADEMIC_STOPWORDS = {
    "paper",
    "study",
    "approach",
    "method",
    "methods",
    "result",
    "results",
    "show",
    "shows",
    "shown",
    "propose",
    "proposed",
    "present",
    "presented",
    "using",
    "use",
    "used",
    "based",
    "problem",
    "task",
    "performance",
    "new",
    "novel",
    "work",
    "framework",
    "experiments",
    "experimental",
    "analysis",
    "demonstrate",
    "demonstrates",
    "significant",
    "effective",
    "efficient",
}
GENERIC_RESEARCH_KEYWORDS = CUSTOM_ACADEMIC_STOPWORDS.union(
    {
        "model",
        "models",
        "data",
        "dataset",
        "datasets",
        "learning",
        "algorithm",
        "algorithms",
    }
)


class Cluster:
    top_representative_count = 10
    stop_words = set(ENGLISH_STOP_WORDS).union(CUSTOM_ACADEMIC_STOPWORDS)

    @staticmethod
    def cluster(
        max_articles: int | None = None,
        min_topic_size: int = 10,
        include_openalex: bool = False,
        clean_papers_csv: list[Path] | None = None,
        raw_db: bool = False,
        output_dir: Path | None = DEFAULT_BERTOPIC_OUTPUT_DIR,
        save_model: bool = True,
        save_database: bool = True,
        run_experiments: bool = False,
        hardware_profile: str | None = None,
        threads: int | None = None,
    ):
        runtime_profile = resolve_runtime_profile(hardware_profile=hardware_profile, threads=threads)
        print("=== RUNTIME PROFILE ===")
        print(
            "Hardware profile: "
            f"{runtime_profile.name}, threads={runtime_profile.thread_count}, "
            f"hdbscan_jobs={runtime_profile.hdbscan_jobs}, low_memory={runtime_profile.low_memory}"
        )

        clean_csvs = [] if raw_db else (clean_papers_csv or Cluster._existing_clean_paper_csvs())
        if clean_csvs:
            clean_articles = Cluster._articles_from_clean_csvs(clean_csvs, max_articles=max_articles)
            print("=== DATA STATISTICS ===")
            print(f"Clean CSV files: {', '.join(str(path) for path in clean_csvs)}")
            print(f"Clean articles selected for clustering with matching embeddings: {len(clean_articles)}")
            print("OpenAlex included through clean CSV input")
        else:
            db = SessionLocal()
            try:
                cs_category_filter = or_(
                    Article.primary_category.ilike("cs.%"),
                    Article.categories.ilike("%cs.%"),
                )
                query = (
                    db.query(Article)
                    .filter(Article.embedding.isnot(None), Article.title.isnot(None), Article.abstract_text.isnot(None))
                    .order_by(Article.id.asc())
                )
                if include_openalex:
                    query = query.filter(
                        or_(
                            and_(Article.source == "arxiv", cs_category_filter),
                            Article.source == "openalex",
                        )
                    )
                else:
                    query = query.filter(Article.source == "arxiv", cs_category_filter)
                if max_articles is not None:
                    query = query.limit(max_articles)
                articles = query.all()
            finally:
                db.close()

            if not articles:
                raise Exception("No articles with embeddings found. Generate embeddings before clustering.")

            clean_articles = [
                a
                for a in articles
                if Cluster._valid_article_for_clustering(a)
                and Cluster._article_in_clustering_scope(a, include_openalex=include_openalex)
            ]

            print("=== DATA STATISTICS ===")
            print(f"Total articles with embeddings fetched: {len(articles)}")
            print(f"Clean CS articles selected for clustering: {len(clean_articles)}")
            print(f"Articles filtered out: {len(articles) - len(clean_articles)}")
            print(f"OpenAlex included: {include_openalex}")

        if not clean_articles:
            raise Exception("No clean articles found with matching embeddings. Generate embeddings from clean CSV first.")

        embeddings = np.array([Cluster._article_embedding(a) for a in clean_articles], dtype=np.float32)
        docs = np.array([Cluster._document_text(a) for a in clean_articles])

        print(f"Embeddings shape: {embeddings.shape}")

        experiment_results = []
        if run_experiments:
            print("\n=== BASELINE EXPERIMENT ===")
            baseline_model = Cluster._build_baseline_topic_model(
                min_topic_size=min_topic_size,
                runtime_profile=runtime_profile,
            )
            with Cluster._threadpool_limits(runtime_profile):
                baseline_topics, _ = baseline_model.fit_transform(docs, embeddings=embeddings)
            experiment_results.append(
                Cluster._evaluate_topic_model(baseline_model, baseline_topics, "baseline")
            )

        print("\n=== FINAL BERTOPIC RUN ===")
        topic_model = Cluster._build_topic_model(min_topic_size=min_topic_size, runtime_profile=runtime_profile)
        with Cluster._threadpool_limits(runtime_profile):
            topics, probs = topic_model.fit_transform(docs, embeddings=embeddings)
        experiment_results.append(
            Cluster._evaluate_topic_model(topic_model, topics, "custom_stopwords_ctfidf_umap_hdbscan")
        )
        
        # CLUSTERING RESULTS
        unique_topics = set(topics)
        outlier_count = list(topics).count(-1)
        clustered_count = len(topics) - outlier_count
        
        print("\n=== CLUSTERING RESULTS ===")
        print(f"Total documents processed: {len(topics)}")
        print(f"Number of clusters formed: {len(unique_topics) - (1 if -1 in unique_topics else 0)}")
        print(f"Documents assigned to clusters: {clustered_count}")
        print(f"Outliers (unassigned): {outlier_count}")
        print(f"Outlier percentage: {(outlier_count/len(topics))*100:.2f}%")
        
        print("\n=== TOPIC SUMMARY ===")
        topic_info = topic_model.get_topic_info()
        print(topic_info)

        if output_dir:
            Cluster._write_topic_outputs(
                output_dir=output_dir,
                articles=clean_articles,
                topic_model=topic_model,
                topics=topics,
                probs=probs,
                experiment_results=experiment_results,
                save_model=save_model,
            )

        if save_database:
            Cluster.save_to_database(clean_articles, topic_model, topics, probs)
    
    @staticmethod
    def save_to_database(clean_articles, topic_model, topics, probs):
        db = SessionLocal()
        try:
            db.query(ClusterModel).delete()
            db.query(Article).update({Article.cluster_id: None})

            topic_info = topic_model.get_topic_info()

            cluster_articles = {}
            for article, topic_id in zip(clean_articles, topics):
                if topic_id != -1:
                    cluster_articles.setdefault(int(topic_id), []).append(article)

            ollama = get_ollama_service()

            cluster_counts = {}
            for _, row in topic_info.iterrows():
                topic_id = int(row["Topic"])
                if topic_id == -1:
                    continue

                raw_keywords = Cluster._topic_keywords(row.get("Representation", []))
                if not Cluster._valid_cluster_keywords(raw_keywords):
                    print(
                        "Skipping topic "
                        f"{topic_id} because its keywords are dominated by stop words: {raw_keywords[:10]}"
                    )
                    continue

                keywords = Cluster._clean_keywords(raw_keywords)
                if not keywords:
                    print(f"Skipping topic {topic_id} because no usable keywords remained after cleaning.")
                    continue

                keywords_str = ", ".join(keywords)
                cluster_name = Cluster._generate_cluster_name(ollama, topic_id, keywords_str)

                articles_for_cluster = cluster_articles.get(topic_id, [])
                if not articles_for_cluster:
                    continue
                article_ids = [article.id for article in articles_for_cluster]
                representative_ids = Cluster._representative_article_ids(articles_for_cluster)
                representative_scores = Cluster._representative_article_scores(articles_for_cluster)
                metadata = Cluster._cluster_metadata(
                    keywords,
                    articles_for_cluster,
                    representative_ids,
                    representative_scores,
                )

                db.add(
                    ClusterModel(
                        cluster_id=topic_id,
                        cluster_description=cluster_name,
                        article_count=len(article_ids),
                        article_ids=",".join(map(str, article_ids)) if article_ids else None,
                        representative_docs=",".join(map(str, representative_ids)) if representative_ids else None,
                        metadata_json=metadata,
                    )
                )
                cluster_counts[topic_id] = len(article_ids)

            for article, topic_id in zip(clean_articles, topics):
                if topic_id != -1 and int(topic_id) in cluster_counts:
                    db.query(Article).filter(Article.id == article.id).update({Article.cluster_id: int(topic_id)})

            db.commit()
            updated_count = len([t for t in topics if t != -1 and int(t) in cluster_counts])
            skipped_count = len([t for t in set(topics) if t != -1 and int(t) not in cluster_counts])
            print(f"Saved {len(cluster_counts)} clusters and updated {updated_count} articles")
            print(f"Skipped {skipped_count} low-quality or empty topics")
            Cluster._refresh_report_snapshots(db)

        except Exception as e:
            db.rollback()
            print(f"Error saving to database: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def _valid_article_for_clustering(article) -> bool:
        return (
            isinstance(article.title, str)
            and bool(article.title.strip())
            and valid_title_and_abstract(article.title, article.abstract_text)
            and isinstance(article.embedding, (list, np.ndarray))
            and len(article.embedding) > 0
        )

    @staticmethod
    def _refresh_report_snapshots(db) -> None:
        try:
            from backend.app.services.report_snapshot_service import ReportSnapshotService

            refreshed = ReportSnapshotService(db).refresh_default_snapshots()
            print(
                "Refreshed report snapshots: "
                f"analytics={refreshed['analytics']}, bulletin={refreshed['bulletin']}"
            )
        except Exception as e:
            print(f"Report snapshot refresh failed after clustering commit: {e}")

    @staticmethod
    def _article_in_clustering_scope(article, include_openalex: bool = False) -> bool:
        source = (getattr(article, "source", None) or "").lower()
        if source == "arxiv":
            return Cluster._has_cs_category(article)
        if source == "openalex":
            return bool(include_openalex and (getattr(article, "metadata_json", {}) or {}).get("is_computer_science"))
        return False

    @staticmethod
    def _existing_clean_paper_csvs() -> list[Path]:
        return [path for path in DEFAULT_CLEAN_PAPER_CSVS if path.exists()]

    @staticmethod
    def _articles_from_clean_csvs(csv_paths: list[Path], max_articles: int | None = None) -> list[Article]:
        rows_by_id = {}
        for csv_path in csv_paths:
            with csv_path.open("r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    article_id = row.get("id")
                    if not article_id or article_id in rows_by_id:
                        continue
                    representation_text = row.get("representation_text")
                    embedding_text = row.get("embedding_text")
                    if not representation_text or not embedding_text:
                        continue
                    rows_by_id[int(article_id)] = row
                    if max_articles is not None and len(rows_by_id) >= max_articles:
                        break
            if max_articles is not None and len(rows_by_id) >= max_articles:
                break

        if not rows_by_id:
            return []

        db = SessionLocal()
        try:
            articles = db.query(Article).filter(Article.id.in_(rows_by_id.keys()), Article.embedding.isnot(None)).all()
            clean_articles = []
            skipped_stale_embeddings = 0
            for article in sorted(articles, key=lambda item: item.id):
                row = rows_by_id.get(article.id)
                expected_hash = row and Cluster._embedding_text_hash(row["embedding_text"])
                if article.embedding_text_hash != expected_hash:
                    skipped_stale_embeddings += 1
                    continue
                setattr(article, "_representation_text", row["representation_text"])
                clean_articles.append(article)
            if skipped_stale_embeddings:
                print(
                    "Skipped "
                    f"{skipped_stale_embeddings} clean CSV articles because their DB embeddings are missing or stale."
                )
            return clean_articles
        finally:
            db.close()

    @staticmethod
    def _embedding_text_hash(text: str) -> str:
        from backend.app.services.embedding_service import EmbeddingService

        return EmbeddingService.text_hash(text)

    @staticmethod
    def _has_cs_category(article) -> bool:
        category_values = [
            getattr(article, "primary_category", None),
            getattr(article, "categories", None),
        ]
        return any(
            isinstance(value, str) and re.search(r"(^|[\s,;])cs\.[A-Za-z]{2}\b", value)
            for value in category_values
        )

    @staticmethod
    def _build_topic_model(
        min_topic_size: int,
        runtime_profile: ClusteringRuntimeProfile | None = None,
        hardware_profile: str | None = None,
        threads: int | None = None,
    ) -> BERTopic:
        runtime_profile = runtime_profile or resolve_runtime_profile(
            hardware_profile=hardware_profile,
            threads=threads,
        )
        vectorizer_model = CountVectorizer(
            stop_words=sorted(Cluster.stop_words),
            ngram_range=(1, 2),
            min_df=2,
            max_df=1.0,
            dtype=np.int32,
        )
        ctfidf_model = ClassTfidfTransformer(
            reduce_frequent_words=True,
        )
        umap_model = UMAP(
            n_neighbors=10,
            n_components=5,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
            low_memory=runtime_profile.low_memory,
        )
        hdbscan_model = HDBSCAN(
            min_cluster_size=min_topic_size,
            min_samples=1,
            metric="euclidean",
            cluster_selection_method="eom",
            prediction_data=True,
            core_dist_n_jobs=runtime_profile.hdbscan_jobs,
        )
        return BERTopic(
            embedding_model=None,
            vectorizer_model=vectorizer_model,
            ctfidf_model=ctfidf_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            min_topic_size=min_topic_size,
            verbose=True,
            nr_topics=None,
        )

    @staticmethod
    def _build_baseline_topic_model(
        min_topic_size: int,
        runtime_profile: ClusteringRuntimeProfile | None = None,
        hardware_profile: str | None = None,
        threads: int | None = None,
    ) -> BERTopic:
        runtime_profile = runtime_profile or resolve_runtime_profile(
            hardware_profile=hardware_profile,
            threads=threads,
        )
        vectorizer_model = CountVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=2,
            dtype=np.int32,
        )
        topic_model = BERTopic(
            embedding_model=None,
            vectorizer_model=vectorizer_model,
            min_topic_size=min_topic_size,
            verbose=True,
            nr_topics=None,
        )
        if hasattr(topic_model.umap_model, "low_memory"):
            topic_model.umap_model.low_memory = runtime_profile.low_memory
        if hasattr(topic_model.hdbscan_model, "core_dist_n_jobs"):
            topic_model.hdbscan_model.core_dist_n_jobs = runtime_profile.hdbscan_jobs
        return topic_model

    @staticmethod
    def _threadpool_limits(runtime_profile: ClusteringRuntimeProfile):
        if threadpool_limits is None:
            return contextlib.nullcontext()
        return threadpool_limits(limits=runtime_profile.thread_count)

    @staticmethod
    def _evaluate_topic_model(topic_model, topics, run_name: str) -> dict:
        topic_info = topic_model.get_topic_info()
        total_docs = len(topics)
        outlier_count = sum(1 for topic in topics if topic == -1)
        outlier_ratio = outlier_count / total_docs if total_docs else 0.0
        non_outlier_info = topic_info[topic_info["Topic"] != -1]

        if len(non_outlier_info) > 0:
            largest_topic_size = int(non_outlier_info["Count"].max())
            largest_topic_ratio = largest_topic_size / total_docs if total_docs else 0.0
            num_topics = len(non_outlier_info)
        else:
            largest_topic_size = 0
            largest_topic_ratio = 0.0
            num_topics = 0

        return {
            "run_name": run_name,
            "total_docs": total_docs,
            "num_topics": num_topics,
            "outlier_count": outlier_count,
            "outlier_ratio": round(outlier_ratio, 6),
            "largest_topic_size": largest_topic_size,
            "largest_topic_ratio": round(largest_topic_ratio, 6),
        }

    @staticmethod
    def _write_topic_outputs(
        output_dir: Path,
        articles,
        topic_model,
        topics,
        probs,
        experiment_results: list[dict],
        save_model: bool = True,
    ):
        output_dir.mkdir(parents=True, exist_ok=True)

        topic_info = topic_model.get_topic_info()
        topic_info.to_csv(output_dir / "topic_info.csv", index=False)

        assignment_rows = []
        for index, (article, topic_id) in enumerate(zip(articles, topics)):
            probability = Cluster._topic_probability(probs, index, topic_id)
            assignment_rows.append(
                {
                    "article_id": getattr(article, "id", None),
                    "source": getattr(article, "source", None),
                    "external_id": getattr(article, "external_id", None),
                    "title": getattr(article, "title", None),
                    "abstract": getattr(article, "abstract_text", None),
                    "topic": int(topic_id),
                    "probability": probability,
                }
            )
        Cluster._write_dict_csv(output_dir / "paper_topic_assignments.csv", assignment_rows)

        keyword_rows = []
        for topic_id in sorted(set(int(topic) for topic in topics)):
            if topic_id == -1:
                continue
            keywords = topic_model.get_topic(topic_id)
            if not keywords:
                continue
            keyword_rows.append(
                {
                    "topic": topic_id,
                    "keywords": ", ".join(word for word, _ in keywords[:10]),
                }
            )
        Cluster._write_dict_csv(output_dir / "topic_keywords.csv", keyword_rows)
        Cluster._write_dict_csv(output_dir / "bertopic_experiment_results.csv", experiment_results)

        report = Cluster._build_experiment_report(experiment_results)
        (output_dir / "bertopic_cluster_iyilestirme_raporu.md").write_text(report, encoding="utf-8")

        if save_model:
            topic_model.save(str(output_dir / "bertopic_model"))

        print(f"\nSaved BERTopic outputs to {output_dir}")

    @staticmethod
    def _topic_probability(probs, index: int, topic_id: int) -> float | None:
        if probs is None:
            return None
        try:
            if np.ndim(probs) == 1:
                return round(float(probs[index]), 6)
            if topic_id == -1:
                return None
            return round(float(np.max(probs[index])), 6)
        except Exception:
            return None

    @staticmethod
    def _write_dict_csv(path: Path, rows: list[dict]):
        fieldnames = sorted({key for row in rows for key in row.keys()})
        with path.open("w", encoding="utf-8", newline="") as file:
            if not fieldnames:
                file.write("")
                return
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _build_experiment_report(results: list[dict]) -> str:
        baseline = next((row for row in results if row["run_name"] == "baseline"), None)
        final = results[-1] if results else {}
        baseline_value = lambda key: baseline.get(key, "not measured") if baseline else "not measured"
        final_value = lambda key: final.get(key, "not measured")
        return "\n".join(
            [
                "# BERTopic Cluster Iyilestirme Raporu",
                "",
                "## Ozet",
                "",
                f"- Baseline en buyuk topic orani: {baseline_value('largest_topic_ratio')}",
                f"- Final en buyuk topic orani: {final_value('largest_topic_ratio')}",
                f"- Baseline topic sayisi: {baseline_value('num_topics')}",
                f"- Final topic sayisi: {final_value('num_topics')}",
                f"- Baseline outlier orani: {baseline_value('outlier_ratio')}",
                f"- Final outlier orani: {final_value('outlier_ratio')}",
                "",
                "## En Etkili Degisiklikler",
                "",
                "1. CountVectorizer icin akademik boilerplate stopword listesi, bigramlar, min_df ve max_df eklendi.",
                "2. c-TF-IDF icin reduce_frequent_words=True aktif edildi.",
                "3. UMAP ve HDBSCAN parametreleri acik ve tekrar edilebilir hale getirildi.",
                "",
                "## Final Konfigurasyon",
                "",
                "- Embedding modeli: DB'deki precomputed embeddingler",
                "- CountVectorizer ayarlari: stop_words=custom+english, ngram_range=(1, 2), min_df=2, max_df=1.0, dtype=int32",
                "- c-TF-IDF ayari: reduce_frequent_words=True",
                "- Representation modeli: default BERTopic c-TF-IDF representation",
                "- UMAP ayarlari: n_neighbors=10, n_components=5, min_dist=0.0, metric=cosine, random_state=42, low_memory=runtime profile",
                "- HDBSCAN ayarlari: min_cluster_size=CLI min_topic_size, min_samples=1, metric=euclidean, core_dist_n_jobs=runtime profile",
                "",
                "## Uretilen Dosyalar",
                "",
                "- topic_info.csv",
                "- paper_topic_assignments.csv",
                "- topic_keywords.csv",
                "- bertopic_experiment_results.csv",
                "- bertopic_model",
                "",
                "## Manuel Inceleme Notlari",
                "",
                "Ilk buyuk topicler topic_info.csv ve topic_keywords.csv uzerinden incelenmelidir.",
                "",
                "## Kalan Riskler",
                "",
                "- Bazi topicler hala fazla genel olabilir.",
                "- Cok nis alanlarda outlier orani artabilir.",
                "- Dataset buyudukce min_df, max_df ve min_cluster_size yeniden ayarlanmalidir.",
                "",
            ]
        )

    @staticmethod
    def _topic_keywords(top_words) -> list[str]:
        if isinstance(top_words, list):
            candidates = top_words
        elif isinstance(top_words, tuple):
            candidates = list(top_words)
        elif top_words:
            candidates = str(top_words).split(",")
        else:
            candidates = []

        keywords = []
        for candidate in candidates[:10]:
            if isinstance(candidate, tuple):
                candidate = candidate[0]
            keyword = str(candidate).strip().strip("'\"")
            if keyword:
                keywords.append(keyword)
        return keywords

    @staticmethod
    def _clean_keywords(keywords: list[str]) -> list[str]:
        cleaned = []
        for keyword in keywords[:10]:
            normalized = re.sub(r"\s+", " ", keyword.strip().lower())
            if normalized and not Cluster._is_stopword_keyword(normalized):
                cleaned.append(normalized)
        return cleaned

    @staticmethod
    def _valid_cluster_keywords(keywords: list[str]) -> bool:
        if not keywords:
            return False
        stopword_count = sum(1 for keyword in keywords[:10] if Cluster._is_stopword_keyword(keyword))
        return stopword_count / min(len(keywords), 10) <= 0.5

    @staticmethod
    def _is_stopword_keyword(keyword: str) -> bool:
        tokens = re.findall(r"[A-Za-z]+", keyword.lower())
        normalized = " ".join(tokens)
        return (
            not tokens
            or normalized in GENERIC_RESEARCH_KEYWORDS
            or all(token in Cluster.stop_words for token in tokens)
        )

    @staticmethod
    def _article_embedding(article) -> np.ndarray:
        return np.array(article.embedding, dtype=np.float32)

    @staticmethod
    def _document_text(article) -> str:
        return getattr(article, "_representation_text", build_representation_text(article.title, article.abstract_text))

    @staticmethod
    def _generate_cluster_name(ollama, topic_id: int, keywords_str: str) -> str:
        print(f"Generating cluster name for topic {topic_id} keywords: {keywords_str}...")
        prompt = (
            "You are an academic classification assistant. Given the following top keywords "
            f"for a research paper cluster: '{keywords_str}', "
            "generate a short, professional, and clear name (2 to 5 words) for this academic topic. "
            "Return ONLY the topic name, with no introductory text, no quotes, and no explanation."
        )
        try:
            cluster_name = ollama.generate(prompt).strip().strip('"').strip("'").strip()
            return cluster_name or keywords_str
        except Exception as e:
            print(f"Ollama failed to generate name for {keywords_str}: {e}. Using keywords instead.")
            return keywords_str

    @staticmethod
    def _representative_article_ids(articles) -> list[int]:
        return [
            article_id
            for article_id, _ in Cluster._representative_article_scores(articles)[:Cluster.top_representative_count]
        ]

    @staticmethod
    def _representative_article_scores(articles) -> list[tuple[int, float]]:
        if not articles:
            return []
        embeddings = np.array([Cluster._article_embedding(article) for article in articles], dtype=np.float32)
        centroid = np.mean(embeddings, axis=0)
        centroid_norm = np.linalg.norm(centroid)
        scored_articles = []
        for article, embedding in zip(articles, embeddings):
            denom = np.linalg.norm(embedding) * centroid_norm
            score = 0.0 if denom == 0.0 else float(np.dot(embedding, centroid) / denom)
            scored_articles.append((article.id, score))
        scored_articles.sort(key=lambda item: item[1], reverse=True)
        return scored_articles

    @staticmethod
    def _cluster_metadata(
        keywords: list[str],
        articles,
        representative_ids: list[int],
        representative_scores: list[tuple[int, float]],
    ) -> dict:
        categories = Counter()
        sources = Counter()
        dates = []
        for article in articles:
            if article.primary_category:
                categories[article.primary_category] += 1
            elif article.categories:
                first_category = article.categories.split(",")[0].strip()
                if first_category:
                    categories[first_category] += 1
            if article.source:
                sources[article.source] += 1
            if article.publish_date:
                dates.append(article.publish_date.date().isoformat())

        return {
            "keywords": keywords,
            "representative_article_ids": representative_ids,
            "representative_article_scores": {
                str(article_id): round(score, 6)
                for article_id, score in representative_scores[:Cluster.top_representative_count]
            },
            "top_categories": [category for category, _ in categories.most_common(5)],
            "source_distribution": dict(sources),
            "date_range": {
                "from": min(dates) if dates else None,
                "to": max(dates) if dates else None,
            },
            "built_at": datetime.now(UTC).isoformat(),
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Cluster articles that already have embeddings.")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Maximum number of embedded articles to cluster. Defaults to all embedded articles.",
    )
    parser.add_argument(
        "--min-topic-size",
        type=int,
        default=10,
        help="BERTopic minimum cluster size.",
    )
    parser.add_argument(
        "--include-openalex",
        action="store_true",
        help="Raw DB mode only: include OpenAlex records marked as computer science.",
    )
    parser.add_argument(
        "--clean-papers-csv",
        action="append",
        type=Path,
        default=None,
        help="Clean data hygiene CSV to use for BERTopic docs. Can be passed multiple times.",
    )
    parser.add_argument(
        "--raw-db",
        action="store_true",
        help="Ignore clean CSV exports and use the legacy DB scan fallback.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_BERTOPIC_OUTPUT_DIR,
        help="Directory for BERTopic CSV/model/report outputs.",
    )
    parser.add_argument(
        "--no-save-model",
        action="store_true",
        help="Write CSV outputs but skip saving the BERTopic model directory.",
    )
    parser.add_argument(
        "--skip-database-save",
        action="store_true",
        help="Run clustering and write outputs without replacing database clusters.",
    )
    parser.add_argument(
        "--run-experiments",
        action="store_true",
        help="Also run the legacy baseline model and record comparison metrics.",
    )
    parser.add_argument(
        "--hardware-profile",
        default=None,
        choices=["auto", "m4-pro-24gb", "balanced", "memory-saver"],
        help=(
            "Runtime profile for CPU thread and memory settings. "
            "Defaults to CLUSTERING_HARDWARE_PROFILE or auto."
        ),
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Override clustering CPU thread limit. Defaults to profile-specific value.",
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    Cluster.cluster(
        max_articles=args.max_articles,
        min_topic_size=args.min_topic_size,
        include_openalex=args.include_openalex,
        clean_papers_csv=args.clean_papers_csv,
        raw_db=args.raw_db,
        output_dir=args.output_dir,
        save_model=not args.no_save_model,
        save_database=not args.skip_database_save,
        run_experiments=args.run_experiments,
        hardware_profile=args.hardware_profile,
        threads=args.threads,
    )
