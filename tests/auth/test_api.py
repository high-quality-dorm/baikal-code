import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.security import hash_password
from app.auth.schemas import Credentials
from app.services.providers import InMemoryAuthStore
from app.services.auth import AuthService

pytestmark = pytest.mark.usefixtures("rsa_keys")


def make_client():
    app = create_app()
    return TestClient(app)


def test_login_success():
    client = make_client()
    client.post("/api/v1/auth/bootstrap-admin",
                json={"email": "admin@x.ru", "password": "admin12345"})
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@x.ru", "password": "admin12345"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["role"] == "admin"


def test_login_wrong_password():
    client = make_client()
    client.post("/api/v1/auth/bootstrap-admin",
                json={"email": "admin@x.ru", "password": "admin12345"})
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@x.ru", "password": "wrongpass"})
    assert resp.status_code == 401


def test_bootstrap_admin_only_once():
    client = make_client()
    r1 = client.post("/api/v1/auth/bootstrap-admin",
                     json={"email": "a@x.ru", "password": "admin12345"})
    r2 = client.post("/api/v1/auth/bootstrap-admin",
                     json={"email": "b@x.ru", "password": "admin12345"})
    assert r1.status_code == 200
    assert r2.status_code == 409


def test_admin_can_create_user():
    client = make_client()
    client.post("/api/v1/auth/bootstrap-admin",
                json={"email": "admin@x.ru", "password": "admin12345"})
    login = client.post("/api/v1/auth/login",
                        json={"email": "admin@x.ru", "password": "admin12345"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.post("/api/v1/auth/users",
                       json={"email": "stud@x.ru", "password": "stud12345", "role": "student"},
                       headers=headers)
    assert resp.status_code == 201


def test_non_admin_cannot_create_user():
    client = make_client()
    client.post("/api/v1/auth/bootstrap-admin",
                json={"email": "admin@x.ru", "password": "admin12345"})
    login = client.post("/api/v1/auth/login",
                        json={"email": "admin@x.ru", "password": "admin12345"}).json()
    # create a student via admin
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    client.post("/api/v1/auth/users",
                json={"email": "stud@x.ru", "password": "stud12345", "role": "student"},
                headers=headers)
    slogin = client.post("/api/v1/auth/login",
                         json={"email": "stud@x.ru", "password": "stud12345"}).json()
    sheaders = {"Authorization": f"Bearer {slogin['access_token']}"}
    resp = client.post("/api/v1/auth/users",
                       json={"email": "x@x.ru", "password": "xxxx12345", "role": "student"},
                       headers=sheaders)
    assert resp.status_code == 403


def test_anonymous_gets_401_on_admin_endpoint():
    client = make_client()
    resp = client.get("/api/v1/auth/users")
    assert resp.status_code == 401
