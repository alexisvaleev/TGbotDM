from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BIGINT


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('user_answers', 'user_id', type_=BIGINT, existing_type=sa.Integer())


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('user_answers', 'user_id', type_=sa.Integer(), existing_type=BIGINT)
