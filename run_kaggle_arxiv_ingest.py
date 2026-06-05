import argparse
import json
import logging
import random
from collections import defaultdict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

from database.db import SessionLocal
from ai_engine.ingestion.loader import _articles_to_insert_rows, save_articles_to_db
from ai_engine.ingestion.schemas import RawArticleSchema
from run_bulk_ingest import validate_article_table_schema


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Kaggle arXiv metadata snapshot dosyasini temizleyip articles tablosuna yazar."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Kaggle arXiv JSONL dosyasi. Ornek: arxiv-metadata-oai-snapshot.json",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="DB'ye yazilacak batch boyutu.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Test icin okunacak maksimum ham kayit sayisi.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB'ye yazmadan sadece parse/filter sayimlarini loglar.",
    )
    parser.add_argument(
        "--samples-per-month",
        type=int,
        default=None,
        help="Verilirse her ay icin bu kadar rastgele uygun makale secilir.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2016,
        help="Sampling modunda dahil edilecek ilk yil.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2026,
        help="Sampling modunda dahil edilecek son yil.",
    )
    parser.add_argument(
        "--target-max-records",
        type=int,
        default=None,
        help="Sampling sonrasi toplam kayit sayisi bu degeri asarsa global olarak tekrar orneklenir.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Sampling'in tekrarlanabilir olmasi icin random seed.",
    )
    args = parser.parse_args()
    if args.samples_per_month is not None and args.samples_per_month <= 0:
        parser.error("--samples-per-month pozitif bir integer olmali.")
    if args.start_year > args.end_year:
        parser.error("--start-year --end-year degerinden buyuk olamaz.")
    if args.target_max_records is not None and args.target_max_records <= 0:
        parser.error("--target-max-records pozitif bir integer olmali.")
    return args


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = " ".join(value.replace("\x00", "").split())
    return cleaned or None


def _category_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    return [item for item in str(value).split() if item]


def _parse_datetime(value: Any) -> datetime | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    try:
        parsed = parsedate_to_datetime(cleaned)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        pass

    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _first_version_date(record: dict[str, Any]) -> datetime | None:
    versions = record.get("versions") or []
    if isinstance(versions, list):
        for version in versions:
            if isinstance(version, dict):
                parsed = _parse_datetime(version.get("created"))
                if parsed is not None:
                    return parsed
    return None


def _pdf_url(external_id: str | None) -> str | None:
    if not external_id:
        return None
    return f"https://arxiv.org/pdf/{external_id}"


def kaggle_record_to_article(record: dict[str, Any]) -> RawArticleSchema | None:
    external_id = _clean_text(record.get("id"))
    title = _clean_text(record.get("title"))
    abstract_text = _clean_text(record.get("abstract"))
    categories = _category_list(record.get("categories"))

    if not external_id or not title:
        return None

    primary_category = categories[0] if categories else None
    publish_date = _first_version_date(record)
    updated_date = _parse_datetime(record.get("update_date"))
    is_computer_science = any(category.lower().startswith("cs.") for category in categories)

    return RawArticleSchema(
        source="arxiv",
        external_id=external_id,
        title=title,
        abstract_text=abstract_text,
        publish_date=publish_date,
        updated_date=updated_date,
        authors=_clean_text(record.get("authors")),
        url=f"https://arxiv.org/abs/{external_id}",
        pdf_url=_pdf_url(external_id),
        primary_category=primary_category,
        categories=", ".join(categories) or None,
        doi=_clean_text(record.get("doi")),
        citation_count=None,
        venue=_clean_text(record.get("journal-ref")),
        metadata_json={
            "source_payload_version": "kaggle_arxiv_v1",
            "is_computer_science": is_computer_science,
            "arxiv_id": external_id,
            "arxiv_primary_category": primary_category,
            "arxiv_categories": categories,
            "kaggle_submitter": _clean_text(record.get("submitter")),
            "kaggle_comments": _clean_text(record.get("comments")),
            "kaggle_report_no": _clean_text(record.get("report-no")),
            "kaggle_license": _clean_text(record.get("license")),
            "kaggle_authors_parsed": record.get("authors_parsed"),
        },
    )


def _month_key(value: datetime | None) -> str | None:
    if value is None:
        return None
    return f"{value.year:04d}-{value.month:02d}"


def _sampling_candidate(
    article: RawArticleSchema,
    start_year: int,
    end_year: int,
) -> tuple[bool, str | None]:
    if article.publish_date is None:
        return False, None
    if article.publish_date.year < start_year or article.publish_date.year > end_year:
        return False, None
    if not article.doi and not article.pdf_url:
        return False, None
    if not _articles_to_insert_rows([article], ingestion_run_id="sampling-check"):
        return False, None
    return True, _month_key(article.publish_date)


def _reservoir_add(
    samples_by_month: dict[str, list[RawArticleSchema]],
    seen_by_month: dict[str, int],
    month: str,
    article: RawArticleSchema,
    samples_per_month: int,
    rng: random.Random,
) -> None:
    seen_by_month[month] += 1
    seen_count = seen_by_month[month]

    if len(samples_by_month[month]) < samples_per_month:
        samples_by_month[month].append(article)
        return

    replacement_index = rng.randrange(seen_count)
    if replacement_index < samples_per_month:
        samples_by_month[month][replacement_index] = article


def _target_months(start_year: int, end_year: int) -> list[str]:
    return [
        f"{year:04d}-{month:02d}"
        for year in range(start_year, end_year + 1)
        for month in range(1, 13)
    ]


