"""Watch CRUD, found-slots log, and manual scan trigger (all per-user)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from ..auth.security import get_current_user
from ..db import get_db
from ..models import FoundSlot, User, Watch
from ..schemas import (
    FoundSlotResponse, ScanResultResponse, WatchCreate, WatchResponse, WatchUpdate,
)
from ..scheduler import get_scheduler
from ..services.monitor_job import get_last_scan, in_scan_window, run_scan, _now
from ..services.scraper import COURSES, circuit, traffic

router = APIRouter()


@router.get("/courses")
def list_courses():
    """Static list of courses for the watch form."""
    return [{"id": cid, "name": name} for cid, name in COURSES.items()]


@router.get("/scan-status")
def scan_status(user: User = Depends(get_current_user)):
    """Scanner health: scheduler state, next run, and last scan summary."""
    sched = get_scheduler()
    running = bool(sched and sched.running)
    next_run = None
    if sched:
        job = sched.get_job("teetime_scan")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    return {
        "scheduler_running": running,
        "next_run": next_run,
        "in_window": in_scan_window(_now()),
        "last_scan": get_last_scan(),
        "scraper": circuit.status(),
        "traffic": traffic.status(),
    }


@router.get("/watches", response_model=list[WatchResponse])
def list_watches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Watch)
        .filter(Watch.user_id == user.id)
        .order_by(Watch.created_at.desc())
        .all()
    )


@router.post("/watches", response_model=WatchResponse, status_code=status.HTTP_201_CREATED)
def create_watch(payload: WatchCreate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    watch = Watch(user_id=user.id, **payload.model_dump())
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return watch


def _get_owned_watch(watch_id: int, db: Session, user: User) -> Watch:
    watch = db.get(Watch, watch_id)
    if not watch or watch.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watch not found")
    return watch


@router.put("/watches/{watch_id}", response_model=WatchResponse)
def update_watch(watch_id: int, payload: WatchUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    watch = _get_owned_watch(watch_id, db, user)
    data = payload.model_dump(exclude_unset=True)
    # Re-validate provided fields via WatchCreate-style rules.
    if data:
        from ..schemas import WatchBase
        merged = WatchBase(
            label=data.get("label", watch.label),
            num_players=data.get("num_players", watch.num_players),
            num_holes=data.get("num_holes", watch.num_holes),
            course_ids=data.get("course_ids", watch.course_ids),
            target_days=data.get("target_days", watch.target_days),
            window_start=data.get("window_start", watch.window_start),
            window_end=data.get("window_end", watch.window_end),
            active=data.get("active", watch.active),
        )
        for field, value in merged.model_dump().items():
            setattr(watch, field, value)
    db.commit()
    db.refresh(watch)
    return watch


@router.delete("/watches/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(watch_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    watch = _get_owned_watch(watch_id, db, user)
    db.delete(watch)
    db.commit()


@router.get("/found-slots", response_model=list[FoundSlotResponse])
def list_found_slots(limit: int = 50, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return (
        db.query(FoundSlot)
        .join(Watch, FoundSlot.watch_id == Watch.id)
        # booking_url reads slot.watch; eager-load to avoid a query per row.
        .options(joinedload(FoundSlot.watch))
        .filter(Watch.user_id == user.id)
        .order_by(FoundSlot.found_at.desc())
        .limit(min(limit, 200))
        .all()
    )


@router.post("/watches/scan-now", response_model=ScanResultResponse)
async def scan_now(user: User = Depends(get_current_user)):
    """Force a scan immediately for the current user's watches (ignores the time window)."""
    return await run_scan(force=True, user_id=user.id)
