"""fix chat message role constraint

Revision ID: b8a2f67d4c91
Revises: 7c4f2a9d8b31
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8a2f67d4c91'
down_revision: Union[str, Sequence[str], None] = '7c4f2a9d8b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE chat_messages SET role = 'agent' WHERE role = 'assistant'")
    op.create_check_constraint(
        "check_chat_message_role",
        "chat_messages",
        "role IN ('user', 'agent')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "check_chat_message_role",
        "chat_messages",
        type_="check",
    )
