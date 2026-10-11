"""initial schema + FTS5 keyword index

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("question", sa.Text, nullable=False, server_default=""),
        sa.Column("think_first", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "papers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", sa.String(500), nullable=False, server_default=""),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("venue", sa.String(200), nullable=False, server_default=""),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("file_path", sa.String(600), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(64), nullable=False, server_default=""),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("detail", sa.String(400), nullable=False, server_default=""),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedded_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "sha256", name="uq_paper_project_sha"),
    )
    op.create_index("ix_papers_project_id", "papers", ["project_id"])
    op.create_index("ix_papers_status", "papers", ["status"])
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("paper_id", sa.Integer, sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.UniqueConstraint("paper_id", "number", name="uq_page_paper_number"),
    )
    op.create_index("ix_pages_paper_id", "pages", ["paper_id"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("paper_id", sa.Integer, sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", sa.LargeBinary, nullable=True),
        sa.Column("embedding_model", sa.String(120), nullable=True),
    )
    op.create_index("ix_chunks_paper_id", "chunks", ["paper_id"])
    op.create_table(
        "threads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("starred", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_threads_project_id", "threads", ["project_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("thread_id", sa.Integer, sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="answered"),
        sa.Column("citations", sa.JSON, nullable=False),
        sa.Column("meta", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_thread_id", "messages", ["thread_id"])
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )

    # Keyword index (SQLite FTS5), kept in sync with chunks by triggers.
    op.execute("CREATE VIRTUAL TABLE chunk_fts USING fts5(text, content='chunks', content_rowid='id', tokenize='porter unicode61')")
    op.execute(
        "CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN "
        "INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.text); END"
    )
    op.execute(
        "CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN "
        "INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.text); END"
    )
    op.execute(
        "CREATE TRIGGER chunks_au AFTER UPDATE OF text ON chunks BEGIN "
        "INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.text); "
        "INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.text); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS chunks_au")
    op.execute("DROP TRIGGER IF EXISTS chunks_ad")
    op.execute("DROP TRIGGER IF EXISTS chunks_ai")
    op.execute("DROP TABLE IF EXISTS chunk_fts")
    for t in ["app_settings", "messages", "threads", "chunks", "pages", "papers", "projects", "users"]:
        op.drop_table(t)
