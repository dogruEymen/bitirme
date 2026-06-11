#!/usr/bin/env python3
import os
import re
import csv
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
load_dotenv()

def clean_title(title: str) -> str:
    """Clean the title to allow robust matching under formatting differences."""
    if not title:
        return ""
    # Standardize LaTeX math symbol for pi
    title = title.replace(r"$\pi$", "π")
    # Remove all non-alphanumeric characters and lowercase
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", title).lower()
    # Normalize whitespaces
    cleaned = " ".join(cleaned.split())
    return cleaned

def fetch_golden_articles(conn, csv_rows):
    """
    Look up each article from the CSV in the database using a multi-stage fallback search.
    Returns a list of dictionaries with matching database details.
    """
    matched_articles = []
    
    for idx, row in enumerate(csv_rows, 1):
        csv_title = row.get("title", "").strip()
        expected_cluster_desc = row.get("cluster_description", "").strip()
        if not csv_title and not row.get("article_id"):
            continue
            
        db_article = None
        match_method = None
        
        # Stage 0: Direct lookup by article_id if present
        article_id = row.get("article_id")
        if article_id:
            try:
                art_id_val = int(str(article_id).strip())
                q0 = text("""
                    SELECT a.id, a.title, a.cluster_id, c.cluster_description
                    FROM articles a
                    LEFT JOIN clusters c ON a.cluster_id = c.cluster_id
                    WHERE a.id = :id
                    LIMIT 1
                """)
                res = conn.execute(q0, {"id": art_id_val}).fetchone()
                if res:
                    db_article = res
                    match_method = "Article ID"
            except ValueError:
                pass
                
        # Stage 1: Exact case-insensitive match (fallback)
        if not db_article and csv_title:
            q1 = text("""
                SELECT a.id, a.title, a.cluster_id, c.cluster_description
                FROM articles a
                LEFT JOIN clusters c ON a.cluster_id = c.cluster_id
                WHERE LOWER(a.title) = LOWER(:title)
                LIMIT 1
            """)
            res = conn.execute(q1, {"title": csv_title}).fetchone()
            if res:
                db_article = res
                match_method = "Exact"
                
        # Stage 2: Fuzzy search with first 30 characters ILIKE (fallback)
        if not db_article and csv_title:
            prefix = csv_title[:30]
            q2 = text("""
                SELECT a.id, a.title, a.cluster_id, c.cluster_description
                FROM articles a
                LEFT JOIN clusters c ON a.cluster_id = c.cluster_id
                WHERE a.title ILIKE :prefix
            """)
            results = conn.execute(q2, {"prefix": f"%{prefix}%"}).fetchall()
            csv_title_clean = clean_title(csv_title)
            for r in results:
                db_title_clean = clean_title(r[1])
                if csv_title_clean in db_title_clean or db_title_clean in csv_title_clean:
                    db_article = r
                    match_method = "Fuzzy (Prefix)"
                    break
                    
        # Stage 3: Keyword-based search (fallback)
        if not db_article and csv_title:
            words = [w for w in re.findall(r"\w+", csv_title) if len(w) > 4]
            if words:
                conditions = " AND ".join(f"a.title ILIKE :w{i}" for i in range(len(words)))
                q3 = text(f"""
                    SELECT a.id, a.title, a.cluster_id, c.cluster_description
                    FROM articles a
                    LEFT JOIN clusters c ON a.cluster_id = c.cluster_id
                    WHERE {conditions}
                    LIMIT 5
                """)
                params = {f"w{i}": f"%{word}%" for i, word in enumerate(words)}
                results = conn.execute(q3, params).fetchall()
                csv_title_clean = clean_title(csv_title)
                for r in results:
                    db_title_clean = clean_title(r[1])
                    if csv_title_clean in db_title_clean or db_title_clean in csv_title_clean:
                        db_article = r
                        match_method = "Fuzzy (Keywords)"
                        break
                        
        if db_article:
            matched_articles.append({
                "csv_index": idx,
                "csv_title": csv_title or db_article[1],
                "expected_cluster_desc": expected_cluster_desc,
                "db_id": db_article[0],
                "db_title": db_article[1],
                "db_cluster_id": db_article[2],
                "db_cluster_desc": db_article[3],
                "match_method": match_method
            })
        else:
            matched_articles.append({
                "csv_index": idx,
                "csv_title": csv_title,
                "expected_cluster_desc": expected_cluster_desc,
                "db_id": None,
                "db_title": None,
                "db_cluster_id": None,
                "db_cluster_desc": None,
                "match_method": "Not Found"
            })
            
    return matched_articles

