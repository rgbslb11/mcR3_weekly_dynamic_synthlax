"""v0 initial schema

Revision ID: 0001_initial
Revises: None
"""
from alembic import op

from ncaaf_engine.db import Base
import ncaaf_engine.models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
