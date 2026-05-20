"""
routers/users.py — REST endpoints for user management.

Prefix: /api/users

Endpoints:
  GET    /           — list all users
  POST   /           — create a user
  GET    /{user_id}  — get a single user
  DELETE /{user_id}  — delete a user
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.api import UserCreate, UserResponse
from services import lock_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    """Return all users ordered by id."""
    return await lock_service.get_all_users(db)


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new user.

    Returns 409 Conflict if the username is already taken.
    """
    try:
        return await lock_service.create_user(db, data.username, data.role)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Username '{data.username}' already exists"
        )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single user by ID."""
    user = await lock_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a user by ID."""
    deleted = await lock_service.delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
