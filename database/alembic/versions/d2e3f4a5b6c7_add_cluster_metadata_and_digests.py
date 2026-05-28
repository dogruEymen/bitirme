"""add cluster metadata and digests

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("clusters", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        "cluster_digests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("highlights_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("representative_article_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cluster_digests_cluster_id"), "cluster_digests", ["cluster_id"], unique=False)
    op.create_index(op.f("ix_cluster_digests_period_start"), "cluster_digests", ["period_start"], unique=False)
    op.create_index(op.f("ix_cluster_digests_period_end"), "cluster_digests", ["period_end"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_cluster_digests_period_end"), table_name="cluster_digests")
    op.drop_index(op.f("ix_cluster_digests_period_start"), table_name="cluster_digests")
    op.drop_index(op.f("ix_cluster_digests_cluster_id"), table_name="cluster_digests")
    op.drop_table("cluster_digests")
    op.drop_column("clusters", "metadata_json")
