"""analysis tables: extraction, results, evaluation, discovery, think-first

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_dt = sa.DateTime(timezone=True)


def _fk(table: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{table}.id", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "extracted_fields",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("paper_id", sa.Integer, _fk("papers"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("pass_a", sa.JSON, nullable=False),
        sa.Column("pass_b", sa.JSON, nullable=False),
        sa.Column("created_at", _dt, nullable=False),
        sa.Column("updated_at", _dt, nullable=False),
    )
    op.create_index("ix_extracted_fields_paper_id", "extracted_fields", ["paper_id"])
    op.create_index("ix_extracted_fields_status", "extracted_fields", ["status"])
    op.create_table(
        "result_rows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("paper_id", sa.Integer, _fk("papers"), nullable=False),
        sa.Column("method", sa.String(200), nullable=False),
        sa.Column("dataset", sa.String(200), nullable=False),
        sa.Column("metric", sa.String(120), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
    )
    op.create_index("ix_result_rows_paper_id", "result_rows", ["paper_id"])
    op.create_table(
        "eval_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, _fk("projects"), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answerable", sa.Boolean, nullable=False),
        sa.Column("expected_paper_id", sa.Integer, nullable=True),
        sa.Column("expected_page", sa.Integer, nullable=True),
        sa.Column("expected_snippet", sa.Text, nullable=False),
    )
    op.create_index("ix_eval_questions_project_id", "eval_questions", ["project_id"])
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, _fk("projects"), nullable=False),
        sa.Column("created_at", _dt, nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("n_questions", sa.Integer, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
    )
    op.create_index("ix_eval_runs_project_id", "eval_runs", ["project_id"])
    op.create_table(
        "search_receipts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, _fk("projects"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("input_text", sa.Text, nullable=False),
        sa.Column("queries", sa.JSON, nullable=False),
        sa.Column("sources_searched", sa.JSON, nullable=False),
        sa.Column("sources_not_searched", sa.JSON, nullable=False),
        sa.Column("counts", sa.JSON, nullable=False),
        sa.Column("results", sa.JSON, nullable=False),
        sa.Column("online", sa.Boolean, nullable=False),
        sa.Column("created_at", _dt, nullable=False),
    )
    op.create_index("ix_search_receipts_project_id", "search_receipts", ["project_id"])
    op.create_table(
        "reading_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, _fk("projects"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", sa.String(500), nullable=False),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("venue", sa.String(200), nullable=False),
        sa.Column("url", sa.String(600), nullable=False),
        sa.Column("why", sa.Text, nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("paper_id", sa.Integer, nullable=True),
        sa.Column("created_at", _dt, nullable=False),
    )
    op.create_index("ix_reading_items_project_id", "reading_items", ["project_id"])
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, _fk("projects"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("method", sa.String(200), nullable=False),
        sa.Column("dataset", sa.String(200), nullable=False),
        sa.Column("metric", sa.String(120), nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("created_at", _dt, nullable=False),
    )
    op.create_index("ix_decisions_project_id", "decisions", ["project_id"])
    op.create_table(
        "decision_alerts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("decision_id", sa.Integer, _fk("decisions"), nullable=False),
        sa.Column("paper_id", sa.Integer, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("quote", sa.JSON, nullable=False),
        sa.Column("resolved", sa.Boolean, nullable=False),
        sa.Column("created_at", _dt, nullable=False),
    )
    op.create_index("ix_decision_alerts_decision_id", "decision_alerts", ["decision_id"])
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, _fk("projects"), nullable=False),
        sa.Column("paper_ids", sa.JSON, nullable=False),
        sa.Column("prediction", sa.Text, nullable=False),
        sa.Column("reflection", sa.Text, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("created_at", _dt, nullable=False),
    )
    op.create_index("ix_predictions_project_id", "predictions", ["project_id"])
    op.create_table(
        "prov_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, _fk("projects"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("marks", sa.JSON, nullable=False),
        sa.Column("created_at", _dt, nullable=False),
        sa.Column("updated_at", _dt, nullable=False),
    )
    op.create_index("ix_prov_documents_project_id", "prov_documents", ["project_id"])
    op.create_table(
        "prov_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.Integer, _fk("prov_documents"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("passage", sa.Text, nullable=False),
        sa.Column("words", sa.Integer, nullable=False),
        sa.Column("created_at", _dt, nullable=False),
    )
    op.create_index("ix_prov_events_document_id", "prov_events", ["document_id"])


def downgrade() -> None:
    for t in [
        "prov_events", "prov_documents", "predictions", "decision_alerts", "decisions", "reading_items",
        "search_receipts", "eval_runs", "eval_questions", "result_rows", "extracted_fields",
    ]:
        op.drop_table(t)
