import os
import re
import uuid
import datetime
import json
from typing import List, Optional, Dict
from pathlib import Path

from fastapi import (
    FastAPI, UploadFile, File, Form, Depends, HTTPException, Query, Header,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, BigInteger,
    or_, func, text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "photos.db"
UPLOAD_DIR = BASE_DIR / "uploads"

# Set REQUIRE_ACTOR=0 only for standalone dev without nginx.
REQUIRE_ACTOR = os.getenv("REQUIRE_ACTOR", "1") == "1"

os.makedirs(UPLOAD_DIR, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class PhotoRecord(Base):
    __tablename__ = "photo_records"

    id = Column(Integer, primary_key=True, index=True)
    owner_name = Column(String, index=True, nullable=False)  # username at upload time

    # --- file info -------------------------------------------------------
    filename = Column(String)                  # name on disk (inside uploads/)
    filepath = Column(String, nullable=False)  # "uploads/<filename>"
    original_filename = Column(String)         # what the client uploaded
    content_type = Column(String)
    size_bytes = Column(BigInteger)

    # --- editable metadata ----------------------------------------------
    display_name = Column(String)              # user-facing title
    description = Column(String)
    tags = Column(String)                      # comma-separated

    # --- timestamps -------------------------------------------------------
    timestamp = Column(DateTime, default=datetime.datetime.now, index=True)
    updated_at = Column(
        DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now
    )

class ActivityLog(Base):
    """Append-only audit log. Survives photo deletion via snapshot fields."""
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True)
    actor = Column(String, index=True, nullable=False)
    # one of: upload, edit, rename, delete
    action = Column(String, index=True, nullable=False)

    # Snapshot so the entry still makes sense if the photo is later deleted.
    photo_id = Column(Integer, index=True, nullable=True)
    photo_display_name = Column(String)

    # Free-form JSON: change diffs, sizes, filenames, etc.
    details = Column(String)

    created_at = Column(
        DateTime, default=datetime.datetime.now, index=True, nullable=False
    )

Base.metadata.create_all(bind=engine)


def ensure_schema() -> None:
    """Tiny SQLite-only migration so an existing photos.db keeps working."""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(photo_records)")).fetchall()
        if not rows:
            return
        existing = {row[1] for row in rows}

        # Old schema: the owner was stored in a column called user_id.
        # Rename it to owner_name. Runs only once.
        if "owner_name" not in existing and "user_id" in existing:
            conn.execute(
                text("ALTER TABLE photo_records RENAME COLUMN user_id TO owner_name")
            )
            existing.discard("user_id")
            existing.add("owner_name")

        new_columns = {
            "filename": "VARCHAR",
            "original_filename": "VARCHAR",
            "display_name": "VARCHAR",
            "description": "VARCHAR",
            "tags": "VARCHAR",
            "content_type": "VARCHAR",
            "size_bytes": "BIGINT",
            "updated_at": "DATETIME",
        }
        for name, ddl in new_columns.items():
            if name not in existing:
                conn.execute(
                    text(f"ALTER TABLE photo_records ADD COLUMN {name} {ddl}")
                )

        # Backfill rows that predate the new columns.
        conn.execute(
            text(
                "UPDATE photo_records SET filename = REPLACE(filepath, 'uploads/', '') "
                "WHERE filename IS NULL"
            )
        )

        # Fill in file sizes from disk where we can.
        missing = conn.execute(
            text("SELECT id, filename FROM photo_records WHERE size_bytes IS NULL")
        ).fetchall()
        for photo_id, filename in missing:
            p = UPLOAD_DIR / Path(filename or "").name
            if filename and p.is_file():
                conn.execute(
                    text("UPDATE photo_records SET size_bytes = :s WHERE id = :i"),
                    {"s": p.stat().st_size, "i": photo_id},
                )


ensure_schema()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class PhotoOut(BaseModel):
    id: int
    owner: str
    filename: Optional[str] = None
    original_filename: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    timestamp: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    url: str
    download_url: str


class PhotoListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[PhotoOut]


class PhotoUpdate(BaseModel):
    """Every field is optional, only what you send gets changed.
    Unknown fields (like an old client's user_id) are ignored."""
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    tags: Optional[List[str]] = None


class RenameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    rename_file: bool = False  # also rename the file on disk


class BulkDeleteRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1)


