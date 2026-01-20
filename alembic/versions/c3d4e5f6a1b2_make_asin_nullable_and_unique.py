"""make_asin_nullable_and_unique

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-01-20 12:20:00.000000

Phase 1 Migration Step 3: Make ASIN nullable and unique (not primary key)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a1b2"
down_revision: Union[str, None] = "b2c3d4e5f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make ASIN nullable and add unique constraint
    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        # Alter ASIN to be nullable
        batch_op.alter_column("asin", nullable=True)
        # Add unique constraint on ASIN
        batch_op.create_unique_constraint("uq_audiobook_asin", ["asin"])
        # Create index on ASIN for faster lookups
        batch_op.create_index("ix_audiobook_asin", ["asin"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        # Drop index
        batch_op.drop_index("ix_audiobook_asin")
        # Drop unique constraint
        batch_op.drop_constraint("uq_audiobook_asin", type_="unique")
        # Make ASIN NOT NULL again
        batch_op.alter_column("asin", nullable=False)
