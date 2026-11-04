"""baseline: the user and access token tables

Revision ID: 0001
Revises:
Create Date: 2026-11-04

"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("rooms", sa.JSON(), nullable=False),
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)
    op.create_table(
        "accesstoken",
        sa.Column("user_id", sa.CHAR(36), nullable=False),
        sa.Column("token", sa.String(43), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.PrimaryKeyConstraint("token"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="cascade"),
    )
    op.create_index(op.f("ix_accesstoken_created_at"), "accesstoken", ["created_at"])


def downgrade() -> None:
    op.drop_table("accesstoken")
    op.drop_table("user")
