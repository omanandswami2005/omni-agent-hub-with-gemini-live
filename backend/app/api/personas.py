"""CRUD /personas — agent persona management."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_personas():
    # TODO: Fetch personas from Firestore
    return []


@router.post("/")
async def create_persona():
    # TODO: Create persona in Firestore
    return {"status": "created"}
