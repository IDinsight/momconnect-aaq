"""add llm_response column

Revision ID: 8929d5c246e7
Revises: cda1098017b5
Create Date: 2023-10-20 18:54:03.570127

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8929d5c246e7"
down_revision: Union[str, None] = "cda1098017b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "user-query-responses", sa.Column("llm_response", sa.String(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("user-query-responses", "llm_response")
    # ### end Alembic commands ###