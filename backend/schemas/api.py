"""
schemas/api.py — Pydantic v2 request/response models for all API endpoints.

All response schemas use `model_config = ConfigDict(from_attributes=True)` so
they can be populated directly from SQLAlchemy ORM instances via
`Schema.model_validate(orm_obj)`.

JSON-stored list fields (pin sequence, gesture sequence) are exposed as
`list[str]` in the API but stored as JSON strings in the database.
Serialisation/deserialisation happens in the service layer, not here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Request body for POST /api/users."""
    username: str = Field(..., min_length=1, max_length=100)
    role: Literal["admin", "operator"] = "operator"


class UserResponse(BaseModel):
    """Response body for user endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Lock schemas
# ---------------------------------------------------------------------------

class LockCreate(BaseModel):
    """Request body for POST /api/locks."""
    name: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=300)
    mode: Literal["entry", "recording"] = "entry"


class LockUpdate(BaseModel):
    """Request body for PUT /api/locks/{lock_id} — all fields optional."""
    name: str | None = Field(None, min_length=1, max_length=200)
    location: str | None = Field(None, min_length=1, max_length=300)
    mode: Literal["entry", "recording"] | None = None


class LockResponse(BaseModel):
    """Response body for lock endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    mode: str
    created_at: datetime


class LockModeSet(BaseModel):
    """Request body for POST /api/locks/{lock_id}/mode."""
    mode: Literal["entry", "recording"]


class LockModeResponse(BaseModel):
    """Response body for GET/POST /api/locks/{lock_id}/mode."""
    mode: str


# ---------------------------------------------------------------------------
# Lock state schemas
# ---------------------------------------------------------------------------

class LockStateUpdate(BaseModel):
    """Request body for PUT /api/locks/{lock_id}/state."""
    state: Literal["locked", "unlocked"]
    changed_by: int | None = None  # user_id, optional for manual/system changes


class LockStateResponse(BaseModel):
    """Response body for lock state endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    lock_id: int
    state: str
    changed_by: int | None
    changed_at: datetime


# ---------------------------------------------------------------------------
# PIN schemas
# ---------------------------------------------------------------------------

class PinSave(BaseModel):
    """
    Request body for POST /api/locks/{lock_id}/pin.

    Called by the frontend after a recording session to persist the PIN.
    """
    user_id: int
    sequence: Annotated[list[str], Field(min_length=3, max_length=6)]

    @field_validator("sequence")
    @classmethod
    def validate_gestures(cls, v: list[str]) -> list[str]:
        """Ensure all gesture names are non-empty strings."""
        valid = {
            "OPEN_PALM", "FIST", "INDEX_UP", "PEACE", "THREE", "FOUR",
            "THUMBS_UP", "THUMBS_DOWN", "PINKY_UP", "OK", "ROCK", "CALL_ME",
        }
        for g in v:
            if g not in valid:
                raise ValueError(f"Unknown gesture: '{g}'")
        return v


class PinConfigResponse(BaseModel):
    """Response body for PIN config endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    lock_id: int
    user_id: int
    # Returned as a parsed list, not a raw JSON string
    sequence: list[str]
    created_at: datetime

    @field_validator("sequence", mode="before")
    @classmethod
    def parse_sequence(cls, v) -> list[str]:
        """Convert JSON string from DB to list[str] for the response."""
        import json
        if isinstance(v, str):
            return json.loads(v)
        return v


# ---------------------------------------------------------------------------
# Gesture verify schemas (used by CV module)
# ---------------------------------------------------------------------------

class GestureVerifyRequest(BaseModel):
    """
    Request body sent by the CV module to POST /api/gestures/verify.

    Sent after every stable gesture confirmation (15-frame hold).
    """
    lock_id: int
    gesture: str
    sequence: list[str]
    mode: Literal["entry", "recording"]
    timestamp: datetime


class GestureVerifyResponse(BaseModel):
    """
    Response from POST /api/gestures/verify.

    status:
      "partial"  — sequence is a valid prefix of the stored PIN (keep going)
      "match"    — sequence matches the full PIN (lock toggled)
      "fail"     — sequence does not match (reset)
      "recorded" — gesture acknowledged in recording mode
    """
    status: Literal["partial", "match", "fail", "recorded"]
    lock_state: str | None = None      # populated on "match"
    gesture_count: int | None = None   # populated on "recorded"


# ---------------------------------------------------------------------------
# Access log schemas
# ---------------------------------------------------------------------------

class AccessLogResponse(BaseModel):
    """Response body for GET /api/access-log entries."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    lock_id: int
    user_id: int | None
    timestamp: datetime
    result: str
    gesture_sequence: list[str]

    @field_validator("gesture_sequence", mode="before")
    @classmethod
    def parse_gesture_sequence(cls, v) -> list[str]:
        """Convert JSON string from DB to list[str]."""
        import json
        if isinstance(v, str):
            return json.loads(v)
        return v
