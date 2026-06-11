from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db import SessionLocal
from database.models.ArticleData import Article


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a selected clustering experiment assignment CSV to Article.cluster_id.")
    parser.add_argument("--run-id", required=True, help="Experiment run id under exports/clustering_experiments.")
    parser.add_argument("--experiment", required=True, help="Experiment directory name under the run id.")
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "exports/clustering_experiments")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    assignment_path = args.input_dir / args.run_id / args.experiment / "paper_topic_assignments.csv"
    if not assignment_path.exists():
        print(f"Assignment file not found: {assignment_path}", file=sys.stderr)
        return 2

    assignments = _read_assignments(assignment_path)
    db = SessionLocal()
    try:
        updated = 0
        for article_id, topic in assignments:
            value = None if topic == -1 else topic
            if not args.dry_run:
                db.query(Article).filter(Article.id == article_id).update({Article.cluster_id: value})
            updated += 1
        if not args.dry_run:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    mode = "would update" if args.dry_run else "updated"
    print(f"{mode} {updated} article cluster assignments from {assignment_path}")
    return 0


def _read_assignments(path: Path) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "article_id" not in (reader.fieldnames or []) or "topic" not in (reader.fieldnames or []):
            raise ValueError("Assignment CSV must contain article_id and topic columns.")
        for row in reader:
            article_id = row.get("article_id")
            topic = row.get("topic")
            if article_id in (None, "") or topic in (None, ""):
                continue
            rows.append((int(article_id), int(float(topic))))
    return rows


if __name__ == "__main__":
    raise SystemExit(main())

