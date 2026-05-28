import asyncio
import argparse
from pathlib import Path
import logging
from datetime import datetime

from sqlalchemy import inspect

from database.db import SessionLocal
from database.models import Article
from ai_engine.ingestion.extractors.arxiv_extractor import ArxivExtractor
from ai_engine.ingestion.extractors.openalex_extractor import OpenAlexExtractor
from ai_engine.ingestion.extractors.s2_extractor import SemanticScholarExtractor
from ai_engine.ingestion.loader import ARTICLE_INSERT_COLUMNS, save_articles_to_db
from ai_engine.ingestion.state_manager import save_state

# Log ayarları
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

INGESTION_STATE_PATH = Path("ai_engine/ingestion/ingestion_state.json")
ARXIV_DB_BATCH_SIZE = 500
EXTRACTOR_FACTORIES = {
    "arxiv": ArxivExtractor,
    "openalex": OpenAlexExtractor,
    "semanticscholar": SemanticScholarExtractor,
}


def parse_args():
    parser = argparse.ArgumentParser(description="API kaynaklarindan makale cekip veritabanina yazar.")
    parser.add_argument(
        "--max-results",
        type=int,
        default=10000,
        help="Her kaynak ve sorgu icin cekilecek maksimum makale sayisi.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Arama sorgusu. Birden fazla kez verilebilir. Varsayilan: bos sorgu.",
    )
    parser.add_argument(
        "--sources",
        default="arxiv,openalex",
        help="Virgulle ayrilmis kaynak listesi: arxiv,openalex,semanticscholar.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="API cursor/offset state dosyasini sifirlayip bastan ceker.",
    )
    return parser.parse_args()


def build_extractors(source_arg: str):
    sources = [source.strip() for source in source_arg.split(",") if source.strip()]
    unknown_sources = [source for source in sources if source not in EXTRACTOR_FACTORIES]
    if unknown_sources:
        raise ValueError(f"Bilinmeyen kaynaklar: {', '.join(unknown_sources)}")
    return [EXTRACTOR_FACTORIES[source]() for source in sources]


def reset_ingestion_state():
    INGESTION_STATE_PATH.write_text("{}\n", encoding="utf-8")


def validate_article_table_schema(db):
    inspector = inspect(db.get_bind())
    table_name = Article.__tablename__
    article_columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing_columns = sorted(set(ARTICLE_INSERT_COLUMNS) - article_columns)

    if missing_columns:
        raise RuntimeError(
            "articles tablosu guncel degil. Eksik kolonlar: "
            f"{', '.join(missing_columns)}. "
            "Migration calistirin: .venv/bin/python -m alembic -c database/alembic.ini upgrade head"
        )

    unique_constraints = inspector.get_unique_constraints(table_name)
    indexes = inspector.get_indexes(table_name)
    has_external_id_unique = any(
        constraint.get("column_names") == ["external_id"]
        for constraint in unique_constraints
    ) or any(
        index.get("unique") and index.get("column_names") == ["external_id"]
        for index in indexes
    )

    if not has_external_id_unique:
        raise RuntimeError(
            "articles.external_id uzerinde unique constraint/index yok. "
            "PostgreSQL ON CONFLICT icin bu zorunlu. "
            "Migration calistirin: .venv/bin/python -m alembic -c database/alembic.ini upgrade head"
        )


async def main():
    args = parse_args()
    ingestion_run_id = f"bulk-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    if args.reset_state:
        reset_ingestion_state()
        logger.info("Ingestion state sifirlandi: %s", INGESTION_STATE_PATH)

    # Özel bir anahtar kelime olmadan (boş sorgu) tüm Computer Science makalelerini çekmek istiyoruz
    queries = args.query if args.query is not None else [""]
    
    extractors = build_extractors(args.sources)
    
    max_results_per_query = args.max_results
    total_inserted = 0

    logger.info("=== MAKALE ÇEKİMİ BAŞLIYOR ===")
    logger.info("Ingestion run id: %s", ingestion_run_id)
    logger.info("Uyarı: Sistem 'ingestion_state.json' dosyasını kontrol ederek kaldığı yerden devam edecektir.")

    # Veritabanı bağlantısını başlat
    db = SessionLocal()

    try:
        validate_article_table_schema(db)
        for query in queries:
            logger.info(f"=== SORGULANIYOR: '{query}' ===")
            for extractor in extractors:
                logger.info(f"[{extractor.source_name.upper()}] API'sine istek atılıyor...")
                try:
                    source_inserted = 0
                    source_fetched = 0

                    if hasattr(extractor, "fetch_article_batches"):
                        async for articles, checkpoint in extractor.fetch_article_batches(
                            query,
                            max_results=max_results_per_query,
                            batch_size=ARXIV_DB_BATCH_SIZE,
                        ):
                            source_fetched += len(articles)
                            logger.info(
                                "[%s] %s makalelik batch veritabanına yazılıyor...",
                                extractor.source_name.upper(),
                                len(articles),
                            )
                            inserted = save_articles_to_db(
                                db,
                                articles,
                                ingestion_run_id=ingestion_run_id,
                            )
                            save_state(extractor.source_name, checkpoint)
                            source_inserted += inserted
                            total_inserted += inserted
                            logger.info(
                                "[%s] Batch başarılı. %s kayıt eklendi/güncellendi. State güncellendi: %s",
                                extractor.source_name.upper(),
                                inserted,
                                checkpoint,
                            )
                    else:
                        articles = await extractor.fetch_articles(query, max_results=max_results_per_query)
                        source_fetched = len(articles)
                        logger.info(f"[{extractor.source_name.upper()}] {len(articles)} adet makale bulundu. Veritabanına yazılıyor...")

                        inserted = save_articles_to_db(db, articles, ingestion_run_id=ingestion_run_id)
                        checkpoint_getter = getattr(extractor, "get_state_checkpoint", None)
                        checkpoint = checkpoint_getter() if checkpoint_getter else None
                        if checkpoint is not None:
                            save_state(extractor.source_name, checkpoint)
                        source_inserted += inserted
                        total_inserted += inserted

                    logger.info(
                        "[%s] Başarılı! %s makale çekildi, %s makale eklendi/güncellendi.",
                        extractor.source_name.upper(),
                        source_fetched,
                        source_inserted,
                    )
                    
                except Exception:
                    logger.exception("[%s] Hata olustu", extractor.source_name.upper())
                
                # Rate limitlere (hız sınırlarına) saygı duymak için bekleme süresi
                await asyncio.sleep(2)
                
    finally:
        db.close()
        logger.info(f"=== İŞLEM TAMAMLANDI. Toplam {total_inserted} makale eklendi/güncellendi. ===")

if __name__ == "__main__":
    asyncio.run(main())