def evaluate_metrics(matched_articles):
    """Calculate and return evaluation metrics."""
    # Filter only those found and clustered
    valid_articles = [
        a for a in matched_articles 
        if a["db_id"] is not None and a["db_cluster_id"] is not None and a["db_cluster_id"] != -1
    ]
    
    total = len(matched_articles)
    found = sum(1 for a in matched_articles if a["db_id"] is not None)
    clustered = len(valid_articles)
    
    if clustered == 0:
        return {
            "total_articles": total,
            "found_articles": found,
            "clustered_articles": clustered,
            "direct_match_accuracy": 0.0,
            "hungarian_mapping_accuracy": 0.0,
            "majority_vote_purity": 0.0,
            "ari": 0.0,
            "nmi": 0.0,
            "mapping": {},
            "majority_mapping": {}
        }
        
    y_true = [a["expected_cluster_desc"] for a in valid_articles]
    y_pred = [a["db_cluster_id"] for a in valid_articles]
    
    # 1. Direct match accuracy
    direct_matches = 0
    for a in valid_articles:
        expected = a["expected_cluster_desc"].strip().lower()
        actual = (a["db_cluster_desc"] or "").strip().lower()
        if expected == actual:
            direct_matches += 1
    direct_match_accuracy = direct_matches / clustered
    
    # 2. Optimal Mapping (Hungarian Algorithm) Accuracy
    from scipy.optimize import linear_sum_assignment
    import numpy as np
    
    unique_true = sorted(list(set(y_true)))
    unique_pred = sorted(list(set(y_pred)))
    
    true_to_idx = {val: idx for idx, val in enumerate(unique_true)}
    pred_to_idx = {val: idx for idx, val in enumerate(unique_pred)}
    
    cost_matrix = np.zeros((len(unique_true), len(unique_pred)))
    for yt, yp in zip(y_true, y_pred):
        cost_matrix[true_to_idx[yt], pred_to_idx[yp]] -= 1
        
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    
    mapping = {}
    for r, c in zip(row_ind, col_ind):
        mapping[unique_pred[c]] = unique_true[r]
        
    mapped_correct = 0
    for yt, yp in zip(y_true, y_pred):
        if yp in mapping and mapping[yp] == yt:
            mapped_correct += 1
    hungarian_mapping_accuracy = mapped_correct / clustered
    
    # 3. Cluster Purity / Majority Vote Accuracy (Many-to-one mapping)
    from collections import Counter
    majority_mapping = {}
    pred_to_true_labels = {p: [] for p in unique_pred}
    for yt, yp in zip(y_true, y_pred):
        pred_to_true_labels[yp].append(yt)
        
    purity_correct = 0
    for yp, true_labels in pred_to_true_labels.items():
        if true_labels:
            most_common = Counter(true_labels).most_common(1)[0]
            majority_mapping[yp] = most_common[0]
            purity_correct += most_common[1]
            
    majority_vote_purity = purity_correct / clustered
    
    # 4. Standard clustering metrics (NMI & ARI)
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
    
    # Map true cluster names to label ids for sklearn
    y_true_ids = [true_to_idx[yt] for yt in y_true]
    ari = float(adjusted_rand_score(y_true_ids, y_pred))
    nmi = float(normalized_mutual_info_score(y_true_ids, y_pred))
    
    return {
        "total_articles": total,
        "found_articles": found,
        "clustered_articles": clustered,
        "direct_match_accuracy": direct_match_accuracy,
        "hungarian_mapping_accuracy": hungarian_mapping_accuracy,
        "majority_vote_purity": majority_vote_purity,
        "ari": ari,
        "nmi": nmi,
        "mapping": {str(k): v for k, v in mapping.items()},
        "majority_mapping": {str(k): v for k, v in majority_mapping.items()}
    }

