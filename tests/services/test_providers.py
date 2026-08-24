import pytest

from app.auth.schemas import Credentials
from app.services.providers import InMemoryAuthStore


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