import pytest

from db_mcp.roles import BusinessRole

from app.auth.schemas import Credentials, UserCreate, UserUpdate
from app.core.security import hash_password, decode_access_token
from app.services.auth import (
    AdminExistsError,
    AuthenticationError,
    AuthService,
    DuplicateLoginError,
)
from app.services.providers import InMemoryAuthStore

pytestmark = pytest.mark.usefixtures("rsa_keys")


def make_service():
    return AuthService(InMemoryAuthStore())


@pytest.mark.anyio
async def test_authenticate_success():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("pw123456"), role="admin", is_active=True))
    token = await svc.authenticate("a@b.c", "pw123456")
    assert token.access_token
    assert token.role == "admin"


@pytest.mark.anyio
async def test_authenticate_wrong_password():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("pw123456"), role="admin", is_active=True))
    with pytest.raises(AuthenticationError):
        await svc.authenticate("a@b.c", "badpass")


@pytest.mark.anyio
async def test_authenticate_inactive():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("pw123456"), role="admin", is_active=False))
    with pytest.raises(AuthenticationError):
        await svc.authenticate("a@b.c", "pw123456")


@pytest.mark.anyio
async def test_authenticate_unknown_login():
    svc = make_service()
    with pytest.raises(AuthenticationError):
        await svc.authenticate("nobody", "whatever1")


@pytest.mark.anyio
async def test_bootstrap_admin_creates_when_empty():
    svc = make_service()
    out = await svc.bootstrap_admin("admin@x.ru", "admin12345")
    assert out.role == BusinessRole.ADMIN.value


@pytest.mark.anyio
async def test_bootstrap_admin_conflict():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("pw123456"), role="admin", is_active=True))
    with pytest.raises(AdminExistsError):
        await svc.bootstrap_admin("admin2@x.ru", "admin12345")


@pytest.mark.anyio
async def test_create_user_duplicate():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("pw123456"), role="student", is_active=True))
    with pytest.raises(DuplicateLoginError):
        await svc.create_user(UserCreate(email="a@b.c", password="pw123456", role=BusinessRole.STUDENT))


@pytest.mark.anyio
async def test_create_user_duplicate_external_id():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("pw123456"), role="student", is_active=True))
    with pytest.raises(DuplicateLoginError):
        await svc.create_user(UserCreate(
            email="other@b.c", password="pw123456", role=BusinessRole.STUDENT, external_id="e1"))


@pytest.mark.anyio
async def test_token_sub_is_credentials_id_even_with_internal_id():
    svc = make_service()
    saved = await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c", internal_id=999,
        password_hash=hash_password("pw123456"), role="admin", is_active=True))
    token = await svc.authenticate("a@b.c", "pw123456")
    payload = decode_access_token(token.access_token)
    assert payload["sub"] == str(saved.id)


@pytest.mark.anyio
async def test_update_user_password():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("oldpass1"), role="student", is_active=True))
    await svc.update_user(1, UserUpdate(password="newpass1"))
    assert (await svc.authenticate("a@b.c", "newpass1")).role == "student"


@pytest.mark.anyio
async def test_deactivate_user():
    svc = make_service()
    await svc.store.add(Credentials(
        id=None, external_id="e1", email="a@b.c",
        password_hash=hash_password("pw123456"), role="student", is_active=True))
    assert await svc.deactivate_user(1) is True
    with pytest.raises(AuthenticationError):
        await svc.authenticate("a@b.c", "pw123456")
