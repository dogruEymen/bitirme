import asyncio
import argparse
from pathlib import Path
import logging

from database.db import SessionLocal
from ai_engine.ingestion.extractors.arxiv_extractor import ArxivExtractor
from ai_engine.ingestion.extractors.openalex_extractor import OpenAlexExtractor
from ai_engine.ingestion.extractors.s2_extractor import SemanticScholarExtractor
from ai_engine.ingestion.loader import save_articles_to_db

# Log ayarları
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

INGESTION_STATE_PATH = Path("ai_engine/ingestion/ingestion_state.json")
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


async def main():
    args = parse_args()
    if args.reset_state:
        reset_ingestion_state()
        logger.info("Ingestion state sifirlandi: %s", INGESTION_STATE_PATH)

    # Özel bir anahtar kelime olmadan (boş sorgu) tüm Computer Science makalelerini çekmek istiyoruz
    queries = args.query if args.query is not None else [""]
    
    extractors = build_extractors(args.sources)
    
    max_results_per_query = args.max_results
    total_inserted = 0

    logger.info("=== MAKALE ÇEKİMİ BAŞLIYOR ===")
    logger.info("Uyarı: Sistem 'ingestion_state.json' dosyasını kontrol ederek kaldığı yerden devam edecektir.")

    # Veritabanı bağlantısını başlat
    db = SessionLocal()

    try:
        for query in queries:
            logger.info(f"=== SORGULANIYOR: '{query}' ===")
            for extractor in extractors:
                logger.info(f"[{extractor.source_name.upper()}] API'sine istek atılıyor...")
                try:
                    # 1. Extract
                    articles = await extractor.fetch_articles(query, max_results=max_results_per_query)
                    logger.info(f"[{extractor.source_name.upper()}] {len(articles)} adet makale bulundu. Veritabanına yazılıyor...")
                    
                    # 2. Load
                    inserted = save_articles_to_db(db, articles)
                    total_inserted += inserted
                    logger.info(f"[{extractor.source_name.upper()}] Başarılı! {inserted} makale eklendi/güncellendi.")
                    
                except Exception as e:
                    logger.error(f"[{extractor.source_name.upper()}] Hata oluştu: {e}")
                
                # Rate limitlere (hız sınırlarına) saygı duymak için bekleme süresi
                await asyncio.sleep(2)
                
    finally:
        db.close()
        logger.info(f"=== İŞLEM TAMAMLANDI. Toplam {total_inserted} makale eklendi/güncellendi. ===")

if __name__ == "__main__":
    asyncio.run(main())
