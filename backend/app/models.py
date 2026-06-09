"""SQLAlchemy ORM models"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base


class User(Base):
    """User account (email + password)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    watches = relationship(
        "Watch", back_populates="user", cascade="all, delete-orphan"
    )


class Watch(Base):
    """A user's tee-time watch configuration."""
    __tablename__ = "watches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    label = Column(String(120), default="My watch", nullable=False)
    num_players = Column(Integer, default=4, nullable=False)        # 1-4
    num_holes = Column(Integer, default=18, nullable=False)         # 9 or 18
    course_ids = Column(String(40), default="all", nullable=False)  # "all" or "1,2,4"
    target_days = Column(String(40), default="sat,sun", nullable=False)  # mon..sun csv
    window_start = Column(String(5), default="07:00", nullable=False)    # HH:MM 24h
    window_end = Column(String(5), default="11:00", nullable=False)      # HH:MM 24h
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="watches")
    found_slots = relationship(
        "FoundSlot", back_populates="watch", cascade="all, delete-orphan"
    )


class FoundSlot(Base):
    """Record of a matched/notified tee-time slot (also used for de-dup)."""
    __tablename__ = "found_slots"

    id = Column(Integer, primary_key=True, index=True)
    watch_id = Column(Integer, ForeignKey("watches.id"), nullable=False, index=True)
    course_id = Column(Integer, nullable=False)
    course_name = Column(String(120))
    date = Column(String(10), nullable=False)   # MM/DD/YYYY
    time = Column(String(10), nullable=False)    # e.g. "7:10 am"
    open_slots = Column(Integer, nullable=False)
    found_at = Column(DateTime(timezone=True), server_default=func.now())
    notified = Column(Boolean, default=False, nullable=False)

    watch = relationship("Watch", back_populates="found_slots")

    __table_args__ = (
        UniqueConstraint("watch_id", "course_id", "date", "time", name="uq_found_slot"),
    )

    @property
    def booking_url(self) -> str:
        """Deep link into WebTrac with this slot's course/date/time prefilled."""
        from .services.links import build_search_url
        players = self.watch.num_players if self.watch else 4
        holes = self.watch.num_holes if self.watch else 18
        return build_search_url(self.course_id, self.date, self.time, players, holes)
