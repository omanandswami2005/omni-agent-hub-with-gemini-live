"""Tests for SessionService — Firestore CRUD with mocked client."""

import pytest

from app.models.session import SessionCreate, SessionUpdate
from app.services.session_service import SessionService
from app.utils.errors import NotFoundError

# ── Fake Firestore helpers ────────────────────────────────────────────


class FakeDocSnap:
    """Mimics a Firestore DocumentSnapshot."""

    def __init__(self, doc_id: str, data: dict, *, exists: bool = True):
        self.id = doc_id
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


class FakeFirestore:
    """In-memory Firestore mock that stores docs in a dict."""

    def __init__(self):
        self._store: dict[str, dict[str, dict]] = {}

    def collection(self, name: str):
        if name not in self._store:
            self._store[name] = {}
        return _FakeCollectionRef(self._store, name)


class _FakeCollectionRef:
    def __init__(self, store, col_name):
        self._store = store
        self._col = col_name

    def document(self, doc_id):
        return _FakeDocRef(self._store, self._col, doc_id)

    def where(self, field, op, value):
        return _FakeQuery(self._store, self._col, field, op, value)

    def order_by(self, field, direction=None):
        return _FakeQuery(self._store, self._col, order_field=field)


class _FakeDocRef:
    def __init__(self, store, col_name, doc_id):
        self._store = store
        self._col = col_name
        self._id = doc_id

    def set(self, data):
        self._store[self._col][self._id] = dict(data)

    def get(self):
        if self._id in self._store.get(self._col, {}):
            return FakeDocSnap(self._id, self._store[self._col][self._id])
        return FakeDocSnap(self._id, {}, exists=False)

    def update(self, updates):
        if self._id not in self._store.get(self._col, {}):
            raise Exception("not found")
        self._store[self._col][self._id].update(updates)

    def delete(self):
        self._store.get(self._col, {}).pop(self._id, None)


class _FakeQuery:
    def __init__(self, store, col_name, field=None, op=None, value=None, order_field=None):
        self._store = store
        self._col = col_name
        self._field = field
        self._op = op
        self._value = value
        self._order_field = order_field

    def where(self, field, op, value):
        return _FakeQuery(self._store, self._col, field, op, value)

    def order_by(self, field, direction=None):
        self._order_field = field
        return self

    def stream(self):
        results = []
        for doc_id, data in self._store.get(self._col, {}).items():
            if self._field and self._op == "==" and data.get(self._field) != self._value:
                continue
            results.append(FakeDocSnap(doc_id, data))
        if self._order_field:
            results.sort(key=lambda s: s.to_dict().get(self._order_field, ""), reverse=True)
        return results


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def fake_db():
    return FakeFirestore()


@pytest.fixture
def svc(fake_db):
    return SessionService(db=fake_db)


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session(svc):
    result = await svc.create_session("user1", SessionCreate(persona_id="coder", title="My Chat"))
    assert result.user_id == "user1"
    assert result.persona_id == "coder"
    assert result.title == "My Chat"
    assert result.message_count == 0
    assert result.id  # non-empty


@pytest.mark.asyncio
async def test_create_session_auto_title(svc):
    result = await svc.create_session("user1", SessionCreate(persona_id="assistant"))
    assert "Session" in result.title  # auto-generated title


@pytest.mark.asyncio
async def test_get_session(svc):
    created = await svc.create_session("user1", SessionCreate(persona_id="researcher"))
    fetched = await svc.get_session("user1", created.id)
    assert fetched.id == created.id
    assert fetched.persona_id == "researcher"


@pytest.mark.asyncio
async def test_get_session_wrong_user_raises_404(svc):
    created = await svc.create_session("user1", SessionCreate())
    with pytest.raises(NotFoundError):
        await svc.get_session("user2", created.id)


@pytest.mark.asyncio
async def test_get_nonexistent_session_raises_404(svc):
    with pytest.raises(NotFoundError):
        await svc.get_session("user1", "nonexistent_id")


@pytest.mark.asyncio
async def test_list_sessions_user_scoped(svc):
    await svc.create_session("user1", SessionCreate(persona_id="a"))
    await svc.create_session("user1", SessionCreate(persona_id="b"))
    await svc.create_session("user2", SessionCreate(persona_id="c"))

    user1_sessions = await svc.list_sessions("user1")
    assert len(user1_sessions) == 2
    assert all(s.persona_id in ("a", "b") for s in user1_sessions)

    user2_sessions = await svc.list_sessions("user2")
    assert len(user2_sessions) == 1


@pytest.mark.asyncio
async def test_update_session(svc):
    created = await svc.create_session("user1", SessionCreate(title="Old"))
    updated = await svc.update_session(
        "user1", created.id, SessionUpdate(title="New Title", message_count=5)
    )
    assert updated.title == "New Title"
    assert updated.message_count == 5


@pytest.mark.asyncio
async def test_update_session_wrong_user_raises_404(svc):
    created = await svc.create_session("user1", SessionCreate())
    with pytest.raises(NotFoundError):
        await svc.update_session("user2", created.id, SessionUpdate(title="Hacked"))


@pytest.mark.asyncio
async def test_delete_session(svc):
    created = await svc.create_session("user1", SessionCreate())
    await svc.delete_session("user1", created.id)

    with pytest.raises(NotFoundError):
        await svc.get_session("user1", created.id)


@pytest.mark.asyncio
async def test_delete_session_wrong_user_raises_404(svc):
    created = await svc.create_session("user1", SessionCreate())
    with pytest.raises(NotFoundError):
        await svc.delete_session("user2", created.id)
