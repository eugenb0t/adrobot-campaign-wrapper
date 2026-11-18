"""Create the campaign workspace table."""
from alembic import op
import sqlalchemy as sa

revision = "001_campaigns"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("traffic_source_id", sa.Integer(), nullable=True),
        sa.Column("keitaro_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("offers", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("visits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaigns_name", "campaigns", ["name"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_name", table_name="campaigns")
    op.drop_table("campaigns")
