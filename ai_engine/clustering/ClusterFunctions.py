import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.ollama_service import get_ollama_service
import numpy as np
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
from sqlalchemy import and_, or_
from database.models.ClusterData import Cluster as ClusterModel
from database.models.ArticleData import Article
from database.db import SessionLocal
from datetime import UTC, datetime
from collections import Counter


class Cluster:
    top_representative_count = 10
    stop_words = set(ENGLISH_STOP_WORDS)

    @staticmethod
    def cluster(
        max_articles: int | None = None,
        min_topic_size: int = 10,
        include_openalex: bool = False,
    ):
        db = SessionLocal()
        try:
            cs_category_filter = or_(
                Article.primary_category.ilike("cs.%"),
                Article.categories.ilike("%cs.%"),
            )
            query = (
                db.query(Article)
                .filter(Article.embedding.isnot(None), Article.title.isnot(None))
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
            raise Exception("No clean articles found with valid embeddings and titles.")

        embeddings = np.array([Cluster._article_embedding(a) for a in clean_articles], dtype=np.float32)
        docs = np.array([Cluster._document_text(a) for a in clean_articles])

        print(f"Embeddings shape: {embeddings.shape}")

        topic_model = Cluster._build_topic_model(min_topic_size=min_topic_size)

        topics, probs = topic_model.fit_transform(docs, embeddings=embeddings)
        
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
        
        # Save to database
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
            and isinstance(article.embedding, (list, np.ndarray))
            and len(article.embedding) > 0
        )

    @staticmethod
    def _article_in_clustering_scope(article, include_openalex: bool = False) -> bool:
        source = (getattr(article, "source", None) or "").lower()
        if source == "arxiv":
            return Cluster._has_cs_category(article)
        if source == "openalex":
            return bool(include_openalex and (getattr(article, "metadata_json", {}) or {}).get("is_computer_science"))
        return False

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
    def _build_topic_model(min_topic_size: int) -> BERTopic:
        vectorizer_model = CountVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=2,
        )
        return BERTopic(
            embedding_model=None,
            vectorizer_model=vectorizer_model,
            min_topic_size=min_topic_size,
            verbose=True,
            nr_topics=None,
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
        return not tokens or all(token in Cluster.stop_words for token in tokens)

    @staticmethod
    def _article_embedding(article) -> np.ndarray:
        return np.array(article.embedding, dtype=np.float32)

    @staticmethod
    def _document_text(article) -> str:
        return f"{article.title}\n\n{article.abstract_text or ''}".strip()

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
        help="Include OpenAlex records marked as computer science. Defaults to arXiv cs.* only.",
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    Cluster.cluster(
        max_articles=args.max_articles,
        min_topic_size=args.min_topic_size,
        include_openalex=args.include_openalex,
    )
