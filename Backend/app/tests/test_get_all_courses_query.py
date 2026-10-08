"""
Tests de get_all_courses con SQL real: valores de rating y número de queries.
Corren contra la DB de desarrollo, por lo que limpian lo que crean.
"""
import pytest
from datetime import datetime
from sqlalchemy import event
from app.db.base import SessionLocal, engine
from app.models.course import Course
from app.models.course_rating import CourseRating
from app.services.course_service import CourseService


@pytest.fixture
def db_session():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def three_courses(db_session):
    """Curso sin ratings, curso con ratings y curso con un rating soft-deleted."""
    suffix = datetime.utcnow().timestamp()
    courses = [
        Course(
            name=f"No Ratings {suffix}",
            description="d",
            thumbnail="https://example.com/t.jpg",
            slug=f"no-ratings-{suffix}",
        ),
        Course(
            name=f"With Ratings {suffix}",
            description="d",
            thumbnail="https://example.com/t.jpg",
            slug=f"with-ratings-{suffix}",
        ),
        Course(
            name=f"Deleted Rating {suffix}",
            description="d",
            thumbnail="https://example.com/t.jpg",
            slug=f"deleted-rating-{suffix}",
        ),
    ]
    db_session.add_all(courses)
    db_session.commit()
    ids = [c.id for c in courses]

    db_session.add_all([
        CourseRating(course_id=ids[1], user_id=1, rating=5),
        CourseRating(course_id=ids[1], user_id=2, rating=4),
        CourseRating(course_id=ids[1], user_id=3, rating=4),
        CourseRating(course_id=ids[2], user_id=1, rating=1, deleted_at=datetime.utcnow()),
    ])
    db_session.commit()

    yield ids

    db_session.rollback()
    db_session.query(CourseRating).filter(CourseRating.course_id.in_(ids)).delete(
        synchronize_session=False
    )
    db_session.query(Course).filter(Course.id.in_(ids)).delete(
        synchronize_session=False
    )
    db_session.commit()


class TestGetAllCoursesQuery:

    def test_ratings_values_and_types(self, db_session, three_courses):
        no_ratings_id, with_ratings_id, deleted_id = three_courses

        result = {c["id"]: c for c in CourseService(db_session).get_all_courses()}

        # Los tres cursos aparecen, incluso el que no tiene ratings
        assert {no_ratings_id, with_ratings_id, deleted_id} <= set(result)

        assert result[no_ratings_id]["average_rating"] == 0.0
        assert result[no_ratings_id]["total_ratings"] == 0

        assert result[with_ratings_id]["average_rating"] == 4.33
        assert result[with_ratings_id]["total_ratings"] == 3

        # El rating soft-deleted no cuenta
        assert result[deleted_id]["average_rating"] == 0.0
        assert result[deleted_id]["total_ratings"] == 0

        for course in result.values():
            assert type(course["average_rating"]) is float
            assert type(course["total_ratings"]) is int

    def test_output_fields_unchanged(self, db_session, three_courses):
        course = CourseService(db_session).get_all_courses()[0]
        assert set(course) == {
            "id", "name", "description", "thumbnail", "slug",
            "average_rating", "total_ratings",
        }

    def test_stable_order_by_id(self, db_session, three_courses):
        ids = [c["id"] for c in CourseService(db_session).get_all_courses()]
        assert ids == sorted(ids)

    def test_soft_deleted_course_excluded(self, db_session, three_courses):
        course_id = three_courses[0]
        db_session.query(Course).filter(Course.id == course_id).update(
            {"deleted_at": datetime.utcnow()}
        )
        db_session.commit()

        ids = [c["id"] for c in CourseService(db_session).get_all_courses()]
        assert course_id not in ids

    def test_single_query(self, db_session, three_courses):
        statements = []

        def count(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            CourseService(db_session).get_all_courses()
        finally:
            event.remove(engine, "before_cursor_execute", count)

        assert len(statements) <= 2, statements
