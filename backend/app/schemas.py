"""Pydantic schemas for API request/response validation"""
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator, model_validator

VALID_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _utc_iso(dt: datetime) -> str:
    """SQLite stores CURRENT_TIMESTAMP as naive UTC; emit an explicit Z offset
    so browsers don't misparse timestamps as local time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# ---------- Auth ----------
class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    created_at: datetime

    @field_serializer("created_at")
    def _ser_created_at(self, dt: datetime) -> str:
        return _utc_iso(dt)

    class Config:
        from_attributes = True


# ---------- Watches ----------
class WatchBase(BaseModel):
    label: str = Field(default="My watch", max_length=120)
    num_players: int = Field(default=4, ge=1, le=4)
    num_holes: int = Field(default=18)
    course_ids: str = Field(default="all")
    target_days: str = Field(default="sat,sun")
    window_start: str = Field(default="07:00")
    window_end: str = Field(default="11:00")
    active: bool = True

    @field_validator("num_holes")
    @classmethod
    def _holes(cls, v: int) -> int:
        if v not in (9, 18):
            raise ValueError("num_holes must be 9 or 18")
        return v

    @field_validator("window_start", "window_end")
    @classmethod
    def _time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("time must be HH:MM (24-hour)")
        return v

    @field_validator("target_days")
    @classmethod
    def _days(cls, v: str) -> str:
        days = [d.strip().lower() for d in v.split(",") if d.strip()]
        if not days:
            raise ValueError("select at least one day")
        for d in days:
            if d not in VALID_DAYS:
                raise ValueError(f"invalid day: {d}")
        # dedupe + keep canonical weekday order
        return ",".join([d for d in VALID_DAYS if d in days])

    @field_validator("course_ids")
    @classmethod
    def _courses(cls, v: str) -> str:
        v = v.strip().lower()
        if v in ("", "all"):
            return "all"
        ids = [c.strip() for c in v.split(",") if c.strip()]
        for c in ids:
            if not c.isdigit() or not (1 <= int(c) <= 5):
                raise ValueError(f"invalid course id: {c}")
        return ",".join(ids)

    @model_validator(mode="after")
    def _window_order(self) -> "WatchBase":
        if self.window_start >= self.window_end:
            raise ValueError("window_start must be before window_end")
        return self


class WatchCreate(WatchBase):
    pass


class WatchUpdate(BaseModel):
    label: Optional[str] = None
    num_players: Optional[int] = Field(default=None, ge=1, le=4)
    num_holes: Optional[int] = None
    course_ids: Optional[str] = None
    target_days: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    active: Optional[bool] = None


class WatchResponse(WatchBase):
    id: int
    user_id: int
    created_at: datetime

    @field_serializer("created_at")
    def _ser_created_at(self, dt: datetime) -> str:
        return _utc_iso(dt)

    class Config:
        from_attributes = True


# ---------- Found slots ----------
class FoundSlotResponse(BaseModel):
    id: int
    watch_id: int
    course_id: int
    course_name: Optional[str]
    date: str
    time: str
    open_slots: int
    found_at: datetime
    notified: bool
    booking_url: str

    @field_serializer("found_at")
    def _ser_found_at(self, dt: datetime) -> str:
        return _utc_iso(dt)

    class Config:
        from_attributes = True


class ScanResultResponse(BaseModel):
    ran: bool
    in_window: bool
    dates_scanned: list[str]
    total_slots: int
    new_matches: int
    message: str
    blocked: bool = False
