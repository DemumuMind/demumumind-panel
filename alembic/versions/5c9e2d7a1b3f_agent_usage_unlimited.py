"""agent_usage unlimited column (free & no disclosed limits)

Revision ID: 5c9e2d7a1b3f
Revises: 3a7f1b9c2d5e
Create Date: 2026-09-01 08:40:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5c9e2d7a1b3f"
down_revision: Union[str, None] = "3a7f1b9c2d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_usage") as batch_op:
        batch_op.add_column(sa.Column("unlimited", sa.Integer(), server_default=sa.text("0"), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("agent_usage") as batch_op:
        batch_op.drop_column("unlimited")