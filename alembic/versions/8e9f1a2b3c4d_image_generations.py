"""image_generations history table

Revision ID: 8e9f1a2b3c4d
Revises: 7d1e2f3a4b5c
Create Date: 2026-09-01 17:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8e9f1a2b3c4d"
down_revision: Union[str, None] = "7d1e2f3a4b5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_generations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("size", sa.String(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_image_generations_agent_type"), "image_generations", ["agent_type"], unique=False)
    op.create_index(op.f("ix_image_generations_created_at"), "image_generations", ["created_at"], unique=False)
    op.create_index(op.f("ix_image_generations_provider_id"), "image_generations", ["provider_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_image_generations_provider_id"), table_name="image_generations")
    op.drop_index(op.f("ix_image_generations_created_at"), table_name="image_generations")
    op.drop_index(op.f("ix_image_generations_agent_type"), table_name="image_generations")
    op.drop_table("image_generations")