class DeleteResponse(BaseModel):
    status: str
    id: Optional[int] = None
    deleted: Optional[int] = None
    missing_files: List[str] = Field(default_factory=list)

class ActivityOut(BaseModel):
    id: int
    actor: str
    action: str
    photo_id: Optional[int] = None
    photo_display_name: Optional[str] = None
    details: dict = Field(default_factory=dict)
    created_at: datetime.datetime


class ActivityListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[ActivityOut]

class DayHighlights(BaseModel):
    top_actor: Optional[str] = None
    top_action: Optional[str] = None
    distinct_actors: int = 0
    deleted_count: int = 0

class ActorDaySummary(BaseModel):
    actor: str
    count: int
    actions: Dict[str, int] = Field(default_factory=dict)


class DayDigest(BaseModel):
    date: str
    total: int
    summary: str
    highlights: DayHighlights
    actors: List[ActorDaySummary]
    items: List[ActivityOut] = Field(default_factory=list)

class ActorTotal(BaseModel):
    actor: str
    count: int

class DigestResponse(BaseModel):
    from_date: str
    to_date: str
    total: int
    summary: str
    totals_by_action: Dict[str, int] = Field(default_factory=dict)
    totals_by_actor: List[ActorTotal] = Field(default_factory=list)
    days: List[DayDigest]

