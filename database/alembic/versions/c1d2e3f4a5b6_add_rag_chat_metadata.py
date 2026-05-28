"""add rag chat metadata

Revision ID: c1d2e3f4a5b6
Revises: b8a2f67d4c91
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b8a2f67d4c91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR")

    op.add_column("articles", sa.Column("embedding_model", sa.String(length=120), nullable=True))
    op.add_column("articles", sa.Column("embedding_text_hash", sa.String(length=64), nullable=True))
    op.add_column("articles", sa.Column("embedding_created_at", sa.DateTime(), nullable=True))
    op.add_column("articles", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("articles", sa.Column("language", sa.String(length=20), nullable=True))
    op.add_column("articles", sa.Column("document_type", sa.String(length=50), nullable=True))
    op.add_column("articles", sa.Column("ingestion_run_id", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_articles_embedding_text_hash"), "articles", ["embedding_text_hash"], unique=False)
    op.create_index(op.f("ix_articles_language"), "articles", ["language"], unique=False)
    op.create_index(op.f("ix_articles_document_type"), "articles", ["document_type"], unique=False)
    op.create_index(op.f("ix_articles_ingestion_run_id"), "articles", ["ingestion_run_id"], unique=False)
    op.create_index(op.f("ix_articles_publish_date"), "articles", ["publish_date"], unique=False)
    op.create_index(op.f("ix_articles_primary_category"), "articles", ["primary_category"], unique=False)

    op.add_column("chat_sessions", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("chat_sessions", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("chat_sessions", sa.Column("summary_updated_at", sa.DateTime(), nullable=True))
    op.add_column("chat_sessions", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column("chat_sessions", sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))

    op.add_column("chat_messages", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column("chat_messages", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f("ix_chat_messages_created_at"), "chat_messages", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_chat_messages_created_at"), table_name="chat_messages")
    op.drop_column("chat_messages", "metadata_json")
    op.drop_column("chat_messages", "created_at")

    op.drop_column("chat_sessions", "updated_at")
    op.drop_column("chat_sessions", "created_at")
    op.drop_column("chat_sessions", "summary_updated_at")
    op.drop_column("chat_sessions", "summary")
    op.drop_column("chat_sessions", "title")

    op.drop_index(op.f("ix_articles_primary_category"), table_name="articles")
    op.drop_index(op.f("ix_articles_publish_date"), table_name="articles")
    op.drop_index(op.f("ix_articles_ingestion_run_id"), table_name="articles")
    op.drop_index(op.f("ix_articles_document_type"), table_name="articles")
    op.drop_index(op.f("ix_articles_language"), table_name="articles")
    op.drop_index(op.f("ix_articles_embedding_text_hash"), table_name="articles")
    op.drop_column("articles", "ingestion_run_id")
    op.drop_column("articles", "document_type")
    op.drop_column("articles", "language")
    op.drop_column("articles", "metadata_json")
    op.drop_column("articles", "embedding_created_at")
    op.drop_column("articles", "embedding_text_hash")
    op.drop_column("articles", "embedding_model")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
