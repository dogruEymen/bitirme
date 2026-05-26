"""add article metadata fields

Revision ID: 7c4f2a9d8b31
Revises: 0f279fc188f6
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c4f2a9d8b31'
down_revision: Union[str, Sequence[str], None] = '0f279fc188f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('updated_date', sa.DateTime(), nullable=True))
    op.add_column('articles', sa.Column('url', sa.String(length=500), nullable=True))
    op.add_column('articles', sa.Column('categories', sa.Text(), nullable=True))
    op.add_column('articles', sa.Column('doi', sa.String(length=255), nullable=True))
    op.add_column('articles', sa.Column('citation_count', sa.Integer(), nullable=True))
    op.add_column('articles', sa.Column('venue', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_articles_doi'), 'articles', ['doi'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_articles_doi'), table_name='articles')
    op.drop_column('articles', 'venue')
    op.drop_column('articles', 'citation_count')
    op.drop_column('articles', 'doi')
    op.drop_column('articles', 'categories')
    op.drop_column('articles', 'url')
    op.drop_column('articles', 'updated_date')
