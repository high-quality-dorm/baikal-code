import pytest

from app.auth.schemas import Credentials
from app.services.providers import DbUserCredentialsStore, InMemoryAuthStore


class FakeGateway:
    """Фейк GatewayClient: имитирует manage_user и запоминает вызовы."""

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    async def manage_user(self, action: str, **params) -> object:
        self.calls.append((action, params))
        if action in self.responses:
            return self.responses[action]
        raise AssertionError(f"Unexpected manage_user action: {action}")


@pytest.mark.anyio
async def test_persist_assigns_id_and_find():
    store = InMemoryAuthStore()
    user = Credentials(id=None, external_id="e1", email="a@b.c",
                       password_hash="h", role="student", is_active=True)
    saved = await store.persist(user)
    assert saved.id is not None
    assert await store.find(saved.id) is saved


@pytest.mark.anyio
async def test_find_missing():
    store = InMemoryAuthStore()
    assert await store.find(999) is None


@pytest.mark.anyio
async def test_get_credentials_by_email():
    store = InMemoryAuthStore()
    await store.add(Credentials(id=1, external_id="e1", email="a@b.c",
                                password_hash="h", role="student", is_active=True))
    creds = await store.get_credentials("a@b.c")
    assert creds is not None
    assert creds.role == "student"


@pytest.mark.anyio
async def test_get_credentials_by_external_id():
    store = InMemoryAuthStore()
    await store.add(Credentials(id=2, external_id="ext-2", email=None,
                                password_hash="h", role="teacher", is_active=True))
    creds = await store.get_credentials("ext-2")
    assert creds is not None
    assert creds.id == 2


@pytest.mark.anyio
async def test_get_credentials_missing():
    store = InMemoryAuthStore()
    assert await store.get_credentials("nobody") is None


@pytest.mark.anyio
async def test_all_lists_users():
    store = InMemoryAuthStore()
    await store.add(Credentials(id=None, external_id="e1", email="a@b.c",
                                password_hash="h", role="student", is_active=True))
    await store.add(Credentials(id=None, external_id="e2", email="b@b.c",
                                password_hash="h", role="admin", is_active=True))
    assert len(await store.all()) == 2


_USER_DICT = {
    "id": 7,
    "external_id": "ext-7",
    "email": "a@b.c",
    "password_hash": "hash",
    "role": "student",
    "internal_id": 100,
    "display_name": "Студент",
    "is_active": True,
}


@pytest.mark.anyio
async def test_db_store_get_credentials_maps():
    gw = FakeGateway({"get_credentials": _USER_DICT})
    store = DbUserCredentialsStore(gw)

    creds = await store.get_credentials("a@b.c")

    assert creds is not None
    assert creds.id == 7
    assert creds.email == "a@b.c"
    assert creds.role == "student"
    assert creds.internal_id == 100
    assert gw.calls == [("get_credentials", {"login": "a@b.c"})]


@pytest.mark.anyio
async def test_db_store_get_credentials_missing():
    gw = FakeGateway({"get_credentials": None})
    store = DbUserCredentialsStore(gw)

    assert await store.get_credentials("nobody") is None


@pytest.mark.anyio
async def test_db_store_find():
    gw = FakeGateway({"find": _USER_DICT})
    store = DbUserCredentialsStore(gw)

    creds = await store.find(7)

    assert creds is not None and creds.id == 7
    assert gw.calls == [("find", {"user_id": 7})]


@pytest.mark.anyio
async def test_db_store_all():
    gw = FakeGateway({"list": [_USER_DICT]})
    store = DbUserCredentialsStore(gw)

    users = await store.all()

    assert len(users) == 1
    assert users[0].role == "student"


@pytest.mark.anyio
async def test_db_store_persist_create():
    gw = FakeGateway({"create": {**_USER_DICT, "id": 10}})
    store = DbUserCredentialsStore(gw)

    saved = await store.persist(Credentials(
        id=None, external_id="ext-10", email="x@y.z", password_hash="hash",
        role="student", internal_id=42, display_name="Иван", is_active=True))

    assert saved is not None and saved.id == 10
    action, params = gw.calls[0]
    assert action == "create"
    assert params["external_id"] == "ext-10"
    assert params["role"] == "student"


@pytest.mark.anyio
async def test_db_store_persist_update():
    gw = FakeGateway({"update": _USER_DICT})
    store = DbUserCredentialsStore(gw)

    saved = await store.persist(Credentials(
        id=7, external_id="ext-7", email="a@b.c", password_hash="hash",
        role="student", internal_id=100, display_name="Студент", is_active=True))

    assert saved is not None and saved.id == 7
    action, params = gw.calls[0]
    assert action == "update"
    assert params["user_id"] == 7