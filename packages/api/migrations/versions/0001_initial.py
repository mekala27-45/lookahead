"""forecasts, their rows, scores, models and the audit log

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("forecast_id", sa.String(), nullable=False),
        sa.Column("authority", sa.String(), nullable=False),
        sa.Column("origin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("backend", sa.String(), nullable=False),
        sa.Column("spec_hash", sa.String(), nullable=False),
        sa.Column("data_source", sa.String(), nullable=False),
        sa.Column("horizons", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scored_rows", sa.Integer(), nullable=False),
    )
    op.create_index("ix_forecasts_forecast_id", "forecasts", ["forecast_id"], unique=True)
    op.create_index("ix_forecasts_authority", "forecasts", ["authority"])
    op.create_index("ix_forecasts_origin", "forecasts", ["origin"])
    op.create_table(
        "forecast_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("forecast_id", sa.String(), sa.ForeignKey("forecasts.forecast_id"), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("target_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("q05", sa.Float(), nullable=False),
        sa.Column("q25", sa.Float(), nullable=False),
        sa.Column("q50", sa.Float(), nullable=False),
        sa.Column("q75", sa.Float(), nullable=False),
        sa.Column("q95", sa.Float(), nullable=False),
    )
    op.create_index("ix_forecast_rows_forecast_id", "forecast_rows", ["forecast_id"])
    op.create_table(
        "scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("forecast_id", sa.String(), sa.ForeignKey("forecasts.forecast_id"), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("target_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual", sa.Float(), nullable=False),
        sa.Column("abs_pct_error", sa.Float(), nullable=False),
        sa.Column("inside_50", sa.Boolean(), nullable=False),
        sa.Column("inside_90", sa.Boolean(), nullable=False),
        sa.Column("pinball_q05", sa.Float(), nullable=False),
        sa.Column("pinball_q25", sa.Float(), nullable=False),
        sa.Column("pinball_q50", sa.Float(), nullable=False),
        sa.Column("pinball_q75", sa.Float(), nullable=False),
        sa.Column("pinball_q95", sa.Float(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scores_forecast_id", "scores", ["forecast_id"])
    op.create_table(
        "models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("backend", sa.String(), nullable=False),
        sa.Column("spec_hash", sa.String(), nullable=False),
        sa.Column("served", sa.Boolean(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_models_version", "models", ["version"], unique=True)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    for name in ("audit_log", "models", "scores", "forecast_rows", "forecasts"):
        op.drop_table(name)