class PhotoHistoryResponse(BaseModel):
    photo_id: int
    photo_display_name: Optional[str] = None
    photo_exists: bool
    total: int
    items: List[ActivityOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe_component(value: str, fallback: str = "item") -> str:
    """Turn arbitrary text into something safe for a filename."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:80] or fallback


def parse_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [t for t in (x.strip() for x in raw.split(",")) if t]


def dump_tags(tags: Optional[List[str]]) -> Optional[str]:
    if tags is None:
        return None
    cleaned: List[str] = []
    for tag in tags:
        tag = (tag or "").strip().replace(",", " ")
        if tag and tag not in cleaned:
            cleaned.append(tag)
    return ",".join(cleaned) or None


def serialize(photo: PhotoRecord) -> dict:
    return {
        "id": photo.id,
        "owner": photo.owner_name,
        "filename": photo.filename,
        "original_filename": photo.original_filename,
        "display_name": photo.display_name
        or photo.original_filename
        or photo.filename,
        "description": photo.description,
        "tags": parse_tags(photo.tags),
        "content_type": photo.content_type,
        "size_bytes": photo.size_bytes,
        "timestamp": photo.timestamp,
        "updated_at": photo.updated_at,
        "url": f"/photos/{photo.id}/file",
        "download_url": f"/photos/{photo.id}/download",
    }


def resolve_stored_path(photo: PhotoRecord) -> str:
    """Return the absolute path of the file, guarding against traversal."""
    name = photo.filename or os.path.basename(photo.filepath or "")
    if not name:
        raise HTTPException(status_code=410, detail="Photo has no file attached")

    # Path(name).name drops any directory parts, so traversal is impossible
    full = UPLOAD_DIR / Path(name).name
    if not full.is_file():
        raise HTTPException(status_code=410, detail="Photo file is missing from disk")
    return str(full)


def get_photo_or_404(db: Session, photo_id: int) -> PhotoRecord:
    photo = db.get(PhotoRecord, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail=f"Photo {photo_id} not found")
    return photo


def save_upload(upload: UploadFile, dest_path: str, max_bytes: int) -> int:
    """Stream the upload to disk, enforcing a size limit. Returns bytes written."""
    size = 0
    try:
        with open(dest_path, "wb") as out:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)",
                    )
                out.write(chunk)
    except Exception:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise
    return size


def delete_file_on_disk(photo: PhotoRecord) -> Optional[str]:
    """Best-effort delete. Returns the path if the file was missing."""
    try:
        path = resolve_stored_path(photo)
    except HTTPException:
        return photo.filepath
    try:
        os.remove(path)
    except OSError:
        return path
    return None

def serialize_activity(log: ActivityLog) -> dict:
    details: dict = {}
    if log.details:
        try:
            details = json.loads(log.details)
        except (ValueError, TypeError):
            details = {"raw": log.details}
    return {
        "id": log.id,
        "actor": log.actor,
        "action": log.action,
        "photo_id": log.photo_id,
        "photo_display_name": log.photo_display_name,
        "details": details,
        "created_at": log.created_at,
    }


def log_activity(
    db: Session,
    actor: str,
    action: str,
    photo: Optional[PhotoRecord] = None,
    *,
    details: Optional[dict] = None,
) -> ActivityLog:
    entry = ActivityLog(
        actor=actor,
        action=action,
        photo_id=photo.id if photo is not None else None,
        photo_display_name=(
            (photo.display_name or photo.original_filename or photo.filename)
            if photo is not None
            else None
        ),
        details=json.dumps(details, default=str) if details else None,
    )
    db.add(entry)
    return entry

# ---------------------------------------------------------------------------

# Digest summarization helpers
# ---------------------------------------------------------------------------
_ACTION_ORDER = ("upload", "edit", "rename", "delete")

# Verb-form: used in per-actor, per-day sentences.
#   "james uploaded 5 photos and edited 2 photos."
_ACTION_VERBS = {
    "upload": ("uploaded", "photo", "photos"),
    "edit":   ("edited",   "photo", "photos"),
    "rename": ("renamed",  "photo", "photos"),
    "delete": ("deleted",  "photo", "photos"),
}

# Noun-form: used in range-wide totals.
#   "25 uploads, 8 edits, 3 renames, 1 deletion."
_ACTION_NOUNS = {
    "upload": ("upload",   "uploads"),
    "edit":   ("edit",     "edits"),
    "rename": ("rename",   "renames"),
    "delete": ("deletion", "deletions"),
}


def _join_naturally(parts: List[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _verb_phrase(action: str, count: int) -> str:
    verb, singular, plural = _ACTION_VERBS.get(
        action, (f"{action}ed", action, f"{action}s")
    )
    noun = singular if count == 1 else plural
    return f"{verb} {count} {noun}"


def _noun_phrase(action: str, count: int) -> str:
    singular, plural = _ACTION_NOUNS.get(action, (action, f"{action}s"))
    noun = singular if count == 1 else plural
    return f"{count} {noun}"


def _ordered_action_items(
    action_counts: Dict[str, int], phrase_fn
) -> List[str]:
    parts: List[str] = []
    seen = set()
    for action in _ACTION_ORDER:
        if action in action_counts:
            parts.append(phrase_fn(action, action_counts[action]))
            seen.add(action)
    # Unknown actions (e.g. future employee_add) fall through in insertion order.
    for action, count in action_counts.items():
        if action not in seen:
            parts.append(phrase_fn(action, count))
    return parts


def summarize_actor_counts(action_counts: Dict[str, int]) -> str:
    """'uploaded 5 photos and edited 2 photos'"""
    return _join_naturally(_ordered_action_items(action_counts, _verb_phrase))


def summarize_action_totals(action_counts: Dict[str, int]) -> str:
    """'25 uploads, 8 edits, 3 renames, and 1 deletion'"""
    return _join_naturally(_ordered_action_items(action_counts, _noun_phrase))


def build_day_summary(actor_buckets: Dict[str, List["ActivityLog"]]) -> str:
    """Multi-actor, per-day narrative. One sentence per actor."""
    sentences: List[str] = []
    for actor_name in sorted(actor_buckets.keys()):
        counts: Dict[str, int] = {}
        for e in actor_buckets[actor_name]:
            counts[e.action] = counts.get(e.action, 0) + 1
        sentences.append(f"{actor_name} {summarize_actor_counts(counts)}.")
    return " ".join(sentences)


def build_range_summary(
    from_date: datetime.date,
    to_date: datetime.date,
    total: int,
    action_counts: Dict[str, int],
    actor_counts: Dict[str, int],
) -> str:
    if total == 0:
        if from_date == to_date:
            return f"No activity on {from_date.isoformat()}."
        return f"No activity between {from_date.isoformat()} and {to_date.isoformat()}."

    if from_date == to_date:
        lead = f"{total} event{'s' if total != 1 else ''} on {from_date.isoformat()}."
    else:
        lead = (
            f"{total} event{'s' if total != 1 else ''} between "
            f"{from_date.isoformat()} and {to_date.isoformat()}."
        )

    parts = [lead]

    if action_counts:
        parts.append(f"By action: {summarize_action_totals(action_counts)}.")

    if actor_counts:
        ranked = sorted(
            actor_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )
        if len(ranked) == 1:
            name, _ = ranked[0]
            parts.append(f"All by {name}.")
        else:
            top_name, top_count = ranked[0]
            parts.append(
                f"Most active: {top_name} ({top_count} event"
                f"{'s' if top_count != 1 else ''})."
            )

    return " ".join(parts)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
pt_app = FastAPI(title="Photo Upload API", version="2.1.0")

pt_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_actor(x_actor: Optional[str] = Header(None)) -> str:
    """The verified username, stamped by nginx from the login session.
    Clients can't fake it as long as nginx is the only way in."""
    actor = (x_actor or "").strip()
    if not actor:
        if REQUIRE_ACTOR:
            raise HTTPException(status_code=401, detail="Missing X-Actor header")
        return "anonymous"
    return actor[:120]


# ---------------------------------------------------------------------------
# Camera and UI pages
# ---------------------------------------------------------------------------
@pt_app.get("/camera")
async def serve_camera_app():
    return FileResponse(BASE_DIR / "camera.html")


@pt_app.get("/ui")
async def serve_ui_app():
    return FileResponse(BASE_DIR / "ui.html")


# ---------------------------------------------------------------------------
# UPLOAD
# ---------------------------------------------------------------------------
@pt_app.post("/upload", response_model=PhotoOut, status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),  # ignored, kept so old clients don't break
    display_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # comma-separated
    actor: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    original_name = file.filename or "photo.jpg"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext or 'unknown'}'. "
                   f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Uploaded file must be an image")

    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stored_name = (
        f"{safe_component(actor, 'user')}_{timestamp_str}_"
        f"{uuid.uuid4().hex[:8]}{ext}"
    )
    file_location = f"{UPLOAD_DIR}/{stored_name}"

    size = save_upload(file, file_location, MAX_UPLOAD_BYTES)

    record = PhotoRecord(
        owner_name=actor,
        filename=stored_name,
        filepath=f"uploads/{stored_name}",
        original_filename=original_name,
        display_name=(display_name or "").strip()
        or os.path.splitext(original_name)[0],
        description=(description or "").strip() or None,
        tags=dump_tags(parse_tags(tags)),
        content_type=file.content_type,
        size_bytes=size,
    )
    db.add(record)
    db.flush()  # assign id so the log entry can reference it

    log_activity(
        db, actor, "upload", photo=record,
        details={
            "size_bytes": size,
            "content_type": file.content_type,
            "original_filename": original_name,
        },
    )

    db.commit()
    db.refresh(record)
    return serialize(record)

