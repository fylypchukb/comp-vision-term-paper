"""
models/orm.py — SQLAlchemy ORM table definitions for the Gesture Smart Lock system.

Tables:
  users        — application users (admin / operator)
  locks        — physical lock devices
  pin_configs  — stored PIN sequences per lock
  lock_states  — append-only audit log of lock state changes
  access_log   — every gesture verification attempt (success or fail)
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    """Application user — admin or operator."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # role is constrained to admin or operator
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="operator",
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator')", name="ck_users_role"),
    )

    # Relationships
    pin_configs: Mapped[list[PinConfig]] = relationship(back_populates="user")
    lock_states_changed: Mapped[list[LockState]] = relationship(
        back_populates="changer", foreign_keys="LockState.changed_by"
    )


class Lock(Base):
    """A physical lock device managed by the system."""

    __tablename__ = "locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(300), nullable=False)
    # mode controls whether the CV module is in PIN-entry or PIN-recording mode
    mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="entry"
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("mode IN ('entry', 'recording')", name="ck_locks_mode"),
    )

    # Relationships
    pin_configs: Mapped[list[PinConfig]] = relationship(back_populates="lock")
    states: Mapped[list[LockState]] = relationship(back_populates="lock")
    access_logs: Mapped[list[AccessLog]] = relationship(back_populates="lock")


class PinConfig(Base):
    """
    Stored PIN sequence for a lock.

    `sequence` is a JSON-serialised list of gesture names, e.g.:
        '["OPEN_PALM", "FIST", "THUMBS_UP"]'
    Only one PIN per lock is active at a time; saving a new PIN deletes the old one.
    """

    __tablename__ = "pin_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("locks.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # NVARCHAR(MAX) via Text — SQL Server has no native JSON column type
    sequence: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    lock: Mapped[Lock] = relationship(back_populates="pin_configs")
    user: Mapped[User] = relationship(back_populates="pin_configs")


class LockState(Base):
    """
    Append-only audit log of lock state changes.

    The *current* state of a lock is always the row with the highest `changed_at`
    for a given `lock_id`.  Rows are never updated — only inserted.
    `changed_by` is nullable because the CV module can trigger state changes
    without an authenticated user session.
    """

    __tablename__ = "lock_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("locks.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    # nullable — CV-driven state changes have no associated operator
    changed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    changed_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('locked', 'unlocked')", name="ck_lock_states_state"
        ),
    )

    # Relationships
    lock: Mapped[Lock] = relationship(back_populates="states")
    changer: Mapped[User | None] = relationship(
        back_populates="lock_states_changed", foreign_keys=[changed_by]
    )


class AccessLog(Base):
    """
    Every gesture verification attempt logged for auditing.

    `user_id` is nullable — the CV module submits gestures without a user session.
    `gesture_sequence` is a JSON-serialised list of gesture names submitted at the
    time of the attempt.
    """

    __tablename__ = "access_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("locks.id"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    timestamp: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    # JSON-serialised gesture sequence at the time of the attempt
    gesture_sequence: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "result IN ('success', 'fail')", name="ck_access_log_result"
        ),
    )

    # Relationships
    lock: Mapped[Lock] = relationship(back_populates="access_logs")
