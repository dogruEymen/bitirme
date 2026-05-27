from backend.app.core.DbFunctions import DbFunctions
from backend.app.services.ollama_service import get_ollama_service
import numpy as np
from bertopic import BERTopic
from database.models.ClusterData import Cluster as ClusterModel
from database.models.ArticleData import Article
from database.db import SessionLocal
from datetime import datetime
from sqlalchemy import text


class Cluster:
    top_representative_count = 10
    num_of_articles = 3500

    @staticmethod
    def cluster():
        # Load articles dynamically at execution time
        articles = DbFunctions.get_articles_with_embedding(lim=Cluster.num_of_articles)
        if articles is None:
            raise Exception("DB returned None (connection issue likely)")
        if len(articles) == 0:
            raise Exception("DB returned empty list. Ensure embeddings are generated first.")

        clean_articles = [
            a for a in articles
            if isinstance(a.title, str)
            and isinstance(a.embedding, (list, np.ndarray))
            and len(a.embedding) > 0
        ]
        
        print("=== DATA STATISTICS ===")
        print(f"Total articles with embeddings fetched: {len(articles)}")
        print(f"Clean articles (with valid title and embedding): {len(clean_articles)}")
        print(f"Articles filtered out: {len(articles) - len(clean_articles)}")
        
        if len(clean_articles) == 0:
            raise Exception("No clean articles found with valid embeddings and titles.")

        embeddings = np.array(
            [np.array(a.embedding, dtype=np.float32) for a in clean_articles],
            dtype=np.float32
        )
        docs = np.array([article.title for article in clean_articles])

        print(f"Embeddings shape: {embeddings.shape}")

        # Initialize BERTopic model
        topic_model = BERTopic(
            embedding_model=None,
            min_topic_size=10,  # Minimum cluster size
            verbose=True,
            nr_topics="auto"  # Let BERTopic determine optimal number of topics
        )

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
            # Clear existing clusters
            db.query(ClusterModel).delete()
            
            # Reset all article cluster_ids
            db.query(Article).update({Article.cluster_id: None})
            db.commit()
            
            # Get topic info from BERTopic
            topic_info = topic_model.get_topic_info()
            
            # Group article IDs by cluster
            cluster_articles = {}
            for i, (article, topic_id) in enumerate(zip(clean_articles, topics)):
                if topic_id != -1:  # Skip outliers
                    if topic_id not in cluster_articles:
                        cluster_articles[topic_id] = []
                    cluster_articles[topic_id].append(article.id)
            
            # Initialize Ollama service for descriptive naming
            ollama = get_ollama_service()

            # Create clusters with Ollama generated descriptions
            cluster_counts = {}
            for _, row in topic_info.iterrows():
                topic_id = row['Topic']
                if topic_id != -1:  # Skip outlier topic
                    # Get top 10 words as representation
                    top_words = row.get('Representation', [])
                    keywords_str = ', '.join(top_words[:10]) if isinstance(top_words, list) else str(top_words)
                    
                    # Generate a concise topic name using Ollama
                    print(f"Generating cluster name for topic {topic_id} keywords: {keywords_str}...")
                    prompt = (
                        "You are an academic classification assistant. Given the following top keywords "
                        f"for a research paper cluster: '{keywords_str}', "
                        "generate a short, professional, and clear name (2 to 5 words) for this academic topic. "
                        "Return ONLY the topic name, with no introductory text, no quotes, and no explanation."
                    )
                    try:
                        cluster_name = ollama.generate(prompt)
                        # Clean up quotes or newlines if any
                        cluster_name = cluster_name.strip().strip('"').strip("'").strip()
                        print(f"Topic {topic_id} Named: {cluster_name}")
                    except Exception as e:
                        print(f"Ollama failed to generate name for {keywords_str}: {e}. Using keywords instead.")
                        cluster_name = keywords_str
                    
                    # Get article IDs for this cluster
                    article_ids = cluster_articles.get(topic_id, [])
                    article_ids_str = ','.join(map(str, article_ids)) if article_ids else None
                    
                    # Get top representative articles
                    if article_ids:
                        cluster_articles_list = [a for a in clean_articles if a.id in article_ids]
                        top_articles = cluster_articles_list[:Cluster.top_representative_count]
                        rep_docs_str = ','.join([str(a.id) for a in top_articles])
                    else:
                        rep_docs_str = None
                    
                    cluster = ClusterModel(
                        cluster_id=topic_id,
                        cluster_description=cluster_name,
                        article_count=row['Count'],
                        article_ids=article_ids_str,
                        representative_docs=rep_docs_str
                    )
                    db.add(cluster)
                    cluster_counts[topic_id] = row['Count']
            
            db.commit()
            
            # Update articles with cluster assignments
            for i, (article, topic_id) in enumerate(zip(clean_articles, topics)):
                if topic_id != -1:  # Skip outliers
                    db.execute(
                        text("UPDATE articles SET cluster_id = :cluster_id WHERE id = :article_id"),
                        {"cluster_id": topic_id, "article_id": article.id}
                    )
            
            db.commit()
            print(f"Saved {len(cluster_counts)} clusters and updated {len([t for t in topics if t != -1])} articles")
            
        except Exception as e:
            db.rollback()
            print(f"Error saving to database: {e}")
            raise
        finally:
            db.close()


if __name__ == '__main__':
    Cluster.cluster()
