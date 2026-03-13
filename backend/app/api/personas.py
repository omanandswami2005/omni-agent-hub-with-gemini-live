"""CRUD /personas — agent persona management."""

from fastapi import APIRouter, Depends

from app.middleware.auth_middleware import CurrentUser
from app.models.persona import PersonaCreate, PersonaResponse, PersonaUpdate
from app.services.persona_service import PersonaService, get_persona_service

router = APIRouter()


@router.get("")
async def list_personas(
    user: CurrentUser,
    svc: PersonaService = Depends(get_persona_service),  # noqa: B008
) -> list[PersonaResponse]:
    """Return defaults + user-created personas."""
    return await svc.list_personas(user.uid)


@router.get("/{persona_id}")
async def get_persona(
    persona_id: str,
    user: CurrentUser,
    svc: PersonaService = Depends(get_persona_service),  # noqa: B008
) -> PersonaResponse:
    """Get a single persona by ID."""
    return await svc.get_persona(user.uid, persona_id)


@router.post("", status_code=201)
async def create_persona(
    body: PersonaCreate,
    user: CurrentUser,
    svc: PersonaService = Depends(get_persona_service),  # noqa: B008
) -> PersonaResponse:
    """Create a custom persona."""
    return await svc.create_persona(user.uid, body)


@router.put("/{persona_id}")
async def update_persona(
    persona_id: str,
    body: PersonaUpdate,
    user: CurrentUser,
    svc: PersonaService = Depends(get_persona_service),  # noqa: B008
) -> PersonaResponse:
    """Update a user-created persona (defaults are immutable)."""
    return await svc.update_persona(user.uid, persona_id, body)


@router.delete("/{persona_id}", status_code=204)
async def delete_persona(
    persona_id: str,
    user: CurrentUser,
    svc: PersonaService = Depends(get_persona_service),  # noqa: B008
) -> None:
    """Delete a user-created persona (defaults cannot be deleted)."""
    await svc.delete_persona(user.uid, persona_id)