def print_report(matched_articles, metrics):
    """Print a detailed report to the console."""
    print("=" * 140)
    print(" CLUSTERING EVALUATION REPORT AGAINST GOLDEN SET")
    print("=" * 140)
    
    # Print article table
    print(f"{'No':<3} | {'Article Title':<50} | {'Expected Cluster':<35} | {'DB Cluster ID':<13} | {'DB Cluster Description'}")
    print("-" * 140)
    for a in matched_articles:
        title_disp = a["csv_title"][:47] + "..." if len(a["csv_title"]) > 50 else a["csv_title"]
        exp_disp = a["expected_cluster_desc"][:32] + "..." if len(a["expected_cluster_desc"]) > 35 else a["expected_cluster_desc"]
        db_cid_disp = str(a["db_cluster_id"]) if a["db_cluster_id"] is not None else "N/A"
        db_desc_disp = a["db_cluster_desc"] or ""
        db_desc_disp = db_desc_disp[:32] + "..." if len(db_desc_disp) > 35 else db_desc_disp
        
        # Mark if direct match
        is_direct = "✓" if (a["expected_cluster_desc"] or "").strip().lower() == (a["db_cluster_desc"] or "").strip().lower() and a["db_cluster_id"] is not None else ""
        if is_direct:
            db_cid_disp += " (Direct)"
            
        print(f"{a['csv_index']:<3} | {title_disp:<50} | {exp_disp:<35} | {db_cid_disp:<13} | {db_desc_disp}")
        
    print("-" * 140)
    print(" SUMMARY STATISTICS")
    print("-" * 140)
    print(f"Total articles in Golden Set:       {metrics['total_articles']}")
    print(f"Articles found in Database:         {metrics['found_articles']} ({metrics['found_articles']/metrics['total_articles']*100:.1f}%)")
    print(f"Articles with active Cluster ID:    {metrics['clustered_articles']} ({metrics['clustered_articles']/metrics['found_articles']*100:.1f}% of found)")
    print(f"Direct Match Accuracy:              {metrics['direct_match_accuracy']*100:.1f}%")
    print(f"Optimal Mapping Accuracy (1-to-1):  {metrics['hungarian_mapping_accuracy']*100:.1f}%")
    print(f"Cluster Purity / Majority Vote:     {metrics['majority_vote_purity']*100:.1f}%")
    print(f"Adjusted Rand Index (ARI):          {metrics['ari']:.4f}")
    print(f"Normalized Mutual Information (NMI): {metrics['nmi']:.4f}")
    print("=" * 140)

