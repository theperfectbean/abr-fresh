"""add_uuid_column_to_audiobook

Revision ID: a1b2c3d4e5f6
Revises: 9c87a9c6fe7d
Create Date: 2026-01-20 12:00:00.000000

Phase 1 Migration Step 1: Add UUID column to Audiobook table and populate with UUIDs
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9c87a9c6fe7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add UUID column to audiobook table (nullable initially)
    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("id", sa.Uuid(), nullable=True)
        )

    # Populate existing rows with UUIDs
    if op.get_bind().dialect.name == "sqlite":
        # SQLite UUID generation
        op.execute("""
            UPDATE audiobook
            SET id = lower(
                hex(randomblob(4)) || '-' ||
                hex(randomblob(2)) || '-4' ||
                substr(hex(randomblob(2)), 2) || '-' ||
                substr('89ab', abs(random()) % 4 + 1, 1) ||
                substr(hex(randomblob(2)), 2) || '-' ||
                hex(randomblob(6))
            )
        """)
    elif op.get_bind().dialect.name == "postgresql":
        # PostgreSQL UUID generation
        op.execute("UPDATE audiobook SET id = gen_random_uuid() WHERE id IS NULL")
    else:
        raise NotImplementedError("Unsupported database dialect")

    # Make UUID column NOT NULL
    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        batch_op.alter_column("id", nullable=False)
        # Create unique index on id
        batch_op.create_unique_constraint("uq_audiobook_id", ["id"])


def downgrade() -> None:
    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        batch_op.drop_constraint("uq_audiobook_id", type_="unique")
        batch_op.drop_column("id")
