"""Persistir la aceptación de privacidad exigida en el registro público.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-26
"""

from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "usuario",
        sa.Column(
            "acepta_privacidad",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("usuario", "acepta_privacidad")
