"""Allow imported campaigns to omit unknown GEO and offer metadata."""
from alembic import op
import sqlalchemy as sa

revision = "002_nullable_imports"
down_revision = "001_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.alter_column("country_code", existing_type=sa.String(length=2), nullable=True)
        batch.alter_column("offer_id", existing_type=sa.Integer(), nullable=True)
    op.execute("UPDATE campaigns SET country_code = NULL, offer_id = NULL WHERE keitaro_id IS NOT NULL AND country_code = '--' AND offer_id = 1")


def downgrade() -> None:
    op.execute("UPDATE campaigns SET country_code = '--' WHERE country_code IS NULL")
    op.execute("UPDATE campaigns SET offer_id = 1 WHERE offer_id IS NULL")
    with op.batch_alter_table("campaigns") as batch:
        batch.alter_column("country_code", existing_type=sa.String(length=2), nullable=False)
        batch.alter_column("offer_id", existing_type=sa.Integer(), nullable=False)
