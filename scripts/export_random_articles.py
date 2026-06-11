import csv
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

def export_random_articles():
    # Database configuration
    db_url = os.getenv("DATABASE_URL_ORIGINAL")
    if not db_url:
        print("Error: DATABASE_URL_ORIGINAL not found in environment variables.")
        return

    # Create engine and session
    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # We query all columns except 'embedding' to keep the CSV clean and small.
        # Query random 300 articles where cluster_id is not null and >= 0 (only id, title, abstract_text)
        query = text("""
            SELECT id, title, abstract_text
            FROM articles
            WHERE embedding IS NOT NULL AND cluster_id IS NOT NULL AND cluster_id >= 0
            ORDER BY RANDOM()
            LIMIT 300
        """)
        
        print("Querying random clustered articles (cluster_id >= 0) with embeddings from the database...")
        result = session.execute(query)
        columns = result.keys()
        rows = result.fetchall()
        
        if len(rows) < 300:
            print(f"Only found {len(rows)} clustered articles. Querying any random articles with embeddings to reach 300...")
            query_all = text("""
                SELECT id, title, abstract_text
                FROM articles
                WHERE embedding IS NOT NULL
                ORDER BY RANDOM()
                LIMIT 300
            """)
            result = session.execute(query_all)
            columns = result.keys()
            rows = result.fetchall()
        
        if not rows:
            print("No articles found in the database.")
            return

        # Ensure exports directory exists
        exports_dir = Path("exports")
        exports_dir.mkdir(exist_ok=True)
        
        output_file = exports_dir / "random_300_articles.csv"
        
        print(f"Writing {len(rows)} articles to {output_file}...")
        
        # Write to CSV
        with open(output_file, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(columns)
            # Write data rows
            writer.writerows(rows)
            
        print(f"Successfully exported 300 random articles to: {output_file.resolve()}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    export_random_articles()
