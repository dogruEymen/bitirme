"""add user bulletin preferences

Revision ID: a1b2c3d4e5f6
Revises: e7f8a9b0c1d2
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_bulletin_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("selection_type", sa.String(length=20), nullable=False),
        sa.Column("selected_cluster_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("selected_categories_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("bulletin_snapshot_key", sa.String(length=200), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False),
        sa.Column("notification_frequency", sa.String(length=20), nullable=False),
        sa.Column("last_generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_bulletin_preferences_user_id"),
    )
    op.create_index(
        op.f("ix_user_bulletin_preferences_user_id"),
        "user_bulletin_preferences",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_bulletin_preferences_bulletin_snapshot_key"),
        "user_bulletin_preferences",
        ["bulletin_snapshot_key"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_bulletin_preferences_bulletin_snapshot_key"), table_name="user_bulletin_preferences")
    op.drop_index(op.f("ix_user_bulletin_preferences_user_id"), table_name="user_bulletin_preferences")
    op.drop_table("user_bulletin_preferences")
