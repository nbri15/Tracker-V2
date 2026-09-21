"""Prevent duplicate responses to a Maths Fundamentals question.

Revision ID: 20260909_03
Revises: 20260909_02
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = '20260909_03'
down_revision = '20260909_02'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing_constraints = {
        constraint.get('name')
        for constraint in sa.inspect(bind).get_unique_constraints('fundamental_responses')
    }
    if 'uq_fundamental_response_attempt_question' in existing_constraints:
        return

    duplicate = bind.execute(sa.text(
        """
        SELECT attempt_id, question_id
        FROM fundamental_responses
        GROUP BY attempt_id, question_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )).first()
    if duplicate:
        raise RuntimeError(
            'Duplicate Maths Fundamentals responses exist. Review them before '
            'adding uq_fundamental_response_attempt_question; this migration '
            'will not delete production assessment data automatically.'
        )

    with op.batch_alter_table('fundamental_responses') as batch_op:
        batch_op.create_unique_constraint(
            'uq_fundamental_response_attempt_question',
            ['attempt_id', 'question_id'],
        )


def downgrade():
    bind = op.get_bind()
    existing_constraints = {
        constraint.get('name')
        for constraint in sa.inspect(bind).get_unique_constraints('fundamental_responses')
    }
    if 'uq_fundamental_response_attempt_question' not in existing_constraints:
        return

    with op.batch_alter_table('fundamental_responses') as batch_op:
        batch_op.drop_constraint(
            'uq_fundamental_response_attempt_question',
            type_='unique',
        )
