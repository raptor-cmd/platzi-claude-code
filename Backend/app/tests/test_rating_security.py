"""
Security tests for rating endpoints: authentication (JWT) and authorization
(a user can only create/update/delete their own ratings).
"""
import time
from unittest.mock import Mock

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app, get_course_service
from app.services.course_service import CourseService

SECRET = "test-secret-with-enough-length-for-hs256"
USER_ID = 100

MOCK_RATING = {
    "id": 1,
    "course_id": 1,
    "user_id": USER_ID,
    "rating": 5,
    "created_at": "2025-10-14T10:30:00",
    "updated_at": "2025-10-14T10:30:00",
}


def make_token(sub=str(USER_ID), secret=SECRET, exp_delta=3600, algorithm="HS256"):
    payload = {"exp": int(time.time()) + exp_delta}
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.fixture
def service():
    mock = Mock(spec=CourseService)
    mock.add_course_rating.return_value = MOCK_RATING
    mock.update_course_rating.return_value = MOCK_RATING
    mock.delete_course_rating.return_value = True
    return mock


@pytest.fixture
def client(service, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", SECRET)
    app.dependency_overrides[get_course_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {make_token()}"}


WRITE_REQUESTS = [
    ("post", "/courses/1/ratings", {"rating": 5}),
    ("put", "/courses/1/ratings/100", {"rating": 5}),
    ("delete", "/courses/1/ratings/100", None),
]


class TestAuthenticationRequired:
    @pytest.mark.parametrize("method,url,body", WRITE_REQUESTS)
    def test_missing_token_returns_401(self, client, service, method, url, body):
        response = getattr(client, method)(url, **({"json": body} if body else {}))
        assert response.status_code == 401
        assert "authentication" in response.json()["detail"].lower()

    @pytest.mark.parametrize("token", [
        "invalid_token",
        make_token(secret="another-secret-with-enough-length-xx"),
        make_token(exp_delta=-10),
        make_token(sub=None),
        make_token(sub="abc"),
        make_token(sub="0"),
    ])
    def test_invalid_token_returns_401(self, client, service, token):
        response = client.post(
            "/courses/1/ratings",
            json={"rating": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        service.add_course_rating.assert_not_called()

    def test_unsigned_token_returns_401(self, client, service):
        token = jwt.encode({"sub": str(USER_ID), "exp": int(time.time()) + 60}, None, algorithm="none")
        response = client.post(
            "/courses/1/ratings",
            json={"rating": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_missing_server_secret_fails_closed(self, client, service, auth, monkeypatch):
        monkeypatch.setattr(settings, "jwt_secret", "")
        response = client.post("/courses/1/ratings", json={"rating": 5}, headers=auth)
        assert response.status_code == 401
        service.add_course_rating.assert_not_called()

    def test_read_endpoints_stay_public(self, client, service):
        service.get_course_rating_stats.return_value = {
            "average_rating": 4.0,
            "total_ratings": 1,
            "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 1, 5: 0},
        }
        assert client.get("/courses/1/ratings/stats").status_code == 200


class TestAuthorization:
    def test_cannot_rate_as_another_user(self, client, service, auth):
        response = client.post(
            "/courses/1/ratings", json={"user_id": 999, "rating": 5}, headers=auth
        )
        assert response.status_code == 403
        service.add_course_rating.assert_not_called()

    def test_cannot_update_another_users_rating(self, client, service, auth):
        response = client.put(
            "/courses/1/ratings/999", json={"user_id": 999, "rating": 1}, headers=auth
        )
        assert response.status_code == 403
        service.update_course_rating.assert_not_called()

    def test_cannot_delete_another_users_rating(self, client, service, auth):
        response = client.delete("/courses/1/ratings/999", headers=auth)
        assert response.status_code == 403
        service.delete_course_rating.assert_not_called()

    def test_user_id_comes_from_token_not_body(self, client, service, auth):
        response = client.post("/courses/1/ratings", json={"rating": 5}, headers=auth)
        assert response.status_code == 201
        service.add_course_rating.assert_called_once_with(
            course_id=1, user_id=USER_ID, rating=5
        )

    def test_matching_body_user_id_is_accepted(self, client, auth):
        response = client.post(
            "/courses/1/ratings", json={"user_id": USER_ID, "rating": 5}, headers=auth
        )
        assert response.status_code == 201


class TestOwnRatingFlow:
    def test_user_can_manage_own_rating(self, client, auth):
        assert client.post("/courses/1/ratings", json={"rating": 5}, headers=auth).status_code == 201
        assert client.put("/courses/1/ratings/100", json={"rating": 4}, headers=auth).status_code == 200
        assert client.delete("/courses/1/ratings/100", headers=auth).status_code == 204
