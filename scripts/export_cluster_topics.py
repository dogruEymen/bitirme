import csv
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

def export_cluster_topics():
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
        # Query all cluster ids and descriptions ordered by cluster_id
        query = text("""
            SELECT cluster_id, cluster_description
            FROM clusters
            ORDER BY cluster_id ASC
        """)
        
        print("Querying topic names from the database...")
        result = session.execute(query)
        
        # Fetch columns and rows
        columns = result.keys()
        rows = result.fetchall()
        
        if not rows:
            print("No clusters found in the database.")
            return

        # Ensure exports directory exists
        exports_dir = Path("exports")
        exports_dir.mkdir(exist_ok=True)
        
        output_file = exports_dir / "cluster_topics.csv"
        
        print(f"Writing {len(rows)} cluster topics to {output_file}...")
        
        # Write to CSV
        with open(output_file, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(columns)
            # Write data rows
            writer.writerows(rows)
            
        print(f"Successfully exported {len(rows)} topics to: {output_file.resolve()}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    export_cluster_topics()
