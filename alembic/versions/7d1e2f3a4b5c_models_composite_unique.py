"""models composite unique (provider_id, user_model_id)

Revision ID: 7d1e2f3a4b5c
Revises: 5c9e2d7a1b3f
Create Date: 2026-09-01 15:30:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "7d1e2f3a4b5c"
down_revision: Union[str, None] = "5c9e2d7a1b3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # user_model_id was globally UNIQUE (routing key). Allow the same alias
    # across providers via a composite unique on (provider_id, user_model_id)
    # so a second provider can import gpt-4o without IntegrityError.
    with op.batch_alter_table("models") as batch_op:
        batch_op.drop_index("ix_models_user_model_id")
        batch_op.create_unique_constraint(
            "uq_models_provider_user", ["provider_id", "user_model_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("models") as batch_op:
        batch_op.drop_constraint("uq_models_provider_user", type_="unique")
        batch_op.create_index("ix_models_user_model_id", ["user_model_id"], unique=True)