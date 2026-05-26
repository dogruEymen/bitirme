import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


INGESTION_STATE_PATH = Path("ai_engine/ingestion/ingestion_state.json")


def reset_public_schema() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL bulunamadi. .env dosyasina veya shell environment'a ekleyin.")

    engine = create_engine(db_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))


def run_migrations() -> None:
    alembic_cfg = Config("database/alembic.ini")
    command.upgrade(alembic_cfg, "head")


def reset_ingestion_state() -> None:
    INGESTION_STATE_PATH.write_text("{}\n", encoding="utf-8")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Neon/PostgreSQL veritabanini sifirlar, migration'lari bastan uygular."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Geri donussuz schema reset islemini onaylar.",
    )
    parser.add_argument(
        "--keep-ingestion-state",
        action="store_true",
        help="API cursor/offset state dosyasini korur.",
    )
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Bu islem tum public schema'yi siler. Calistirmak icin --yes ekleyin.")

    reset_public_schema()
    run_migrations()

    if not args.keep_ingestion_state:
        reset_ingestion_state()

    print("Database schema resetlendi, migration'lar uygulandi.")
    if not args.keep_ingestion_state:
        print(f"Ingestion state sifirlandi: {INGESTION_STATE_PATH}")


if __name__ == "__main__":
    main()