# ---------------------------------------------------------------------------
# LIST / SEARCH  (paginated, filterable, sortable)
# ---------------------------------------------------------------------------
@pt_app.get("/photos", response_model=PhotoListResponse)
def list_photos(
    owner: Optional[str] = Query(None, description="Filter by owner name"),
    q: Optional[str] = Query(None, description="Search name/description/tags"),
    tag: Optional[str] = Query(None, description="Filter by a single tag"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("timestamp", pattern="^(timestamp|display_name|size_bytes|id)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    filters = []
    if owner:
        filters.append(PhotoRecord.owner_name == owner)
    if tag:
        filters.append(PhotoRecord.tags.ilike(f"%{tag}%"))
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                PhotoRecord.display_name.ilike(like),
                PhotoRecord.original_filename.ilike(like),
                PhotoRecord.description.ilike(like),
                PhotoRecord.tags.ilike(like),
            )
        )

    total = db.query(func.count(PhotoRecord.id)).filter(*filters).scalar() or 0

    column = getattr(PhotoRecord, sort_by)
    ordering = column.asc() if order == "asc" else column.desc()

    photos = (
        db.query(PhotoRecord)
        .filter(*filters)
        .order_by(ordering)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serialize(p) for p in photos],
    }


# ---------------------------------------------------------------------------
# STATS
# ---------------------------------------------------------------------------
@pt_app.get("/stats")
def get_stats(
    owner: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    filters = [PhotoRecord.owner_name == owner] if owner else []
    total = db.query(func.count(PhotoRecord.id)).filter(*filters).scalar() or 0
    total_bytes = (
        db.query(func.coalesce(func.sum(PhotoRecord.size_bytes), 0))
        .filter(*filters)
        .scalar()
        or 0
    )
    distinct_users = (
        db.query(func.count(func.distinct(PhotoRecord.owner_name))).scalar() or 0
    )
    return {
        "total_photos": total,
        "total_bytes": int(total_bytes),
        "total_megabytes": round(int(total_bytes) / (1024 * 1024), 2),
        "distinct_users": distinct_users,
    }


# ---------------------------------------------------------------------------
# BULK DELETE  (declared before /photos/{photo_id} so it isn't shadowed)
# ---------------------------------------------------------------------------
@pt_app.post("/photos/bulk-delete", response_model=DeleteResponse)
def bulk_delete_photos(
    payload: BulkDeleteRequest,
    actor: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    photos = db.query(PhotoRecord).filter(PhotoRecord.id.in_(payload.ids)).all()
    missing: List[str] = []

    for photo in photos:
        gone = delete_file_on_disk(photo)
        if gone:
            missing.append(gone)
        log_activity(
            db, actor, "delete", photo=photo,
            details={
                "size_bytes": photo.size_bytes,
                "content_type": photo.content_type,
                "filename": photo.filename,
                "missing_on_disk": bool(gone),
                "bulk": True,
            },
        )
        db.delete(photo)

    db.commit()
    return {
        "status": "deleted",
        "deleted": len(photos),
        "missing_files": missing,
    }

# ---------------------------------------------------------------------------
# READ ONE  (metadata)
# ---------------------------------------------------------------------------
@pt_app.get("/photos/{photo_id}", response_model=PhotoOut)
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    return serialize(get_photo_or_404(db, photo_id))


# ---------------------------------------------------------------------------
# SERVE THE IMAGE
# ---------------------------------------------------------------------------
@pt_app.get("/photos/{photo_id}/file")
def get_photo_file(photo_id: int, db: Session = Depends(get_db)):
    """Inline image, good for <img src="...">."""
    photo = get_photo_or_404(db, photo_id)
    path = resolve_stored_path(photo)
    return FileResponse(
        path,
        media_type=photo.content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@pt_app.get("/photos/{photo_id}/download")
def download_photo(photo_id: int, db: Session = Depends(get_db)):
    """Forces a browser download with the friendly name."""
    photo = get_photo_or_404(db, photo_id)
    path = resolve_stored_path(photo)

    ext = os.path.splitext(photo.filename or path)[1] or ".jpg"
    download_name = f"{safe_component(photo.display_name or 'photo', 'photo')}{ext}"

    return FileResponse(
        path,
        media_type=photo.content_type or "application/octet-stream",
        filename=download_name,
    )


# ---------------------------------------------------------------------------
# UPDATE METADATA (partial)
# ---------------------------------------------------------------------------
@pt_app.patch("/photos/{photo_id}", response_model=PhotoOut)
def update_photo(
    photo_id: int,
    payload: PhotoUpdate,
    actor: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    photo = get_photo_or_404(db, photo_id)
    data = payload.model_dump(exclude_unset=True)

    before = {
        "display_name": photo.display_name,
        "description": photo.description,
        "tags": parse_tags(photo.tags),
    }

    if "display_name" in data:
        new_name = (data["display_name"] or "").strip()
        if not new_name:
            raise HTTPException(
                status_code=422, detail="display_name cannot be empty"
            )
        photo.display_name = new_name

    if "description" in data:
        photo.description = (data["description"] or "").strip() or None

    if "tags" in data:
        photo.tags = dump_tags(data["tags"])

    after = {
        "display_name": photo.display_name,
        "description": photo.description,
        "tags": parse_tags(photo.tags),
    }
    changes = {
        k: {"from": before[k], "to": after[k]}
        for k in before
        if before[k] != after[k]
    }
    if changes:
        log_activity(db, actor, "edit", photo=photo, details={"changes": changes})

    photo.updated_at = datetime.datetime.now()
    db.commit()
    db.refresh(photo)
    return serialize(photo)

# ---------------------------------------------------------------------------
# RENAME (title, and optionally the file on disk)
# ---------------------------------------------------------------------------
@pt_app.post("/photos/{photo_id}/rename", response_model=PhotoOut)
def rename_photo(
    photo_id: int,
    payload: RenameRequest,
    actor: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    photo = get_photo_or_404(db, photo_id)

    new_display = payload.display_name.strip()
    if not new_display:
        raise HTTPException(status_code=422, detail="display_name cannot be empty")

    details: dict = {
        "display_name": {"from": photo.display_name, "to": new_display}
    }

    if payload.rename_file:
        old_path = resolve_stored_path(photo)

        ext = os.path.splitext(photo.filename or old_path)[1].lower() or ".jpg"
        stem = safe_component(new_display, "photo")
        owner = safe_component(photo.owner_name, "user")
        new_filename = f"{owner}_{stem}_{uuid.uuid4().hex[:6]}{ext}"
        new_path = f"{UPLOAD_DIR}/{new_filename}"

        try:
            os.replace(old_path, new_path)
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"Could not rename file on disk: {exc}"
            )

        details["filename"] = {
            "from": photo.filename, "to": new_filename
        }
        photo.filename = new_filename
        photo.filepath = f"uploads/{new_filename}"

    photo.display_name = new_display
    photo.updated_at = datetime.datetime.now()
    log_activity(db, actor, "rename", photo=photo, details=details)
    db.commit()
    db.refresh(photo)
    return serialize(photo)

# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
@pt_app.delete("/photos/{photo_id}", response_model=DeleteResponse)
def delete_photo(
    photo_id: int,
    actor: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    photo = get_photo_or_404(db, photo_id)
    missing = delete_file_on_disk(photo)

    log_activity(
        db, actor, "delete", photo=photo,
        details={
            "size_bytes": photo.size_bytes,
            "content_type": photo.content_type,
            "filename": photo.filename,
            "missing_on_disk": bool(missing),
        },
    )

    db.delete(photo)
    db.commit()
    return {
        "status": "deleted",
        "id": photo_id,
        "missing_files": [missing] if missing else [],
    }

# ---------------------------------------------------------------------------
# ACTIVITY — raw feed
# ---------------------------------------------------------------------------
@pt_app.get("/activity", response_model=ActivityListResponse)
def list_activity(
    actor: Optional[str] = Query(None, description="Filter by actor"),
    action: Optional[str] = Query(
        None, pattern="^(upload|edit|rename|delete)$"
    ),
    photo_id: Optional[int] = Query(None),
    from_date: Optional[datetime.date] = Query(None),
    to_date: Optional[datetime.date] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _requester: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    filters = []
    if actor:
        filters.append(ActivityLog.actor == actor)
    if action:
        filters.append(ActivityLog.action == action)
    if photo_id is not None:
        filters.append(ActivityLog.photo_id == photo_id)
    if from_date:
        filters.append(
            ActivityLog.created_at
            >= datetime.datetime.combine(from_date, datetime.time.min)
        )
    if to_date:
        filters.append(
            ActivityLog.created_at
            <= datetime.datetime.combine(to_date, datetime.time.max)
        )

    total = db.query(func.count(ActivityLog.id)).filter(*filters).scalar() or 0

    rows = (
        db.query(ActivityLog)
        .filter(*filters)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serialize_activity(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# ACTIVITY — daily digest (calendar view)
# ---------------------------------------------------------------------------
@pt_app.get("/activity/digest", response_model=DigestResponse)
def get_activity_digest(
    from_date: Optional[datetime.date] = Query(None, description="Defaults to today"),
    to_date: Optional[datetime.date] = Query(None, description="Defaults to from_date"),
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None, pattern="^(upload|edit|rename|delete)$"),
    include_items: bool = Query(True, description="Set false for a compact calendar"),
    _requester: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    today = datetime.date.today()
    from_date = from_date or today
    to_date = to_date or from_date

    if to_date < from_date:
        raise HTTPException(status_code=422, detail="to_date must be >= from_date")
    if (to_date - from_date).days > 366:
        raise HTTPException(
            status_code=422, detail="Date range too large (max 366 days)"
        )

    start = datetime.datetime.combine(from_date, datetime.time.min)
    end = datetime.datetime.combine(to_date, datetime.time.max)

    filters = [ActivityLog.created_at >= start, ActivityLog.created_at <= end]
    if actor:
        filters.append(ActivityLog.actor == actor)
    if action:
        filters.append(ActivityLog.action == action)

    rows = (
        db.query(ActivityLog)
        .filter(*filters)
        .order_by(ActivityLog.created_at.asc(), ActivityLog.id.asc())
        .all()
    )

    # ---- aggregate across the whole range --------------------------------
    totals_by_action: Dict[str, int] = {}
    totals_by_actor_counts: Dict[str, int] = {}
    for r in rows:
        totals_by_action[r.action] = totals_by_action.get(r.action, 0) + 1
        totals_by_actor_counts[r.actor] = totals_by_actor_counts.get(r.actor, 0) + 1

    totals_by_actor = [
        {"actor": a, "count": c}
        for a, c in sorted(
            totals_by_actor_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]

    grand_total = len(rows)
    range_summary = build_range_summary(
        from_date, to_date, grand_total, totals_by_action, totals_by_actor_counts
    )

    # ---- group by day -> actor -------------------------------------------
    grouped: Dict[str, Dict[str, List[ActivityLog]]] = {}
    for r in rows:
        day_key = r.created_at.date().isoformat()
        grouped.setdefault(day_key, {}).setdefault(r.actor, []).append(r)

    days_out: List[dict] = []
    for day_key in sorted(grouped.keys()):
        actor_buckets = grouped[day_key]

        actor_summaries: List[dict] = []
        day_items: List[ActivityLog] = []
        day_action_counts: Dict[str, int] = {}

        for actor_name in sorted(actor_buckets.keys()):
            entries = actor_buckets[actor_name]
            action_counts: Dict[str, int] = {}
            for e in entries:
                action_counts[e.action] = action_counts.get(e.action, 0) + 1
                day_action_counts[e.action] = day_action_counts.get(e.action, 0) + 1
            actor_summaries.append(
                {
                    "actor": actor_name,
                    "count": len(entries),
                    "actions": action_counts,
                }
            )
            day_items.extend(entries)

        day_items.sort(key=lambda e: (e.created_at, e.id))

        top_actor = (
            max(actor_summaries, key=lambda a: a["count"])["actor"]
            if actor_summaries
            else None
        )
        top_action = (
            max(day_action_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if day_action_counts
            else None
        )

        days_out.append(
            {
                "date": day_key,
                "total": len(day_items),
                "summary": build_day_summary(actor_buckets),
                "highlights": {
                    "top_actor": top_actor,
                    "top_action": top_action,
                    "distinct_actors": len(actor_summaries),
                    "deleted_count": day_action_counts.get("delete", 0),
                },
                "actors": actor_summaries,
                "items": (
                    [serialize_activity(e) for e in day_items]
                    if include_items
                    else []
                ),
            }
        )

    return {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "total": grand_total,
        "summary": range_summary,
        "totals_by_action": totals_by_action,
        "totals_by_actor": totals_by_actor,
        "days": days_out,
    }

@pt_app.get("/photos/{photo_id}/history", response_model=PhotoHistoryResponse)
def get_photo_history(
    photo_id: int,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _requester: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    """Everything that ever happened to one photo — upload, edits, renames, deletion."""
    total = (
        db.query(func.count(ActivityLog.id))
        .filter(ActivityLog.photo_id == photo_id)
        .scalar()
        or 0
    )

    rows = (
        db.query(ActivityLog)
        .filter(ActivityLog.photo_id == photo_id)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    photo = db.get(PhotoRecord, photo_id)
    if photo is not None:
        display_name = (
            photo.display_name or photo.original_filename or photo.filename
        )
    else:
        display_name = rows[0].photo_display_name if rows else None

    return {
        "photo_id": photo_id,
        "photo_display_name": display_name,
        "photo_exists": photo is not None,
        "total": total,
        "items": [serialize_activity(r) for r in rows],
    }
