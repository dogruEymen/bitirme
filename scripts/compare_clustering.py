import os
import re
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Real data provided by user
real_data = [
    {
        "title": "Distributed Black-Box Optimization via Error Correcting Codes",
        "expected_cluster_id": 10,
        "expected_topic": "Multiobjective Bayesian Evolutionary Optimization"
    },
    {
        "title": "Facetize: An Interactive Tool for Cleaning and Transforming Datasets for Facilitating Exploratory Search",
        "expected_cluster_id": 414,
        "expected_topic": "Knowledge Graph Querying with RDF"
    },
    {
        "title": "Energy-Aware Relay Selection and Power Allocation for Multiple-User Cooperative Networks",
        "expected_cluster_id": 39,
        "expected_topic": "Energy Harvesting Secure Communications"
    },
    {
        "title": "Benchmarking Machine Learning Models for IoT Malware Detection under Data Scarcity and Drift",
        "expected_cluster_id": 31,
        "expected_topic": "IoT Intrusion Detection and DDoS Attacks"
    },
    {
        "title": "Point Cloud Network: An Order of Magnitude Improvement in Linear Layer Parameter Count",
        "expected_cluster_id": 66,
        "expected_topic": "3D Point Cloud Processing and Analysis"
    },
    {
        "title": "Multi-Domain Translation by Learning Uncoupled Autoencoders",
        "expected_cluster_id": 303,
        "expected_topic": "Unpaired Image Translation"
    },
    {
        "title": "A Laplacian Framework for Option Discovery in Reinforcement Learning",
        "expected_cluster_id": 63,
        "expected_topic": "Offline Reinforcement Learning Methods"
    },
    {
        "title": "Balancing Reconstruction and Editing Quality of GAN Inversion for Real Image Editing with StyleGAN Prior Latent Space",
        "expected_cluster_id": 88,
        "expected_topic": "Aesthetic Makeup Transfer using GANs"
    },
    {
        "title": "Multi-head Temporal Attention-Augmented Bilinear Network for Financial time series prediction",
        "expected_cluster_id": 148,
        "expected_topic": "Stock Price Prediction and Volatility"
    },
    {
        "title": "SegSLR: Promptable Video Segmentation for Isolated Sign Language Recognition",
        "expected_cluster_id": 321,
        "expected_topic": "Sign Language Recognition and Translation"
    }
]

def compare_clustering():
    db_url = os.getenv("DATABASE_URL_ORIGINAL")
    if not db_url:
        print("Error: DATABASE_URL_ORIGINAL not found.")
        return

    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print(f"{'No':<3} | {'Article Title':<50} | {'Expected CID':<12} | {'DB CID':<6} | {'Match?':<6} | {'Expected Topic':<45} | {'DB Topic'}")
        print("-" * 180)
        
        correct_count = 0
        found_count = 0

        for idx, item in enumerate(real_data, 1):
            title = item["title"]
            expected_cid = item["expected_cluster_id"]
            expected_topic = item["expected_topic"]
            
            # We search for the article in DB (using ILIKE to ignore case, and removing extra spacing if any)
            query_article = text("""
                SELECT id, title, cluster_id 
                FROM articles 
                WHERE LOWER(title) LIKE LOWER(:title) 
                LIMIT 1
            """)
            
            # Try exact match first
            result = session.execute(query_article, {"title": title}).fetchone()
            if not result:
                # Try search with wildcard/percentage signs
                result = session.execute(query_article, {"title": f"%{title}%"}).fetchone()
            
            db_cid = "N/A"
            db_topic = "N/A"
            is_match = "No"

            if result:
                found_count += 1
                db_cid_val = result[2]
                if db_cid_val is not None:
                    db_cid = db_cid_val
                    # Find topic name
                    query_topic = text("SELECT cluster_description FROM clusters WHERE cluster_id = :cid")
                    topic_res = session.execute(query_topic, {"cid": db_cid_val}).fetchone()
                    if topic_res:
                        db_topic = topic_res[0]
                    
                    if int(db_cid) == int(expected_cid):
                        correct_count += 1
                        is_match = "Yes"
                else:
                    db_cid = "NULL"
            else:
                db_cid = "Not Found"
                
            short_title = title[:47] + "..." if len(title) > 50 else title
            print(f"{idx:<3} | {short_title:<50} | {expected_cid:<12} | {str(db_cid):<6} | {is_match:<6} | {expected_topic[:42]+'...':<45} | {db_topic}")
            
        print("-" * 180)
        print(f"Total articles processed: {len(real_data)}")
        print(f"Found in DB: {found_count} / {len(real_data)}")
        print(f"Correct cluster matches: {correct_count} / {found_count} (Accuracy: {correct_count/found_count*100:.1f}% of found articles)")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    compare_clustering()
