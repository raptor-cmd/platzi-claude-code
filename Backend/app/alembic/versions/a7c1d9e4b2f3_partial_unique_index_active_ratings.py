"""partial unique index for active course ratings

Revision ID: a7c1d9e4b2f3
Revises: 0e3a8766f785
Create Date: 2026-10-06 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c1d9e4b2f3'
down_revision: Union[str, None] = '0e3a8766f785'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enforce one active rating per user/course at DB level.

    UNIQUE(course_id, user_id, deleted_at) never fires while deleted_at IS NULL
    (NULL != NULL in PostgreSQL), so replace it with a partial unique index.

    Before creating the index, existing duplicate active ratings are cleaned up:
    the most recent one per (course_id, user_id) is kept and the rest are
    soft-deleted (recoverable, since deleted_at is only set).
    """
    op.execute(
        """
        UPDATE course_ratings
        SET deleted_at = NOW()
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY course_id, user_id
                           ORDER BY updated_at DESC, id DESC
                       ) AS rn
                FROM course_ratings
                WHERE deleted_at IS NULL
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    )
    op.drop_constraint(
        'uq_course_ratings_user_course_deleted',
        'course_ratings',
        type_='unique'
    )
    op.create_index(
        'uq_course_ratings_active_user_course',
        'course_ratings',
        ['course_id', 'user_id'],
        unique=True,
        postgresql_where='deleted_at IS NULL'
    )


def downgrade() -> None:
    """Restore the old (ineffective) constraint and drop the partial index.

    Duplicates soft-deleted by upgrade() are NOT restored.
    """
    op.drop_index('uq_course_ratings_active_user_course', table_name='course_ratings')
    op.create_unique_constraint(
        'uq_course_ratings_user_course_deleted',
        'course_ratings',
        ['course_id', 'user_id', 'deleted_at']
    )
