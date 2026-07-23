# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 Wave 5: ITP hold points, EVM forecast alerts, clash profiles,
compliance rule packs, agent automation, takt scheduling.

Consolidated migration for the six Wave 5 items that touch schema. The embedded
PostgreSQL runtime materialises all of this via create_all at startup; this
migration covers external-PostgreSQL deployments that manage schema with Alembic.
Every change is inspector-guarded so a re-run, or a DB the runtime already
auto-created, is a no-op. GUID columns are VARCHAR(36) (the app.database.GUID
TypeDecorator impl); sa.JSON() compiles to JSONB on PostgreSQL via the codebase
@compiles hook.

Revision ID: v3157_wave5_top30
Revises: v3156_payroll_batches
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3157_wave5_top30"
down_revision = "v3156_payroll_batches"
branch_labels = None
depends_on = None


def _cols(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # ---------------------------------------------------------------- #12 QMS
    itp = _cols(insp, "oe_qms_itp_item")
    if itp:
        if "boq_position_id" not in itp:
            op.add_column("oe_qms_itp_item", sa.Column("boq_position_id", sa.String(length=36), nullable=True))
        if "csi_section_ref" not in itp:
            op.add_column("oe_qms_itp_item", sa.Column("csi_section_ref", sa.String(length=64), nullable=True))
        if "spec_drawing_ref" not in itp:
            op.add_column("oe_qms_itp_item", sa.Column("spec_drawing_ref", sa.String(length=255), nullable=True))
        if "bim_element_id" not in itp:
            op.add_column("oe_qms_itp_item", sa.Column("bim_element_id", sa.String(length=255), nullable=True))
        if "predecessor_itp_item_id" not in itp:
            op.add_column("oe_qms_itp_item", sa.Column("predecessor_itp_item_id", sa.String(length=36), nullable=True))
            op.create_index(
                "ix_oe_qms_itp_item_predecessor_itp_item_id", "oe_qms_itp_item", ["predecessor_itp_item_id"]
            )
            op.create_foreign_key(
                "fk_qms_itp_item_predecessor",
                "oe_qms_itp_item",
                "oe_qms_itp_item",
                ["predecessor_itp_item_id"],
                ["id"],
                ondelete="SET NULL",
            )

    insp_cols = _cols(insp, "oe_qms_inspection")
    if insp_cols and "attachment_document_ids" not in insp_cols:
        op.add_column(
            "oe_qms_inspection", sa.Column("attachment_document_ids", sa.JSON(), nullable=False, server_default="[]")
        )

    sig = _cols(insp, "oe_qms_inspection_signature")
    if sig:
        if "timestamp_utc" not in sig:
            op.add_column(
                "oe_qms_inspection_signature", sa.Column("timestamp_utc", sa.String(length=32), nullable=True)
            )
        if "signer_ip" not in sig:
            op.add_column("oe_qms_inspection_signature", sa.Column("signer_ip", sa.String(length=64), nullable=True))
        if "signer_user_agent" not in sig:
            op.add_column(
                "oe_qms_inspection_signature", sa.Column("signer_user_agent", sa.String(length=512), nullable=True)
            )
        if "signature_token" not in sig:
            op.add_column(
                "oe_qms_inspection_signature", sa.Column("signature_token", sa.String(length=255), nullable=True)
            )

    if "oe_qms_inspection_attachment" not in tables:
        op.create_table(
            "oe_qms_inspection_attachment",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("inspection_id", sa.String(length=36), nullable=False),
            sa.Column("document_id", sa.String(length=36), nullable=False),
            sa.Column("caption", sa.String(length=500), nullable=True),
            sa.Column("file_hash_sha256", sa.String(length=64), nullable=True),
            sa.Column("uploaded_by", sa.String(length=36), nullable=True),
            sa.Column("attached_at", sa.String(length=32), nullable=True),
            sa.ForeignKeyConstraint(["inspection_id"], ["oe_qms_inspection.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_oe_qms_inspection_attachment_inspection_id", "oe_qms_inspection_attachment", ["inspection_id"]
        )
        op.create_index("ix_oe_qms_inspection_attachment_document_id", "oe_qms_inspection_attachment", ["document_id"])

    if "oe_qms_hold_point_release" not in tables:
        op.create_table(
            "oe_qms_hold_point_release",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("inspection_id", sa.String(length=36), nullable=False, unique=True),
            sa.Column("released_by", sa.String(length=36), nullable=True),
            sa.Column("released_at", sa.String(length=32), nullable=True),
            sa.Column("justification", sa.Text(), nullable=True),
            sa.Column("approval_route_id", sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(["inspection_id"], ["oe_qms_inspection.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_oe_qms_hold_point_release_inspection_id", "oe_qms_hold_point_release", ["inspection_id"])

    # ----------------------------------------------------- #19 EVM forecast alerts
    evm = _cols(insp, "oe_evm_forecast")
    if evm:
        if "alert_status" not in evm:
            op.add_column("oe_evm_forecast", sa.Column("alert_status", sa.String(length=32), nullable=True))
        if "triggered_at" not in evm:
            op.add_column("oe_evm_forecast", sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True))

    # ------------------------------------------------------------ #23 clash profiles
    if "oe_clash_profile" not in tables:
        op.create_table(
            "oe_clash_profile",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("clash_type", sa.String(length=16), nullable=False, server_default="both"),
            sa.Column("ignore_same_model", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("tolerance_m", sa.Float(), nullable=False, server_default="0.01"),
            sa.Column("clearance_m", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("mode", sa.String(length=32), nullable=False, server_default="cross_discipline"),
            sa.Column("discipline_filter", sa.JSON(), nullable=True),
            sa.Column("set_a", sa.JSON(), nullable=True),
            sa.Column("set_b", sa.JSON(), nullable=True),
            sa.Column("rules", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("spatial_grid_mm", sa.Integer(), nullable=False, server_default="500"),
            sa.Column("created_by", sa.String(length=64), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["project_id"], ["oe_projects_project.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", "name", name="uq_clash_profile_project_name"),
        )
        op.create_index("ix_clash_profile_project", "oe_clash_profile", ["project_id"])

    clash_result = _cols(insp, "oe_clash_result")
    if clash_result:
        if "a_element_system" not in clash_result:
            op.add_column(
                "oe_clash_result",
                sa.Column("a_element_system", sa.String(length=100), nullable=False, server_default=""),
            )
        if "b_element_system" not in clash_result:
            op.add_column(
                "oe_clash_result",
                sa.Column("b_element_system", sa.String(length=100), nullable=False, server_default=""),
            )

    # ---------------------------------------------- #27 compliance rule packs
    proj = _cols(insp, "oe_projects_project")
    if proj and "compliance_rule_packs" not in proj:
        op.add_column(
            "oe_projects_project",
            sa.Column("compliance_rule_packs", sa.JSON(), nullable=False, server_default='["universal"]'),
        )

    # ------------------------------------------------- #29 agent automation
    agents = _cols(insp, "oe_ai_agents_custom")
    if agents and "automation" not in agents:
        op.add_column("oe_ai_agents_custom", sa.Column("automation", sa.JSON(), nullable=False, server_default="{}"))

    # -------------------------------------------------------- #30 takt scheduling
    if "oe_schedule_advanced_takt_schedule" not in tables:
        op.create_table(
            "oe_schedule_advanced_takt_schedule",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("master_schedule_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("target_cycle_days", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("takt_rhythm_tolerance_days", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("location_sequence_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(
                ["master_schedule_id"], ["oe_schedule_advanced_master_schedule.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_oe_schedule_advanced_takt_schedule_master_schedule_id",
            "oe_schedule_advanced_takt_schedule",
            ["master_schedule_id"],
        )

    if "oe_schedule_advanced_takt_location" not in tables:
        op.create_table(
            "oe_schedule_advanced_takt_location",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("takt_schedule_id", sa.String(length=36), nullable=False),
            sa.Column("sequence_order", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("work_area_sqm", sa.Numeric(precision=12, scale=2), nullable=True),
            sa.ForeignKeyConstraint(
                ["takt_schedule_id"], ["oe_schedule_advanced_takt_schedule.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_oe_schedule_advanced_takt_location_takt_schedule_id",
            "oe_schedule_advanced_takt_location",
            ["takt_schedule_id"],
        )
        op.create_index(
            "ix_oe_schedule_advanced_takt_location_sequence_order",
            "oe_schedule_advanced_takt_location",
            ["sequence_order"],
        )

    if "oe_schedule_advanced_takt_activity" not in tables:
        op.create_table(
            "oe_schedule_advanced_takt_activity",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("takt_schedule_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("activity_code", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("planned_cycle_duration_days", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("crew_size", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("crew_skill_codes", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("buffer_days_before", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sequence_predecessor_activity_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
            sa.Column("actual_cycle_duration_days", sa.Numeric(precision=6, scale=2), nullable=True),
            sa.ForeignKeyConstraint(
                ["takt_schedule_id"], ["oe_schedule_advanced_takt_schedule.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["sequence_predecessor_activity_id"], ["oe_schedule_advanced_takt_activity.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_oe_schedule_advanced_takt_activity_takt_schedule_id",
            "oe_schedule_advanced_takt_activity",
            ["takt_schedule_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    for t in (
        "oe_schedule_advanced_takt_activity",
        "oe_schedule_advanced_takt_location",
        "oe_schedule_advanced_takt_schedule",
    ):
        if t in tables:
            op.drop_table(t)

    agents = _cols(insp, "oe_ai_agents_custom")
    if "automation" in agents:
        op.drop_column("oe_ai_agents_custom", "automation")

    proj = _cols(insp, "oe_projects_project")
    if "compliance_rule_packs" in proj:
        op.drop_column("oe_projects_project", "compliance_rule_packs")

    clash_result = _cols(insp, "oe_clash_result")
    for col in ("a_element_system", "b_element_system"):
        if col in clash_result:
            op.drop_column("oe_clash_result", col)
    if "oe_clash_profile" in tables:
        op.drop_table("oe_clash_profile")

    evm = _cols(insp, "oe_evm_forecast")
    for col in ("alert_status", "triggered_at"):
        if col in evm:
            op.drop_column("oe_evm_forecast", col)

    for t in ("oe_qms_hold_point_release", "oe_qms_inspection_attachment"):
        if t in tables:
            op.drop_table(t)
    sig = _cols(insp, "oe_qms_inspection_signature")
    for col in ("timestamp_utc", "signer_ip", "signer_user_agent", "signature_token"):
        if col in sig:
            op.drop_column("oe_qms_inspection_signature", col)
    insp_cols = _cols(insp, "oe_qms_inspection")
    if "attachment_document_ids" in insp_cols:
        op.drop_column("oe_qms_inspection", "attachment_document_ids")
    itp = _cols(insp, "oe_qms_itp_item")
    for col in ("boq_position_id", "csi_section_ref", "spec_drawing_ref", "bim_element_id", "predecessor_itp_item_id"):
        if col in itp:
            op.drop_column("oe_qms_itp_item", col)
