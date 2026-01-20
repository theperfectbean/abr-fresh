"""update_audiobookrequest_to_use_uuid

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-01-20 12:10:00.000000

Phase 1 Migration Step 2: Create new AudiobookRequest table with UUID foreign key
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create new audiobookrequest table with UUID foreign key
    op.create_table(
        "audiobookrequest_v2",
        sa.Column("audiobook_id", sa.Uuid(), nullable=False),
        sa.Column("user_username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["audiobook_id"], ["audiobook.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_username"], ["user.username"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("audiobook_id", "user_username"),
    )

    # Copy data from old table to new table, using audiobook.id lookup
    op.execute("""
        INSERT INTO audiobookrequest_v2 (audiobook_id, user_username, updated_at)
        SELECT a.id, ar.user_username, ar.updated_at
        FROM audiobookrequest ar
        JOIN audiobook a ON ar.asin = a.asin
    """)

    # Drop old table and rename new one
    op.drop_table("audiobookrequest")
    op.rename_table("audiobookrequest_v2", "audiobookrequest")


def downgrade() -> None:
    # Rename table back
    op.rename_table("audiobookrequest", "audiobookrequest_v2")

    # Recreate old table
    op.create_table(
        "audiobookrequest",
        sa.Column("asin", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asin"], ["audiobook.asin"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_username"], ["user.username"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("asin", "user_username"),
    )

    # Copy data back
    op.execute("""
        INSERT INTO audiobookrequest (asin, user_username, updated_at)
        SELECT a.asin, ar.user_username, ar.updated_at
        FROM audiobookrequest_v2 ar
        JOIN audiobook a ON ar.audiobook_id = a.id
    """)

    # Drop new table
    op.drop_table("audiobookrequest_v2")
