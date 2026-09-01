"""agent_usage pricing columns (model_id, is_free, price_known, cache_hit)

Revision ID: 3a7f1b9c2d5e
Revises: bd3bc1e9bf9e
Create Date: 2026-09-01 07:30:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3a7f1b9c2d5e"
down_revision: Union[str, None] = "bd3bc1e9bf9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_usage") as batch_op:
        batch_op.add_column(sa.Column("model_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("is_free", sa.Integer(), server_default=sa.text("0"), nullable=False))
        batch_op.add_column(sa.Column("price_known", sa.Integer(), server_default=sa.text("0"), nullable=False))
        batch_op.add_column(sa.Column("cache_hit", sa.Integer(), server_default=sa.text("0"), nullable=False))
        batch_op.create_index("ix_agent_usage_model_id", ["model_id"])
        batch_op.create_foreign_key("fk_agent_usage_model", "models", ["model_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("agent_usage") as batch_op:
        batch_op.drop_constraint("fk_agent_usage_model", type_="foreignkey")
        batch_op.drop_index("ix_agent_usage_model_id")
        batch_op.drop_column("cache_hit")
        batch_op.drop_column("price_known")
        batch_op.drop_column("is_free")
        batch_op.drop_column("model_id")