import argparse
import csv
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.data_hygiene.text_preparation import DataHygieneResult, clean_paper_records
from database.db import SessionLocal
from database.models.ArticleData import Article


KEEP_COLUMNS = [
    "title",
    "abstract",
    "title_clean",
    "abstract_clean",
    "abstract_truncated",
    "embedding_text",
    "representation_text",
    "is_survey",
]
OPTIONAL_COLUMNS = [
    "arxiv_id",
    "doi",
    "paper_id",
    "authors",
    "published",
    "updated",
    "primary_category",
    "categories",
    "source",
    "lang",
    "category_family",
]


def article_to_record(article: Article) -> dict[str, Any]:
    return {
        "id": article.id,
        "external_id": article.external_id,
        "arxiv_id": article.external_id if article.source == "arxiv" else None,
        "paper_id": article.external_id,
        "doi": article.doi,
        "title": article.title,
        "abstract": article.abstract_text,
        "abstract_text": article.abstract_text,
        "authors": article.authors,
        "published": article.publish_date.isoformat() if article.publish_date else None,
        "updated": article.updated_date.isoformat() if article.updated_date else None,
        "primary_category": article.primary_category,
        "categories": article.categories,
        "source": article.source,
        "lang": article.language,
        "language": article.language,
    }


def load_article_records(
    source: str | None,
    cs_only: bool,
    limit: int | None,
) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        query = db.query(Article).order_by(Article.id.asc())
        if source:
            query = query.filter(Article.source == source)
        if cs_only:
            query = query.filter(
                (Article.primary_category.ilike("cs.%"))
                | (Article.categories.ilike("%cs.%"))
                | (Article.metadata_json["is_computer_science"].as_boolean().is_(True))
            )
        if limit is not None:
            query = query.limit(limit)
        return [article_to_record(article) for article in query.all()]
    finally:
        db.close()


def write_outputs(result: DataHygieneResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "clean_papers.csv", result.clean_records)
    write_csv(output_dir / "clean_papers_for_bertopic.csv", _bertopic_records(result.clean_records))
    write_csv(
        output_dir / "data_hygiene_metrics.csv",
        [{"metric": key, "value": value} for key, value in result.metrics.items()],
    )
    write_csv(output_dir / "removed_records.csv", result.removed_records)
    write_csv(output_dir / "duplicate_records.csv", result.duplicate_records)
    write_report(result, output_dir / "data_hygiene_report.md")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = _fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(result: DataHygieneResult, path: Path) -> None:
    metrics = result.metrics
    report = f"""# Data Hygiene ve Text Preparation Raporu

## Ozet

- Baslangic kayit sayisi: {metrics.get("initial_rows", 0)}
- Final kayit sayisi: {metrics.get("final_rows", 0)}
- Silinen toplam kayit sayisi: {metrics.get("removed_total", 0)}
- Duplicate kayit sayisi: {metrics.get("duplicate_total", 0)}

## Baslangic Problemleri

- Bos title sayisi: {metrics.get("empty_title_count", 0)}
- Bos abstract sayisi: {metrics.get("empty_abstract_count", 0)}
- Cok kisa title sayisi: {metrics.get("short_title_count_len_le_10", 0)}
- Cok kisa abstract sayisi: {metrics.get("short_abstract_count_len_le_100", 0)}

## Final Veri Kalitesi

- Ortalama title uzunlugu: {metrics.get("avg_title_length", 0):.2f}
- Ortalama abstract uzunlugu: {metrics.get("avg_abstract_length", 0):.2f}
- Ortalama abstract kelime sayisi: {metrics.get("avg_abstract_word_count", 0):.2f}
- Survey/review olarak isaretlenen kayit sayisi: {metrics.get("survey_count", 0)}
- Dil filtresi uygulandi: {metrics.get("language_filter_applied", False)}

## Uretilen Alanlar

- title_clean
- abstract_clean
- abstract_truncated
- embedding_text
- representation_text
- is_survey
- category_family

## Uretilen Dosyalar

- clean_papers.csv
- clean_papers_for_bertopic.csv
- data_hygiene_metrics.csv
- removed_records.csv
- duplicate_records.csv

## Notlar

Embedding icin `embedding_text` kullanilmalidir.
Topic representation ve BERTopic docs girdisi icin `representation_text` kullanilmalidir.
Embeddingler disaridan hesaplanip BERTopic'e verilmelidir.
"""
    path.write_text(report, encoding="utf-8")


def _bertopic_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    final_columns = [column for column in KEEP_COLUMNS + OPTIONAL_COLUMNS if any(column in row for row in rows)]
    return [{column: row.get(column) for column in final_columns} for row in rows]


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["id"]
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    return fieldnames


def parse_args():
    parser = argparse.ArgumentParser(description="Export clean paper CSVs for embedding and BERTopic.")
    parser.add_argument("--output-dir", default="exports/data_hygiene", help="Directory for generated CSV/report files.")
    parser.add_argument("--source", default="arxiv", help="Source filter. Use empty string with --include-all-sources.")
    parser.add_argument("--include-all-sources", action="store_true", help="Do not filter by source.")
    parser.add_argument("--include-non-cs", action="store_true", help="Do not filter to Computer Science-like records.")
    parser.add_argument("--detect-language", action="store_true", help="Use langdetect when installed; otherwise existing language metadata is used.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum records to read from the database.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = None if args.include_all_sources else args.source
    records = load_article_records(source=source, cs_only=not args.include_non_cs, limit=args.limit)
    result = clean_paper_records(records, detect_language=args.detect_language)
    write_outputs(result, Path(args.output_dir))
    print(f"Clean records: {len(result.clean_records)}")
    print(f"Removed records: {len(result.removed_records)}")
    print(f"Duplicate records: {len(result.duplicate_records)}")
    print(f"Output directory: {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