def iter_kaggle_records(path: Path, max_records: int | None = None) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if max_records is not None and line_number > max_records:
                break
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Gecersiz JSON satiri atlandi: %s", line_number)
                continue
            if isinstance(record, dict):
                yield record


def sample_kaggle_articles(
    path: Path,
    samples_per_month: int,
    start_year: int,
    end_year: int,
    random_seed: int,
    max_records: int | None = None,
    target_max_records: int | None = None,
) -> tuple[list[RawArticleSchema], dict[str, Any]]:
    rng = random.Random(random_seed)
    samples_by_month: dict[str, list[RawArticleSchema]] = defaultdict(list)
    seen_by_month: dict[str, int] = defaultdict(int)
    raw_count = 0
    parsed_count = 0
    eligible_count = 0

    for record in iter_kaggle_records(path, max_records=max_records):
        raw_count += 1
        article = kaggle_record_to_article(record)
        if article is None:
            continue
        parsed_count += 1

        is_candidate, month = _sampling_candidate(article, start_year=start_year, end_year=end_year)
        if not is_candidate or month is None:
            continue

        eligible_count += 1
        _reservoir_add(samples_by_month, seen_by_month, month, article, samples_per_month, rng)

        if raw_count % 250000 == 0:
            logger.info(
                "Sampling devam ediyor. raw=%s parsed=%s eligible=%s selected=%s",
                raw_count,
                parsed_count,
                eligible_count,
                sum(len(rows) for rows in samples_by_month.values()),
            )

    selected = [
        article
        for month in sorted(samples_by_month)
        for article in samples_by_month[month]
    ]
    if target_max_records is not None and len(selected) > target_max_records:
        selected = rng.sample(selected, target_max_records)

    month_targets = _target_months(start_year, end_year)
    month_counts = {month: 0 for month in month_targets}
    for article in selected:
        month = _month_key(article.publish_date)
        if month in month_counts:
            month_counts[month] += 1
    underfilled_months = {
        month: count
        for month, count in month_counts.items()
        if count < samples_per_month
    }
    stats = {
        "raw_count": raw_count,
        "parsed_count": parsed_count,
        "eligible_count": eligible_count,
        "selected_count": len(selected),
        "month_counts": month_counts,
        "underfilled_months": underfilled_months,
    }
    return selected, stats


def save_sampled_articles(
    db,
    articles: list[RawArticleSchema],
    batch_size: int,
    ingestion_run_id: str,
    dry_run: bool,
) -> int:
    inserted_count = 0
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        if dry_run:
            inserted = len(_articles_to_insert_rows(batch, ingestion_run_id=ingestion_run_id))
        else:
            inserted = save_articles_to_db(db, batch, ingestion_run_id=ingestion_run_id)
        inserted_count += inserted
        logger.info(
            "Sample batch tamamlandi. batch=%s selected_processed=%s upserted=%s",
            len(batch),
            min(i + batch_size, len(articles)),
            inserted_count,
        )
    return inserted_count


def main():
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Kaggle dosyasi bulunamadi: {input_path}")

    ingestion_run_id = f"kaggle-arxiv-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    db = SessionLocal()
    raw_count = 0
    parsed_count = 0
    inserted_count = 0
    batch: list[RawArticleSchema] = []

    try:
        if not args.dry_run:
            validate_article_table_schema(db)

        if args.samples_per_month is not None:
            selected, stats = sample_kaggle_articles(
                input_path,
                samples_per_month=args.samples_per_month,
                start_year=args.start_year,
                end_year=args.end_year,
                random_seed=args.random_seed,
                max_records=args.max_records,
                target_max_records=args.target_max_records,
            )
            inserted_count = save_sampled_articles(
                db,
                selected,
                batch_size=args.batch_size,
                ingestion_run_id=ingestion_run_id,
                dry_run=args.dry_run,
            )
            if stats["underfilled_months"]:
                logger.warning("Hedefin altinda kalan aylar: %s", stats["underfilled_months"])
            logger.info(
                "Kaggle sampling import tamamlandi. run_id=%s raw=%s parsed=%s eligible=%s selected=%s upserted=%s dry_run=%s",
                ingestion_run_id,
                stats["raw_count"],
                stats["parsed_count"],
                stats["eligible_count"],
                stats["selected_count"],
                inserted_count,
                args.dry_run,
            )
            return

        for record in iter_kaggle_records(input_path, max_records=args.max_records):
            raw_count += 1
            article = kaggle_record_to_article(record)
            if article is None:
                continue
            parsed_count += 1
            batch.append(article)

            if len(batch) >= args.batch_size:
                if args.dry_run:
                    inserted = len(_articles_to_insert_rows(batch, ingestion_run_id=ingestion_run_id))
                else:
                    inserted = save_articles_to_db(db, batch, ingestion_run_id=ingestion_run_id)
                inserted_count += inserted
                logger.info(
                    "Batch tamamlandi. raw=%s parsed=%s upserted=%s",
                    raw_count,
                    parsed_count,
                    inserted_count,
                )
                batch = []

        if batch:
            if args.dry_run:
                inserted = len(_articles_to_insert_rows(batch, ingestion_run_id=ingestion_run_id))
            else:
                inserted = save_articles_to_db(db, batch, ingestion_run_id=ingestion_run_id)
            inserted_count += inserted

        logger.info(
            "Kaggle import tamamlandi. run_id=%s raw=%s parsed=%s upserted=%s dry_run=%s",
            ingestion_run_id,
            raw_count,
            parsed_count,
            inserted_count,
            args.dry_run,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
