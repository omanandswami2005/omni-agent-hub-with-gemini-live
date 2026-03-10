"""Tests for PersonaService — defaults, Firestore CRUD, protection rules."""

import pytest

from app.agents.personas import DEFAULT_PERSONAS, get_default_persona_ids, get_default_personas
from app.models.persona import PersonaCreate, PersonaUpdate
from app.services.persona_service import PersonaService
from app.utils.errors import AuthorizationError, NotFoundError

# ── Fake Firestore helpers (same pattern as test_session_service) ─────


class _FakeDocSnap:
    def __init__(self, doc_id: str, data: dict, *, exists: bool = True):
        self.id = doc_id
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


class _FakeFirestore:
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
            return _FakeDocSnap(self._id, self._store[self._col][self._id])
        return _FakeDocSnap(self._id, {}, exists=False)

    def update(self, updates):
        if self._id not in self._store.get(self._col, {}):
            msg = "not found"
            raise Exception(msg)
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
            results.append(_FakeDocSnap(doc_id, data))
        if self._order_field:
            results.sort(key=lambda s: s.to_dict().get(self._order_field, ""), reverse=True)
        return results


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def svc():
    return PersonaService(db=_FakeFirestore())


# ── Default personas ─────────────────────────────────────────────────


class TestDefaultPersonas:
    def test_five_defaults_exist(self):
        assert len(DEFAULT_PERSONAS) == 5

    def test_default_ids(self):
        ids = get_default_persona_ids()
        assert ids == {"assistant", "coder", "researcher", "analyst", "creative"}

    def test_default_personas_are_persona_response(self):
        personas = get_default_personas()
        for p in personas:
            assert p.user_id == "system"
            assert p.is_default is True
            assert p.name  # non-empty

    def test_each_default_has_unique_voice(self):
        voices = [p.voice for p in get_default_personas()]
        assert len(voices) == len(set(voices))


# ── PersonaService CRUD ──────────────────────────────────────────────


class TestListPersonas:
    async def test_list_includes_defaults(self, svc):
        result = await svc.list_personas("user1")
        default_ids = {p.id for p in result if p.is_default}
        assert "assistant" in default_ids
        assert len(default_ids) == 5

    async def test_list_includes_user_created(self, svc):
        await svc.create_persona("user1", PersonaCreate(name="Custom"))
        result = await svc.list_personas("user1")
        custom = [p for p in result if not p.is_default]
        assert len(custom) == 1
        assert custom[0].name == "Custom"

    async def test_list_user_scoped(self, svc):
        await svc.create_persona("user1", PersonaCreate(name="Mine"))
        await svc.create_persona("user2", PersonaCreate(name="Theirs"))
        u1 = [p for p in await svc.list_personas("user1") if not p.is_default]
        u2 = [p for p in await svc.list_personas("user2") if not p.is_default]
        assert len(u1) == 1
        assert len(u2) == 1


class TestGetPersona:
    async def test_get_default_persona(self, svc):
        p = await svc.get_persona("anyone", "assistant")
        assert p.name == "Claire"
        assert p.is_default is True

    async def test_get_user_persona(self, svc):
        created = await svc.create_persona("user1", PersonaCreate(name="Bot"))
        fetched = await svc.get_persona("user1", created.id)
        assert fetched.name == "Bot"

    async def test_get_wrong_user_raises_404(self, svc):
        created = await svc.create_persona("user1", PersonaCreate(name="X"))
        with pytest.raises(NotFoundError):
            await svc.get_persona("user2", created.id)

    async def test_get_nonexistent_raises_404(self, svc):
        with pytest.raises(NotFoundError):
            await svc.get_persona("user1", "nope")


class TestCreatePersona:
    async def test_create_returns_response(self, svc):
        p = await svc.create_persona(
            "user1",
            PersonaCreate(name="Helper", voice="Fenrir", system_instruction="Be helpful"),
        )
        assert p.name == "Helper"
        assert p.voice == "Fenrir"
        assert p.user_id == "user1"
        assert p.is_default is False
        assert p.id  # non-empty

    async def test_create_defaults_voice(self, svc):
        p = await svc.create_persona("user1", PersonaCreate(name="Test"))
        assert p.voice == "Kore"  # default from PersonaCreate


class TestUpdatePersona:
    async def test_update_custom_persona(self, svc):
        created = await svc.create_persona("user1", PersonaCreate(name="Old"))
        updated = await svc.update_persona(
            "user1", created.id, PersonaUpdate(name="New", voice="Leda")
        )
        assert updated.name == "New"
        assert updated.voice == "Leda"

    async def test_update_default_raises_403(self, svc):
        with pytest.raises(AuthorizationError):
            await svc.update_persona("user1", "assistant", PersonaUpdate(name="Hacked"))

    async def test_update_wrong_user_raises_404(self, svc):
        created = await svc.create_persona("user1", PersonaCreate(name="X"))
        with pytest.raises(NotFoundError):
            await svc.update_persona("user2", created.id, PersonaUpdate(name="Y"))

    async def test_update_empty_is_noop(self, svc):
        created = await svc.create_persona("user1", PersonaCreate(name="Same"))
        updated = await svc.update_persona("user1", created.id, PersonaUpdate())
        assert updated.name == "Same"


class TestDeletePersona:
    async def test_delete_custom_persona(self, svc):
        created = await svc.create_persona("user1", PersonaCreate(name="Temp"))
        await svc.delete_persona("user1", created.id)
        with pytest.raises(NotFoundError):
            await svc.get_persona("user1", created.id)

    async def test_delete_default_raises_403(self, svc):
        with pytest.raises(AuthorizationError):
            await svc.delete_persona("user1", "coder")

    async def test_delete_wrong_user_raises_404(self, svc):
        created = await svc.create_persona("user1", PersonaCreate(name="X"))
        with pytest.raises(NotFoundError):
            await svc.delete_persona("user2", created.id)
