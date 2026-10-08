"""
Database constraint tests for course_ratings table.
Tests actual database constraints (requires test database).
"""
import threading
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from app.db.base import SessionLocal
from app.models.course import Course
from app.models.course_rating import CourseRating
from app.services.course_service import CourseService


@pytest.fixture
def db_session():
    """Create database session for testing."""
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_course(db_session):
    """Create and persist sample course."""
    course = Course(
        name="Test Course",
        description="Test Description",
        thumbnail="https://example.com/thumb.jpg",
        slug=f"test-course-{datetime.utcnow().timestamp()}"
    )
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    course_id = course.id
    yield course

    # Cleanup: tests run against the development DB, so remove test data
    db_session.rollback()
    db_session.query(CourseRating).filter(
        CourseRating.course_id == course_id
    ).delete()
    db_session.query(Course).filter(Course.id == course_id).delete()
    db_session.commit()


class TestRatingConstraints:
    """Tests for database constraints on course_ratings table."""

    def test_rating_check_constraint_min(self, db_session, sample_course):
        """Test CHECK constraint prevents rating < 1."""
        # Arrange
        rating = CourseRating(
            course_id=sample_course.id,
            user_id=42,
            rating=0  # Invalid: below minimum
        )
        db_session.add(rating)

        # Act & Assert
        with pytest.raises(IntegrityError, match="ck_course_ratings_rating_range"):
            db_session.commit()

    def test_rating_check_constraint_max(self, db_session, sample_course):
        """Test CHECK constraint prevents rating > 5."""
        # Arrange
        rating = CourseRating(
            course_id=sample_course.id,
            user_id=42,
            rating=6  # Invalid: above maximum
        )
        db_session.add(rating)

        # Act & Assert
        with pytest.raises(IntegrityError, match="ck_course_ratings_rating_range"):
            db_session.commit()

    def test_unique_constraint_prevents_duplicate_active_ratings(
        self,
        db_session,
        sample_course
    ):
        """Test partial UNIQUE index prevents multiple active ratings from same user.

        In PostgreSQL NULL != NULL, so a plain UNIQUE including deleted_at would not
        fire; the index is partial (WHERE deleted_at IS NULL) instead.
        """
        # Arrange - Create first rating
        rating1 = CourseRating(
            course_id=sample_course.id,
            user_id=42,
            rating=5
        )
        db_session.add(rating1)
        db_session.commit()

        # Act - Try to create duplicate
        rating2 = CourseRating(
            course_id=sample_course.id,
            user_id=42,  # Same user
            rating=3
        )
        db_session.add(rating2)

        # Assert
        with pytest.raises(IntegrityError, match="uq_course_ratings_active_user_course"):
            db_session.commit()

    def test_unique_constraint_allows_soft_deleted_duplicates(
        self,
        db_session,
        sample_course
    ):
        """Test UNIQUE constraint allows creating new rating after soft delete."""
        # Arrange - Create and soft delete first rating
        rating1 = CourseRating(
            course_id=sample_course.id,
            user_id=42,
            rating=5
        )
        db_session.add(rating1)
        db_session.commit()

        rating1.deleted_at = datetime.utcnow()
        db_session.commit()

        # Act - Create new rating (should succeed)
        rating2 = CourseRating(
            course_id=sample_course.id,
            user_id=42,  # Same user, but previous is deleted
            rating=3
        )
        db_session.add(rating2)
        db_session.commit()

        # Assert
        db_session.refresh(rating2)
        assert rating2.id is not None
        assert rating2.rating == 3

    def test_multiple_soft_deleted_and_one_active_coexist(
        self,
        db_session,
        sample_course
    ):
        """Two soft-deleted ratings and one active rating can coexist."""
        now = datetime.utcnow()
        db_session.add_all([
            CourseRating(course_id=sample_course.id, user_id=42, rating=1, deleted_at=now),
            CourseRating(course_id=sample_course.id, user_id=42, rating=2, deleted_at=now),
            CourseRating(course_id=sample_course.id, user_id=42, rating=5),
        ])
        db_session.commit()

        active = db_session.query(CourseRating).filter(
            CourseRating.course_id == sample_course.id,
            CourseRating.user_id == 42,
            CourseRating.deleted_at.is_(None)
        ).count()
        assert active == 1

    def test_service_add_rating_twice_keeps_single_active_row(
        self,
        db_session,
        sample_course
    ):
        """Two consecutive add_course_rating calls leave one active row."""
        service = CourseService(db_session)

        first = service.add_course_rating(sample_course.id, 42, 5)
        second = service.add_course_rating(sample_course.id, 42, 3)

        assert first["id"] == second["id"]
        rows = db_session.query(CourseRating).filter(
            CourseRating.course_id == sample_course.id,
            CourseRating.user_id == 42,
            CourseRating.deleted_at.is_(None)
        ).all()
        assert len(rows) == 1
        assert rows[0].rating == 3

    def test_foreign_key_constraint(self, db_session):
        """Test foreign key constraint to courses table."""
        # Arrange - Create rating with non-existent course_id
        rating = CourseRating(
            course_id=99999,  # Non-existent course
            user_id=42,
            rating=5
        )
        db_session.add(rating)

        # Act & Assert
        with pytest.raises(IntegrityError, match="fk_course_ratings_course_id"):
            db_session.commit()


class TestConcurrentRatings:
    """Concurrent add_course_rating calls for the same (course, user)."""

    def test_concurrent_add_rating_same_user_keeps_single_active_row(
        self,
        db_session,
        sample_course
    ):
        """Two threads (one session each) race to create the same rating.

        Both calls must succeed (the loser falls back to UPDATE after the
        IntegrityError) and exactly one active row must remain.
        """
        course_id = sample_course.id
        barrier = threading.Barrier(2)
        results = {}
        errors = []

        def worker(rating_value):
            session = SessionLocal()  # Sessions are not thread-safe: one per thread
            try:
                barrier.wait(timeout=10)
                results[rating_value] = CourseService(session).add_course_rating(
                    course_id, 77, rating_value
                )
            except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
                errors.append(exc)
            finally:
                session.close()

        threads = [threading.Thread(target=worker, args=(value,)) for value in (2, 4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == []
        assert len(results) == 2

        db_session.expire_all()
        rows = db_session.query(CourseRating).filter(
            CourseRating.course_id == course_id,
            CourseRating.user_id == 77,
            CourseRating.deleted_at.is_(None)
        ).all()
        assert len(rows) == 1
        assert rows[0].rating in (2, 4)
