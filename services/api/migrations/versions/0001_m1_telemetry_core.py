"""Create M1 observation and rejection evidence tables.

Revision ID: 0001_m1_telemetry_core
Revises: None
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_m1_telemetry_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "observations",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_origin", sa.String(length=16), nullable=False),
        sa.Column("source_delivery", sa.String(length=16), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replay_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingest_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quality", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("topic", sa.String(length=512), nullable=False),
        sa.Column("raw_message", sa.LargeBinary(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("is_late", sa.Boolean(), nullable=False),
        sa.Column("clock_skew_detected", sa.Boolean(), nullable=False),
        sa.Column("processing_outcome", sa.String(length=16), nullable=False),
        sa.CheckConstraint("schema_version = '1.0'", name="ck_observations_schema_version"),
        sa.CheckConstraint(
            "source_origin IN ('SYNTHETIC', 'PHYSICAL')",
            name="ck_observations_source_origin",
        ),
        sa.CheckConstraint(
            "source_delivery IN ('LIVE', 'RECORDED')",
            name="ck_observations_source_delivery",
        ),
        sa.CheckConstraint(
            "(source_delivery = 'RECORDED' AND replay_time IS NOT NULL) OR "
            "(source_delivery = 'LIVE' AND replay_time IS NULL)",
            name="ck_observations_replay_time",
        ),
        sa.CheckConstraint(
            "processing_outcome = 'ACCEPTED'",
            name="ck_observations_processing_outcome",
        ),
        sa.CheckConstraint(
            "(payload_type = 'environment.temperature' AND unit = 'Cel') OR "
            "(payload_type = 'environment.relative_humidity' AND unit = '%') OR "
            "(payload_type = 'environment.ammonia_concentration' AND unit = '[ppm]')",
            name="ck_observations_payload_unit",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_observations_ingest_time",
        "observations",
        ["ingest_time"],
        unique=False,
    )
    op.create_index(
        "ix_observations_payload_event_time",
        "observations",
        ["payload_type", "event_time"],
        unique=False,
    )
    op.create_index(
        "ix_observations_source_event_time",
        "observations",
        ["source_id", "event_time"],
        unique=False,
    )

    op.create_table(
        "telemetry_rejections",
        sa.Column("rejection_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("topic", sa.String(length=512), nullable=False),
        sa.Column("event_id_text", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("error_detail", sa.String(length=512), nullable=False),
        sa.Column("raw_message", sa.LargeBinary(), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_truncated", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("rejection_id"),
    )
    op.create_index(
        "ix_telemetry_rejections_error_code",
        "telemetry_rejections",
        ["error_code"],
        unique=False,
    )
    op.create_index(
        "ix_telemetry_rejections_received_at",
        "telemetry_rejections",
        ["received_at"],
        unique=False,
    )


def downgrade() -> None:
    # Destructive by design; use only for isolated local/test rollback.
    op.drop_index("ix_telemetry_rejections_received_at", table_name="telemetry_rejections")
    op.drop_index("ix_telemetry_rejections_error_code", table_name="telemetry_rejections")
    op.drop_table("telemetry_rejections")
    op.drop_index("ix_observations_source_event_time", table_name="observations")
    op.drop_index("ix_observations_payload_event_time", table_name="observations")
    op.drop_index("ix_observations_ingest_time", table_name="observations")
    op.drop_table("observations")
