import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.models import User, ChatMessage, ChatSession, Article, Cluster, ClusterDigest, ReportSnapshot, UserBulletinPreference

def get_db_url_with_dbname(original_url, dbname):
    # E.g., postgresql+psycopg2://postgres:postgres@localhost:5432/academic_platform -> postgresql+psycopg2://postgres:postgres@localhost:5432/dbname
    base_url = original_url.rsplit("/", 1)[0]
    return f"{base_url}/{dbname}"

def main():
    load_dotenv()
    original_url = os.getenv("DATABASE_URL")
    if not original_url:
        print("Error: DATABASE_URL not found in environment or .env file.")
        sys.exit(1)
        
    sample_dbname = "academic_platform_sample"
    postgres_url = get_db_url_with_dbname(original_url, "postgres")
    sample_url = get_db_url_with_dbname(original_url, sample_dbname)
    
    print(f"Connecting to database server via default 'postgres' database...")
    postgres_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    
    # Check if sample database exists
    with postgres_engine.connect() as conn:
        db_exists = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{sample_dbname}'")).scalar()
        if db_exists:
            print(f"Database '{sample_dbname}' already exists. Recreating it to start fresh...")
            conn.execute(text(f"DROP DATABASE {sample_dbname} WITH (FORCE);"))
        
        print(f"Creating database '{sample_dbname}'...")
        conn.execute(text(f"CREATE DATABASE {sample_dbname};"))
        
    postgres_engine.dispose()
    
    # Enable vector extension
    print(f"Enabling pgvector extension on '{sample_dbname}'...")
    sample_engine_init = create_engine(sample_url, isolation_level="AUTOCOMMIT")
    with sample_engine_init.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    sample_engine_init.dispose()
    
    # Run migrations using Alembic
    print("Running database migrations on the new sample database...")
    alembic_path = PROJECT_ROOT / ".venv/bin/alembic"
    if not alembic_path.exists():
        alembic_path = "alembic"  # Fallback to system alembic
        
    env = os.environ.copy()
    env["DATABASE_URL"] = sample_url
    
    result = subprocess.run(
        [str(alembic_path), "-c", "database/alembic.ini", "upgrade", "head"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("Error running migrations:")
        print(result.stderr)
        sys.exit(1)
    print("Database migrations applied successfully.")
    
    # Setup database engines and sessions
    src_engine = create_engine(original_url)
    dst_engine = create_engine(sample_url)
    
    SrcSession = sessionmaker(bind=src_engine)
    DstSession = sessionmaker(bind=dst_engine)
    
    src_session = SrcSession()
    dst_session = DstSession()
    
    try:
        # 1. Copy Users
        print("Copying users...")
        users = src_session.query(User).all()
        for u in users:
            dst_session.add(User(
                id=u.id,
                username=u.username,
                email=u.email,
                password_hash=u.password_hash,
                created_at=u.created_at,
                updated_at=u.updated_at
            ))
        dst_session.commit()
        print(f"Copied {len(users)} users.")
        
        # 2. Copy Clusters
        print("Copying clusters...")
        clusters = src_session.query(Cluster).all()
        for c in clusters:
            dst_session.add(Cluster(
                id=c.id,
                cluster_id=c.cluster_id,
                cluster_description=c.cluster_description,
                article_count=c.article_count,
                article_ids=c.article_ids,
                representative_docs=c.representative_docs,
                metadata_json=c.metadata_json,
                created_at=c.created_at
            ))
        dst_session.commit()
        print(f"Copied {len(clusters)} clusters.")
        
        # 3. Copy Cluster Digests
        print("Copying cluster digests...")
        digests = src_session.query(ClusterDigest).all()
        for d in digests:
            dst_session.add(ClusterDigest(
                id=d.id,
                cluster_id=d.cluster_id,
                period_start=d.period_start,
                period_end=d.period_end,
                summary=d.summary,
                highlights_json=d.highlights_json,
                representative_article_ids_json=d.representative_article_ids_json,
                created_at=d.created_at
            ))
        dst_session.commit()
        print(f"Copied {len(digests)} cluster digests.")
        
        # 4. Copy Random 20,000 Articles
        print("Sampling 20,000 random articles from the source database...")
        # Get random articles that have embeddings
        articles = src_session.query(Article).filter(Article.embedding.isnot(None)).order_by(text("RANDOM()")).limit(20000).all()
        
        # If there are fewer than 20k articles with embeddings, fallback to any articles
        if len(articles) < 20000:
            print(f"Found only {len(articles)} articles with embeddings. Fetching additional articles without embeddings to reach 20,000...")
            needed = 20000 - len(articles)
            existing_ids = {a.id for a in articles}
            additional = src_session.query(Article).filter(~Article.id.in_(existing_ids)).order_by(text("RANDOM()")).limit(needed).all()
            articles.extend(additional)
            
        print(f"Writing {len(articles)} articles to the sample database...")
        batch_size = 1000
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i+batch_size]
            for a in batch:
                dst_session.add(Article(
                    id=a.id,
                    source=a.source,
                    external_id=a.external_id,
                    title=a.title,
                    abstract_text=a.abstract_text,
                    publish_date=a.publish_date,
                    updated_date=a.updated_date,
                    authors=a.authors,
                    url=a.url,
                    pdf_url=a.pdf_url,
                    primary_category=a.primary_category,
                    categories=a.categories,
                    doi=a.doi,
                    citation_count=a.citation_count,
                    venue=a.venue,
                    embedding=a.embedding,
                    embedding_model=a.embedding_model,
                    embedding_text_hash=a.embedding_text_hash,
                    embedding_created_at=a.embedding_created_at,
                    metadata_json=a.metadata_json,
                    language=a.language,
                    document_type=a.document_type,
                    ingestion_run_id=a.ingestion_run_id,
                    cluster_id=a.cluster_id
                ))
            dst_session.commit()
            print(f"Written batch {i // batch_size + 1}/{(len(articles) - 1) // batch_size + 1}...")
            
        print(f"Successfully copied {len(articles)} articles.")
        
        # 5. Copy User Bulletin Preferences
        print("Copying user bulletin preferences...")
        prefs = src_session.query(UserBulletinPreference).all()
        for p in prefs:
            dst_session.add(UserBulletinPreference(
                id=p.id,
                user_id=p.user_id,
                selection_type=p.selection_type,
                selected_cluster_ids_json=p.selected_cluster_ids_json,
                selected_categories_json=p.selected_categories_json,
                bulletin_snapshot_key=p.bulletin_snapshot_key,
                notifications_enabled=p.notifications_enabled,
                notification_frequency=p.notification_frequency,
                last_generated_at=p.last_generated_at,
                created_at=p.created_at,
                updated_at=p.updated_at
            ))
        dst_session.commit()
        print(f"Copied {len(prefs)} user bulletin preferences.")
        
        # 6. Copy Report Snapshots
        print("Copying report snapshots...")
        snapshots = src_session.query(ReportSnapshot).all()
        for s in snapshots:
            dst_session.add(ReportSnapshot(
                id=s.id,
                snapshot_key=s.snapshot_key,
                payload_json=s.payload_json,
                metadata_json=s.metadata_json,
                generated_at=s.generated_at
            ))
        dst_session.commit()
        print(f"Copied {len(snapshots)} report snapshots.")
        
        # 7. Copy Chat Sessions and Messages
        print("Copying chat sessions...")
        sessions = src_session.query(ChatSession).all()
        for s in sessions:
            dst_session.add(ChatSession(
                id=s.id,
                user_id=s.user_id,
                title=s.title,
                summary=s.summary,
                summary_updated_at=s.summary_updated_at,
                created_at=s.created_at,
                updated_at=s.updated_at
            ))
        dst_session.commit()
        print(f"Copied {len(sessions)} chat sessions.")
        
        print("Copying chat messages...")
        messages = src_session.query(ChatMessage).all()
        for m in messages:
            dst_session.add(ChatMessage(
                id=m.id,
                chat_id=m.chat_id,
                role=m.role,
                content=m.content,
                metadata_json=m.metadata_json,
                created_at=m.created_at
            ))
        dst_session.commit()
        print(f"Copied {len(messages)} chat messages.")
        
        # Reset primary key sequences
        print("Resetting primary key sequences...")
        tables = [
            "users", "clusters", "cluster_digests", "articles", 
            "user_bulletin_preferences", "report_snapshots", 
            "chat_sessions", "chat_messages"
        ]
        with dst_engine.connect() as conn:
            for table in tables:
                seq_res = conn.execute(text(f"SELECT pg_get_serial_sequence('{table}', 'id');")).scalar()
                if seq_res:
                    conn.execute(text(f"SELECT setval('{seq_res}', COALESCE((SELECT MAX(id)+1 FROM {table}), 1), false);"))
            conn.execute(text("COMMIT;"))
        print("Sequences reset successfully.")
        
        print("\n=== SUCCESS ===")
        print(f"New sample database '{sample_dbname}' has been created with a 20,000 random sample of articles!")
        print("To switch your application to use this database, update the DATABASE_URL in your '.env' file:")
        print(f'DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/{sample_dbname}"')
        
    except Exception as e:
        dst_session.rollback()
        print(f"\nError occurred during database copying: {str(e)}")
        sys.exit(1)
    finally:
        src_session.close()
        dst_session.close()

if __name__ == "__main__":
    main()