def write_reports_to_disk(matched_articles, metrics, output_dir, runs_data=None):
    """Write report files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save JSON report
    json_path = output_dir / "clustering_accuracy_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        payload = {
            "metrics": metrics,
            "articles": matched_articles
        }
        if runs_data:
            payload["runs_data"] = runs_data
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON report to: {json_path.resolve()}")
    
    # Save Markdown report
    md_path = output_dir / "clustering_accuracy_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Clustering Accuracy Evaluation Report\n\n")
        
        if runs_data:
            f.write(f"## Multi-Run Summary ({runs_data['num_runs']} Runs of {runs_data['sample_size']} Articles)\n\n")
            f.write("| Metric | Mean | Std Dev | Individual Runs |\n")
            f.write("| --- | --- | --- | --- |\n")
            
            for key, label in [
                ("direct_match_accuracy", "**Direct Match Accuracy**"),
                ("hungarian_mapping_accuracy", "**Optimal Mapping Accuracy (Hungarian)**"),
                ("majority_vote_purity", "**Cluster Purity (Majority Vote)**"),
                ("ari", "Adjusted Rand Index (ARI)"),
                ("nmi", "Normalized Mutual Information (NMI)")
            ]:
                mean_val = metrics[f"{key}_mean"]
                std_val = metrics[f"{key}_std"]
                runs_list = [f"{v*100:.1f}%" if key not in ["ari", "nmi"] else f"{v:.4f}" for v in metrics[f"{key}_runs"]]
                
                if key in ["ari", "nmi"]:
                    f.write(f"| {label} | {mean_val:.4f} | {std_val:.4f} | [{', '.join(runs_list)}] |\n")
                else:
                    f.write(f"| {label} | **{mean_val*100:.1f}%** | {std_val*100:.1f}% | [{', '.join(runs_list)}] |\n")
            f.write("\n")
        else:
            f.write("## Overview Metrics\n\n")
            f.write("| Metric | Value |\n")
            f.write("| --- | --- |\n")
            f.write(f"| Total Golden Set Articles | {metrics['total_articles']} |\n")
            f.write(f"| Articles Found in DB | {metrics['found_articles']} ({metrics['found_articles']/metrics['total_articles']*100:.1f}%) |\n")
            f.write(f"| Active Clustered Articles | {metrics['clustered_articles']} |\n")
            f.write(f"| **Direct Match Accuracy** | **{metrics['direct_match_accuracy']*100:.1f}%** |\n")
            f.write(f"| **Optimal Mapping Accuracy (Hungarian)** | **{metrics['hungarian_mapping_accuracy']*100:.1f}%** |\n")
            f.write(f"| **Cluster Purity (Majority Vote)** | **{metrics['majority_vote_purity']*100:.1f}%** |\n")
            f.write(f"| Adjusted Rand Index (ARI) | {metrics['ari']:.4f} |\n")
            f.write(f"| Normalized Mutual Information (NMI) | {metrics['nmi']:.4f} |\n\n")
        
        f.write("## Article Breakdown (Sample from Run 1)\n\n")
        f.write("| No | Article Title | Expected Cluster | DB Cluster ID | DB Cluster Description | Match Type |\n")
        f.write("| --- | --- | --- | --- | --- | --- |\n")
        
        # We use the mapping from run 1 for rendering the table statuses
        mapping = runs_data["first_run_mapping"] if runs_data else metrics.get("mapping", {})
        maj_mapping = runs_data["first_run_majority_mapping"] if runs_data else metrics.get("majority_mapping", {})
        
        for a in matched_articles:
            title = a["csv_title"].replace("|", "\\|")
            exp = a["expected_cluster_desc"].replace("|", "\\|")
            db_id = str(a["db_cluster_id"]) if a["db_cluster_id"] is not None else "N/A"
            db_desc = (a["db_cluster_desc"] or "").replace("|", "\\|")
            
            # Determine match status
            expected_clean = (a["expected_cluster_desc"] or "").strip().lower()
            actual_clean = (a["db_cluster_desc"] or "").strip().lower()
            if a["db_cluster_id"] is None:
                match_status = "Not Found"
            elif expected_clean == actual_clean:
                match_status = "Direct Match"
            else:
                db_id_str = str(a["db_cluster_id"])
                maj_mapped = maj_mapping.get(db_id_str)
                opt_mapped = mapping.get(db_id_str)
                if opt_mapped == a["expected_cluster_desc"]:
                    match_status = "Optimal Mapping Match"
                elif maj_mapped == a["expected_cluster_desc"]:
                    match_status = "Purity Mapping Match"
                else:
                    match_status = "Mismatch"
            
            f.write(f"| {a['csv_index']} | {title} | {exp} | {db_id} | {db_desc} | {match_status} |\n")
            
    print(f"Saved Markdown report to: {md_path.resolve()}")

def main():
    import argparse
    import random
    import numpy as np
    
    parser = argparse.ArgumentParser(description="Evaluate clustering accuracy.")
    parser.add_argument(
        "--csv",
        type=str,
        default="evaluation/golden_set_topic_clustering.csv",
        help="Path to the golden set CSV file (relative to project root or absolute)"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Number of random articles to sample from the CSV for evaluation"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of evaluation runs to perform (averages results if > 1)"
    )
    args = parser.parse_args()

    # Database config
    db_url = os.getenv("DATABASE_URL_ORIGINAL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: Neither DATABASE_URL_ORIGINAL nor DATABASE_URL found in environment variables.")
        sys.exit(1)
        
    engine = create_engine(db_url, pool_pre_ping=True)
    
    # Load CSV
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
        
    if not csv_path.exists():
        print(f"Error: Golden set file not found at {csv_path}")
        sys.exit(1)
        
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        csv_rows = list(reader)
        
    print(f"Loaded {len(csv_rows)} golden set articles from {csv_path.name}.")
    
    if args.runs <= 1:
        # Single run evaluation
        selected_rows = csv_rows
        if args.sample is not None:
            if len(csv_rows) <= args.sample:
                print(f"Sample size {args.sample} is greater than or equal to available rows {len(csv_rows)}. Skipping sampling.")
            else:
                print(f"Randomly sampling {args.sample} articles out of {len(csv_rows)}...")
                selected_rows = random.sample(csv_rows, args.sample)
                # Write to golden_set.csv
                sampled_csv_path = PROJECT_ROOT / "evaluation/golden_set.csv"
                with open(sampled_csv_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(selected_rows)
                print(f"Successfully wrote {len(selected_rows)} sampled rows to: {sampled_csv_path.resolve()}")
                
        print("Matching articles against the database...")
        with engine.connect() as conn:
            matched_articles = fetch_golden_articles(conn, selected_rows)
            
        print("Computing metrics...")
        metrics = evaluate_metrics(matched_articles)
        print_report(matched_articles, metrics)
        
        output_dir = PROJECT_ROOT / "exports/evaluation"
        write_reports_to_disk(matched_articles, metrics, output_dir)
        
    else:
        # Multi-run evaluation
        num_runs = args.runs
        sample_size = args.sample if args.sample is not None else len(csv_rows)
        print(f"Starting multi-run evaluation: {num_runs} runs of {sample_size} articles each.")
        
        all_metrics = []
        first_run_matched = None
        first_run_mapping = None
        first_run_majority_mapping = None
        
        for run_idx in range(1, num_runs + 1):
            selected_rows = csv_rows
            if args.sample is not None and len(csv_rows) > args.sample:
                selected_rows = random.sample(csv_rows, args.sample)
                if run_idx == 1:
                    # Save the first run's subset to golden_set.csv
                    sampled_csv_path = PROJECT_ROOT / "evaluation/golden_set.csv"
                    with open(sampled_csv_path, "w", encoding="utf-8", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(selected_rows)
                    print(f"Run 1: Successfully wrote sampled rows to: {sampled_csv_path.resolve()}")
            
            with engine.connect() as conn:
                matched = fetch_golden_articles(conn, selected_rows)
                
            metrics = evaluate_metrics(matched)
            all_metrics.append(metrics)
            
            if run_idx == 1:
                first_run_matched = matched
                first_run_mapping = metrics["mapping"]
                first_run_majority_mapping = metrics["majority_mapping"]
                
            print(f"Completed run {run_idx}/{num_runs} (Direct Match: {metrics['direct_match_accuracy']*100:.1f}%, Optimal Mapping: {metrics['hungarian_mapping_accuracy']*100:.1f}%)")
            
        # Aggregate statistics
        keys_to_avg = ["direct_match_accuracy", "hungarian_mapping_accuracy", "majority_vote_purity", "ari", "nmi"]
        aggregated_metrics = {
            "total_articles": sample_size,
            "found_articles": sample_size,
            "clustered_articles": sample_size,
        }
        for key in keys_to_avg:
            values = [m[key] for m in all_metrics]
            aggregated_metrics[f"{key}_mean"] = float(np.mean(values))
            aggregated_metrics[f"{key}_std"] = float(np.std(values))
            aggregated_metrics[f"{key}_runs"] = values
            
        # Print summary report
        print("=" * 140)
        print(f" MULTI-RUN SUMMARY STATISTICS ({num_runs} Runs of {sample_size} articles)")
        print("=" * 140)
        print(f"{'Metric':<35} | {'Mean':<10} | {'Std Dev':<10} | {'Individual Runs'}")
        print("-" * 140)
        for key, label in [
            ("direct_match_accuracy", "Direct Match Accuracy"),
            ("hungarian_mapping_accuracy", "Optimal Mapping Accuracy (1-to-1)"),
            ("majority_vote_purity", "Cluster Purity / Majority Vote"),
            ("ari", "Adjusted Rand Index (ARI)"),
            ("nmi", "Normalized Mutual Information (NMI)")
        ]:
            mean_val = aggregated_metrics[f"{key}_mean"]
            std_val = aggregated_metrics[f"{key}_std"]
            runs_list = [f"{v*100:.1f}%" if key not in ["ari", "nmi"] else f"{v:.4f}" for v in aggregated_metrics[f"{key}_runs"]]
            
            if key in ["ari", "nmi"]:
                print(f"{label:<35} | {mean_val:<10.4f} | {std_val:<10.4f} | [{', '.join(runs_list)}]")
            else:
                print(f"{label:<35} | {mean_val*100:<9.1f}% | {std_val*100:<9.1f}% | [{', '.join(runs_list)}]")
        print("=" * 140)
        
        runs_data = {
            "num_runs": num_runs,
            "sample_size": sample_size,
            "first_run_mapping": first_run_mapping,
            "first_run_majority_mapping": first_run_majority_mapping
        }
        
        output_dir = PROJECT_ROOT / "exports/evaluation"
        write_reports_to_disk(first_run_matched, aggregated_metrics, output_dir, runs_data)

if __name__ == "__main__":
    main()
