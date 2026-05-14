"""normalize pupil gender values

Revision ID: 20260514_01
Revises: 20260512_04
Create Date: 2026-05-14
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '20260514_01'
down_revision = '20260512_04'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE pupils
        SET gender = 'Male'
        WHERE lower(trim(coalesce(gender, ''))) IN ('m', 'male')
    """)
    op.execute("""
        UPDATE pupils
        SET gender = 'Female'
        WHERE lower(trim(coalesce(gender, ''))) IN ('f', 'female')
    """)
    op.execute("""
        UPDATE pupils
        SET gender = ''
        WHERE lower(trim(coalesce(gender, ''))) NOT IN ('male', 'female', '')
    """)


def downgrade():
    # lossy normalization; leave canonical values unchanged
    pass
