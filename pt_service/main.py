import os
import re
import uuid
import datetime
import json
from typing import List, Optional, Dict
from pathlib import Path

from fastapi import (
    FastAPI, UploadFile, File, Form, Depends, HTTPException, Query, Header, Request,
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
DB_PATH = Path(os.getenv("PT_DB_PATH") or BASE_DIR / "photos.db")
UPLOAD_DIR = Path(os.getenv("PT_UPLOAD_DIR") or BASE_DIR / "uploads")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
    title = Column(String)
    location_name = Column(String)
    mobile_metadata = Column(String)
    upload_key = Column(String, unique=True)
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
    photo_title = Column(String)
    author = Column(String)
    source = Column(String)

    # Free-form JSON: change diffs, sizes, filenames, etc.
    details = Column(String)

    created_at = Column(
        DateTime, default=datetime.datetime.now, index=True, nullable=False
    )

class PhotoTitleRevision(Base):
    """Last accepted mobile edit, retained even if a photo is deleted."""
    __tablename__ = "photo_title_revisions"
    upload_key = Column(String, primary_key=True)
    revision = Column(Integer, nullable=False)
    title = Column(String, nullable=False)

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
            "title": "VARCHAR",
            "location_name": "VARCHAR",
            "mobile_metadata": "VARCHAR",
            "upload_key": "VARCHAR",
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

        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_photo_upload_key ON photo_records(upload_key)"))

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

        columns = {r[1] for r in conn.execute(text("PRAGMA table_info(activity_logs)"))}
        for name in ("photo_title", "author", "source"):
            if name not in columns:
                conn.execute(text(f"ALTER TABLE activity_logs ADD COLUMN {name} VARCHAR"))
        # Recover only supported values, never treat the old display name as a title.
        # Follow upload generations: SQLite IDs may have been reused after deletion.
        live = {r.id: r for r in conn.execute(text("SELECT id,title,owner_name,mobile_metadata FROM photo_records"))}
        snapshots = {}
        for row in conn.execute(text("SELECT id,photo_id,action,actor,details,photo_title,author,source FROM activity_logs ORDER BY id")).fetchall():
            try:
                detail = json.loads(row.details or '{}')
                if not isinstance(detail, dict): detail = {}
            except (ValueError, TypeError):
                detail = {}
            if row.action == 'upload':
                title = detail.get('title') or 'Untitled Photo'
                author = detail.get('full_name') or row.actor
                source = detail.get('source')
                current = live.get(row.photo_id)
                if current:
                    try: current_meta = json.loads(current.mobile_metadata or '{}')
                    except (ValueError, TypeError): current_meta = {}
                    if isinstance(current_meta, dict) and detail.get('upload_id') and detail.get('upload_id') == current_meta.get('upload_id'):
                        title = current.title or title
                        author = current.owner_name or author
                snapshots[row.photo_id] = (title, author, source)
            title, author, source = snapshots.get(row.photo_id, ('Untitled Photo', 'Unknown author', None))
            conn.execute(text("UPDATE activity_logs SET photo_title=COALESCE(photo_title,:title),author=COALESCE(author,:author),source=COALESCE(source,:source) WHERE id=:id"),
                         dict(id=row.id,title=title,author=author,source=source if source in ('camera','gallery') else None))


ensure_schema()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class PhotoOut(BaseModel):
    title: str = "Untitled Photo"
    location_name: Optional[str] = None
    mobile_metadata: Optional[dict] = None
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
    photo_title: str = "Untitled Photo"
    author: str = "Unknown author"
    source: Optional[str] = None
    id: int
    actor: str
    action: str
    photo_id: Optional[int] = None
    photo_display_name: Optional[str] = None
    photo_exists: Optional[bool] = None
    photo_url: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    details: dict = Field(default_factory=dict)
    created_at: datetime.datetime


class ActorStat(BaseModel):
    actor: str
    total: int
    last_seen: datetime.datetime
    actions: Dict[str, int] = Field(default_factory=dict)


class ActorListResponse(BaseModel):
    actors: List[ActorStat]


class PhotoBatchRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=200)


class PhotoBatchResponse(BaseModel):
    found: List[PhotoOut]
    missing: List[int]

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
        "title": photo.title or "Untitled Photo",
        "location_name": photo.location_name,
        "mobile_metadata": json.loads(photo.mobile_metadata) if photo.mobile_metadata else None,
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

def serialize_activity(
    log: ActivityLog, photo_exists: Optional[bool] = None
) -> dict:
    details: dict = {}
    if log.details:
        try:
            details = json.loads(log.details)
        except (ValueError, TypeError):
            details = {"raw": log.details}

    pid = log.photo_id
    if pid is None:
        # Non-photo action (future: employee_add, document_issue, etc.)
        exists: Optional[bool] = None
        photo_url = download_url = thumbnail_url = None
    elif photo_exists:
        exists = True
        photo_url = f"/photos/{pid}/file"
        download_url = f"/photos/{pid}/download"
        thumbnail_url = f"/photos/{pid}/file"  # same for now; swap when we add thumbnails
    else:
        # Caller said "gone" OR didn't tell us — hide links defensively.
        exists = False
        photo_url = download_url = thumbnail_url = None

    return {
        "id": log.id,
        "actor": log.actor,
        "action": "edit" if log.action == "rename" else log.action,
        "photo_id": pid,
        "photo_display_name": log.photo_display_name,
        "photo_title": log.photo_title or "Untitled Photo",
        "author": log.author or "Unknown author",
        "source": log.source,
        "photo_exists": exists,
        "photo_url": photo_url,
        "download_url": download_url,
        "thumbnail_url": thumbnail_url,
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
    try:
        metadata = json.loads(photo.mobile_metadata or "{}") if photo is not None else {}
    except (ValueError, TypeError):
        metadata = {}
    if not isinstance(metadata, dict): metadata = {}
    entry = ActivityLog(
        photo_title=(photo.title or "Untitled Photo") if photo is not None else "Untitled Photo",
        author=photo.owner_name if photo is not None else "Unknown author",
        source=metadata.get("source") if metadata.get("source") in ("camera", "gallery") else None,
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


def concise_activity_summary(rows):
    labels = {"upload": ("upload", "uploads"), "edit": ("edit", "edits"), "delete": ("deletion", "deletions")}
    parts = []
    for action, (one, many) in labels.items():
        count = sum(("edit" if r.action == "rename" else r.action) == action for r in rows)
        if count: parts.append(f"{count} {one if count == 1 else many}")
    authors = {r.author for r in rows if r.author and r.author != "Unknown author"}
    parts.append(f"{len(authors)} {'author' if len(authors) == 1 else 'authors'}")
    return " · ".join(parts) if rows else "No activity"


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

def _photo_exists_map(db: Session, photo_ids: List[Optional[int]]) -> Dict[int, bool]:
    """Batch-check which photo ids still exist. One query, no N+1."""
    ids = [pid for pid in set(photo_ids) if pid is not None]
    if not ids:
        return {}
    rows = db.query(PhotoRecord.id).filter(PhotoRecord.id.in_(ids)).all()
    present = {r[0] for r in rows}
    return {pid: (pid in present) for pid in ids}

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
@pt_app.post("/upload")
async def upload_photo():
    """Legacy browser uploads are disabled; employee uploads use /mobile-upload."""
    raise HTTPException(status_code=403, detail="Only employees can upload photos through the Northpoint Android app.")

# ---------------------------------------------------------------------------
# LIST / SEARCH  (paginated, filterable, sortable)
# ---------------------------------------------------------------------------
def photo_business_date():
    """Library dates follow the existing Asia/Manila timestamp convention."""
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("Asia/Manila")).date()


def _effective_upload_time(metadata_raw, fallback_timestamp):
    if metadata_raw:
        try:
            meta = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
            raw = meta.get("uploaded_at") if isinstance(meta, dict) else None
            if isinstance(raw, str) and raw.strip():
                parsed = datetime.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(MANILA_TZ).replace(tzinfo=None)
                return parsed
        except (ValueError, TypeError):
            pass
    return fallback_timestamp


def photo_time_bounds(timeframe, on_date=None):
    day = on_date or photo_business_date()
    if timeframe == "all":
        return None
    start_day = day if timeframe == "today" else day - datetime.timedelta(days=day.weekday())
    return (datetime.datetime.combine(start_day, datetime.time.min),
            datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min))


@pt_app.get("/photos", response_model=PhotoListResponse)
def list_photos(
    timeframe: str = Query("all", pattern="^(today|week|all)$"),
    on_date: Optional[datetime.date] = Query(None, description="Business date in Asia/Manila; defaults to today"),
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
    bounds = photo_time_bounds(timeframe, on_date)
    if owner:
        filters.append(PhotoRecord.owner_name == owner)
    if tag:
        filters.append(PhotoRecord.tags.ilike(f"%{tag}%"))
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                PhotoRecord.owner_name.ilike(like),                PhotoRecord.display_name.ilike(like),
                PhotoRecord.original_filename.ilike(like),
                PhotoRecord.description.ilike(like),
                PhotoRecord.tags.ilike(like),
            )
        )

    if bounds or sort_by == "timestamp":
        matched = db.query(PhotoRecord).filter(*filters).all()
        if bounds:
            matched = [
                p for p in matched
                if (ts := _effective_upload_time(p.mobile_metadata, p.timestamp)) is not None
                and bounds[0] <= ts < bounds[1]
            ]
        total = len(matched)
        reverse = order == "desc"
        if sort_by == "timestamp":
            matched.sort(
                key=lambda p: (_effective_upload_time(p.mobile_metadata, p.timestamp) or datetime.datetime.min, p.id),
                reverse=reverse,
            )
        elif sort_by == "display_name":
            matched.sort(key=lambda p: ((p.display_name or ""), p.id), reverse=reverse)
        elif sort_by == "size_bytes":
            matched.sort(key=lambda p: (p.size_bytes or 0, p.id), reverse=reverse)
        else:
            matched.sort(key=lambda p: p.id, reverse=reverse)
        photos = matched[offset : offset + limit]
    else:
        total = db.query(func.count(PhotoRecord.id)).filter(*filters).scalar() or 0

        column = getattr(PhotoRecord, sort_by)
        ordering = column.asc() if order == "asc" else column.desc()

        photos = (
            db.query(PhotoRecord)
            .filter(*filters)
            .order_by(ordering, PhotoRecord.id.asc() if order == "asc" else PhotoRecord.id.desc())
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
    include_employees: bool = Query(False, description="Include employee upload counters and Philippine business date"),
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
    if not include_employees:
        return {"total_photos": total, "total_bytes": int(total_bytes),
                "total_megabytes": round(int(total_bytes) / (1024 * 1024), 2),
                "distinct_users": distinct_users}
    day = photo_business_date()
    today_start, tomorrow = photo_time_bounds("today", day)
    counts = {}
    for name, metadata, timestamp in db.query(
        PhotoRecord.owner_name, PhotoRecord.mobile_metadata, PhotoRecord.timestamp
    ).filter(*filters).all():
        try:
            meta = json.loads(metadata or "{}")
        except (ValueError, TypeError):
            meta = {}
        employee_id = meta.get("employee_id") if isinstance(meta, dict) else None
        if not isinstance(employee_id, int) or isinstance(employee_id, bool) or employee_id < 1:
            employee_id = None
        key = (employee_id, "" if employee_id else name)
        bucket = counts.setdefault(key, {"employee_id": employee_id, "owner": name,
                                         "uploads_today": 0, "total_uploads": 0})
        bucket["total_uploads"] += 1
        uploaded_ts = _effective_upload_time(meta, timestamp)
        bucket["uploads_today"] += int(uploaded_ts is not None and today_start <= uploaded_ts < tomorrow)
    employee_counts = sorted(counts.values(), key=lambda row: (row["owner"].casefold(), row["employee_id"] or 0))
    return {
        "business_date": day.isoformat(),
        "timezone": "Asia/Manila",
        "week_starts_on": "Monday",
        "uploads_today": sum(row["uploads_today"] for row in employee_counts),
        "employee_counts": employee_counts,
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
    log_activity(db, actor, "edit", photo=photo, details=details)
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
    author: Optional[str] = Query(None),
    actor: Optional[str] = Query(None, description="Case-insensitive exact match"),
    action: Optional[str] = Query(
        None, pattern="^(upload|edit|rename|delete)$"
    ),
    photo_id: Optional[int] = Query(None),
    q: Optional[str] = Query(
        None,
        description="Free text — matches actor, photo name, and details JSON",
    ),
    photo_display_name: Optional[str] = Query(
        None, description="Partial match on the snapshot photo name"
    ),
    from_date: Optional[datetime.date] = Query(None),
    to_date: Optional[datetime.date] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _requester: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    filters = []
    if author:
        filters.append(func.lower(ActivityLog.author) == author.lower())
    if actor:
        filters.append(func.lower(ActivityLog.actor) == actor.lower())
    if action:
        filters.append(ActivityLog.action.in_(("edit", "rename")) if action == "edit" else ActivityLog.action == action)
    if photo_id is not None:
        filters.append(ActivityLog.photo_id == photo_id)
    if photo_display_name:
        filters.append(
            ActivityLog.photo_display_name.ilike(f"%{photo_display_name}%")
        )
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                ActivityLog.author.ilike(like),
                ActivityLog.photo_title.ilike(like),
                ActivityLog.actor.ilike(like),
                ActivityLog.photo_display_name.ilike(like),
                ActivityLog.details.ilike(like),
            )
        )
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

    exists_map = _photo_exists_map(db, [r.photo_id for r in rows])

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            serialize_activity(r, exists_map.get(r.photo_id) if r.photo_id else None)
            for r in rows
        ],
    }

# ---------------------------------------------------------------------------
# ACTIVITY — daily digest (calendar view)
# ---------------------------------------------------------------------------
@pt_app.get("/activity/digest", response_model=DigestResponse)
def get_activity_digest(
    author: Optional[str] = Query(None),
    from_date: Optional[datetime.date] = Query(None),
    to_date: Optional[datetime.date] = Query(None),
    actor: Optional[str] = Query(None, description="Case-insensitive exact match"),
    action: Optional[str] = Query(None, pattern="^(upload|edit|rename|delete)$"),
    q: Optional[str] = Query(
        None,
        description="Free text — matches actor, photo name, and details JSON",
    ),
    photo_display_name: Optional[str] = Query(None),
    include_items: bool = Query(True),
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
    if author:
        filters.append(func.lower(ActivityLog.author) == author.lower())
    if actor:
        filters.append(func.lower(ActivityLog.actor) == actor.lower())
    if action:
        filters.append(ActivityLog.action.in_(("edit", "rename")) if action == "edit" else ActivityLog.action == action)
    if photo_display_name:
        filters.append(
            ActivityLog.photo_display_name.ilike(f"%{photo_display_name}%")
        )
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                ActivityLog.author.ilike(like),
                ActivityLog.photo_title.ilike(like),
                ActivityLog.actor.ilike(like),
                ActivityLog.photo_display_name.ilike(like),
                ActivityLog.details.ilike(like),
            )
        )

    rows = (
        db.query(ActivityLog)
        .filter(*filters)
        .order_by(ActivityLog.created_at.asc(), ActivityLog.id.asc())
        .all()
    )

    exists_map = _photo_exists_map(db, [r.photo_id for r in rows])

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
                "summary": concise_activity_summary(day_items),
                "highlights": {
                    "top_actor": top_actor,
                    "top_action": top_action,
                    "distinct_actors": len(actor_summaries),
                    "deleted_count": day_action_counts.get("delete", 0),
                },
                "actors": actor_summaries,
                "items": (
                    [
                        serialize_activity(
                            e, exists_map.get(e.photo_id) if e.photo_id else None
                        )
                        for e in day_items
                    ]
                    if include_items
                    else []
                ),
            }
        )

    return {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "total": grand_total,
        "summary": concise_activity_summary(rows),
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
    photo_exists = photo is not None

    if photo_exists:
        display_name = (
            photo.title or "Untitled Photo"
        )
    else:
        display_name = (rows[0].photo_title or "Untitled Photo") if rows else "Untitled Photo"

    return {
        "photo_id": photo_id,
        "photo_display_name": display_name,
        "photo_exists": photo_exists,
        "total": total,
        "items": [serialize_activity(r, photo_exists) for r in rows],
    }

@pt_app.get("/activity/authors", response_model=ActorListResponse)
def list_activity_authors(_requester: str = Depends(get_actor), db: Session = Depends(get_db)):
    rows = db.query(ActivityLog.author, func.count(ActivityLog.id), func.max(ActivityLog.created_at)).group_by(ActivityLog.author).all()
    return {"actors": [{"actor": name or "Unknown author", "total": count, "last_seen": last, "actions": {}} for name,count,last in rows]}

@pt_app.get("/activity/actors", response_model=ActorListResponse)
def list_activity_actors(
    from_date: Optional[datetime.date] = Query(None),
    to_date: Optional[datetime.date] = Query(None),
    q: Optional[str] = Query(None, description="Partial match on actor name"),
    _requester: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    filters = []
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
    if q:
        filters.append(ActivityLog.actor.ilike(f"%{q}%"))

    rows = db.query(ActivityLog).filter(*filters).all()

    agg: Dict[str, dict] = {}
    for r in rows:
        bucket = agg.setdefault(
            r.actor,
            {"actor": r.actor, "total": 0, "actions": {}, "last_seen": r.created_at},
        )
        bucket["total"] += 1
        bucket["actions"][r.action] = bucket["actions"].get(r.action, 0) + 1
        if r.created_at > bucket["last_seen"]:
            bucket["last_seen"] = r.created_at

    actors = sorted(agg.values(), key=lambda x: (-x["total"], x["actor"]))
    return {"actors": actors}

@pt_app.post("/photos/batch", response_model=PhotoBatchResponse)
def get_photos_batch(
    payload: PhotoBatchRequest,
    _requester: str = Depends(get_actor),
    db: Session = Depends(get_db),
):
    """Fetch many photo records in one call, e.g. for a gallery of
    uploads a specific actor did on a specific day."""
    # dedupe while preserving order
    seen: set = set()
    unique_ids: List[int] = []
    for pid in payload.ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)

    photos = (
        db.query(PhotoRecord).filter(PhotoRecord.id.in_(unique_ids)).all()
    )
    by_id = {p.id: p for p in photos}

    found = [serialize(by_id[pid]) for pid in unique_ids if pid in by_id]
    missing = [pid for pid in unique_ids if pid not in by_id]

    return {"found": found, "missing": missing}

# Mobile uploads are separate from the existing browser upload contract.
from auth.mobile_access import tracker_identity
from pydantic import ConfigDict, AwareDatetime, model_validator
from sqlalchemy.exc import IntegrityError
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen
from zoneinfo import ZoneInfo

MANILA_TZ = ZoneInfo('Asia/Manila')
_GEOCODE_CACHE: Dict[tuple[float, float], str] = {}
_GEOCODE_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_EXIF_TIME_RE = re.compile(
    r'^(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$'
)


def _to_manila_aware(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MANILA_TZ)
    return dt.astimezone(MANILA_TZ)


def _parse_exif_datetime_str(raw: object, offset_raw: object = None) -> Optional[datetime.datetime]:
    if not isinstance(raw, str):
        return None
    m = _EXIF_TIME_RE.match(raw.strip())
    if not m:
        return None
    y, mo, d, h, mi, s, inline_tz = m.groups()
    try:
        dt = datetime.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    except ValueError:
        return None
    if dt.year < 1970:
        return None
    tz_raw = inline_tz or (offset_raw.strip() if isinstance(offset_raw, str) and offset_raw.strip() else None)
    tzinfo: datetime.tzinfo = MANILA_TZ
    if tz_raw == 'Z':
        tzinfo = datetime.timezone.utc
    elif tz_raw and re.fullmatch(r'[+-]\d{2}:?\d{2}', tz_raw):
        clean = tz_raw.replace(':', '')
        sign = 1 if clean[0] == '+' else -1
        delta = datetime.timedelta(hours=int(clean[1:3]), minutes=int(clean[3:5]))
        tzinfo = datetime.timezone(sign * delta)
    return dt.replace(tzinfo=tzinfo).astimezone(MANILA_TZ)


def _extract_pillow_exif_taken_at(image_path: Path) -> Optional[datetime.datetime]:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None
            sub_ifd = exif.get_ifd(0x8769) or {}
            for tag_id, offset_tag_id in ((36867, 36881), (36868, 36882)):
                raw = sub_ifd.get(tag_id) or exif.get(tag_id)
                if raw:
                    offset_raw = sub_ifd.get(offset_tag_id) or sub_ifd.get(36880) or exif.get(offset_tag_id)
                    parsed = _parse_exif_datetime_str(raw, offset_raw)
                    if parsed is not None:
                        return parsed
    except Exception:
        return None
    return None


def _format_place_label(body: object) -> Optional[str]:
    if not isinstance(body, dict) or body.get('error'):
        return None
    address = body.get('address')
    if isinstance(address, dict):
        groups = (
            ('building', 'amenity', 'tourism', 'leisure'),
            ('road', 'pedestrian', 'footway', 'path'),
            ('suburb', 'quarter', 'neighbourhood', 'village'),
            ('city', 'town', 'municipality'),
            ('state',),
        )
        parts: List[str] = []
        seen = set()
        for group in groups:
            for key in group:
                value = address.get(key)
                if isinstance(value, str) and value.strip():
                    cleaned = ' '.join(value.split())
                    if cleaned.casefold() not in seen:
                        seen.add(cleaned.casefold())
                        parts.append(cleaned)
                    break
        if parts:
            return ', '.join(parts)[:400]
    display_name = body.get('display_name')
    if isinstance(display_name, str) and display_name.strip():
        return ' '.join(display_name.split())[:400]
    return None


def _fetch_nominatim_label(url: str) -> Optional[str]:
    req = UrlRequest(
        url,
        headers={
            'User-Agent': 'NorthpointPhotoTracker/2.1 (CS317 field verification)',
            'Accept': 'application/json',
        },
    )
    with urlopen(req, timeout=2.5) as resp:
        raw = resp.read(65537)
        if len(raw) <= 65536:
            return _format_place_label(json.loads(raw))
    return None


def _resolve_location_name(db: Session, latitude: float, longitude: float) -> Optional[str]:
    cache_key = (round(latitude, 5), round(longitude, 5))
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]
    # Reuse geocoding/worker.py cache if present in photos.db.
    try:
        coord_key = json.dumps([latitude, longitude], separators=(',', ':'))
        cached = db.execute(
            text('SELECT label FROM photo_geocode_cache WHERE coordinate_key = :k'),
            {'k': coord_key},
        ).fetchone()
        if cached and isinstance(cached[0], str) and cached[0].strip():
            label = cached[0].strip()[:400]
            _GEOCODE_CACHE[cache_key] = label
            return label
    except Exception:
        pass
    if os.getenv('PT_REVERSE_GEOCODE', '1') == '0':
        return None
    query = urlencode({
        'format': 'jsonv2',
        'lat': latitude,
        'lon': longitude,
        'addressdetails': 1,
        'zoom': 18,
        'accept-language': 'en',
    })
    geocoder_url = (os.getenv('GEOCODER_URL') or '').strip().rstrip('/')
    url = (
        f'{geocoder_url}/reverse?{query}'
        if geocoder_url
        else f'https://nominatim.openstreetmap.org/reverse?{query}'
    )
    try:
        label = _GEOCODE_EXECUTOR.submit(_fetch_nominatim_label, url).result(timeout=3.5)
        if label:
            if len(_GEOCODE_CACHE) >= 512:
                _GEOCODE_CACHE.clear()
            _GEOCODE_CACHE[cache_key] = label
            return label
    except Exception:
        return None
    return None


def _format_manila_watermark_time(dt: datetime.datetime) -> str:
    manila = _to_manila_aware(dt)
    hour_12 = manila.strftime('%I:%M %p').lstrip('0')
    return f"{manila.strftime('%b')} {manila.day}, {manila.year} | {hour_12} PHT"


def _load_watermark_fonts(size: int):
    from PIL import ImageFont
    bold_candidates = (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
    )
    reg_candidates = (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        'C:/Windows/Fonts/arial.ttf',
    )
    bold_font = reg_font = None
    for candidate in bold_candidates:
        if os.path.isfile(candidate):
            try:
                bold_font = ImageFont.truetype(candidate, size)
                break
            except OSError:
                pass
    for candidate in reg_candidates:
        if os.path.isfile(candidate):
            try:
                reg_font = ImageFont.truetype(candidate, max(12, int(size * 0.88)))
                break
            except OSError:
                pass
    if bold_font and reg_font:
        return bold_font, reg_font, True
    try:
        return (
            bold_font or ImageFont.load_default(size=size),
            reg_font or ImageFont.load_default(size=max(12, int(size * 0.88))),
            True,
        )
    except TypeError:
        default_font = ImageFont.load_default()
        return bold_font or default_font, reg_font or default_font, False


def _wrap_watermark_text(draw, text_value: str, font, max_width: int, max_lines: int = 2) -> List[str]:
    words = text_value.split()
    if not words:
        return []
    lines: List[str] = []
    idx = 0
    while idx < len(words) and len(lines) < max_lines:
        line = words[idx]
        idx += 1
        while idx < len(words):
            candidate = f'{line} {words[idx]}'
            if draw.textlength(candidate, font=font) <= max_width:
                line = candidate
                idx += 1
            else:
                break
        if len(lines) == max_lines - 1 and idx < len(words):
            line = f"{line} {' '.join(words[idx:])}"
            while len(line) > 4 and draw.textlength(line + '...', font=font) > max_width:
                line = line[:-1].rstrip()
            line = line + '...'
            idx = len(words)
        lines.append(line)
    return lines


def _apply_photo_watermark(
    image_path: Path,
    ext: str,
    *,
    employee_name: str,
    photo_title: str,
    verified_dt: datetime.datetime,
    location_name: Optional[str],
    latitude: float,
    longitude: float,
    source: str,
    has_exif: bool = False,
) -> int:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError:
        return image_path.stat().st_size
    try:
        with Image.open(image_path) as opened:
            img = ImageOps.exif_transpose(opened)
            base = img.convert('RGBA')
        width, height = base.size
        if width < 64 or height < 64:
            return image_path.stat().st_size
        font_size = max(14, min(32, int(width * 0.023)))
        bold_font, reg_font, unicode_ok = _load_watermark_fonts(font_size)
        sep = ' | '
        time_text = _format_manila_watermark_time(verified_dt)
        header_text = f'{employee_name}{sep}{photo_title}'
        if source == 'camera':
            meta_text = f'{time_text}{sep}Camera Photo'
            coords_text = f'GPS: {latitude:.6f}, {longitude:.6f}'
            loc_text = f'{location_name}{sep}{coords_text}' if location_name else coords_text
        else:
            time_prefix = 'Taken (EXIF): ' if has_exif else 'Selected: '
            meta_text = f'{time_prefix}{time_text}{sep}Gallery Upload'
            loc_text = 'Capture location unverified'
        if not unicode_ok:
            header_text = header_text.encode('latin-1', 'replace').decode('latin-1')
            meta_text = meta_text.encode('latin-1', 'replace').decode('latin-1')
            loc_text = loc_text.encode('latin-1', 'replace').decode('latin-1')

        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        pad_x = max(14, int(width * 0.025))
        pad_y = max(12, int(height * 0.018))
        max_text_w = max(40, width - 2 * pad_x)

        rows: List[tuple[str, object, tuple[int, int, int, int]]] = []
        for line in _wrap_watermark_text(draw, header_text, bold_font, max_text_w, max_lines=2):
            rows.append((line, bold_font, (255, 255, 255, 255)))
        for line in _wrap_watermark_text(draw, meta_text, reg_font, max_text_w, max_lines=2):
            rows.append((line, reg_font, (226, 238, 252, 255)))
        for line in _wrap_watermark_text(draw, loc_text, reg_font, max_text_w, max_lines=2):
            rows.append((line, reg_font, (210, 226, 246, 255)))

        line_gap = max(4, int(font_size * 0.25))
        measured: List[tuple[str, object, tuple[int, int, int, int], int]] = []
        total_h = 0
        for text_line, font_obj, color in rows:
            bbox = draw.textbbox((0, 0), text_line, font=font_obj)
            lh = max(font_size, bbox[3] - bbox[1])
            measured.append((text_line, font_obj, color, lh))
            total_h += lh
        total_h += line_gap * max(0, len(measured) - 1)

        banner_h = min(height, total_h + 2 * pad_y)
        banner_top = height - banner_h
        draw.rectangle([(0, banner_top), (width, height)], fill=(15, 29, 48, 198))
        draw.rectangle([(0, banner_top), (width, min(height, banner_top + 3))], fill=(49, 137, 206, 230))

        y = banner_top + pad_y
        for text_line, font_obj, color, lh in measured:
            draw.text((pad_x, y), text_line, font=font_obj, fill=color)
            y += lh + line_gap

        composited = Image.alpha_composite(base, overlay)
        if ext in ('.jpg', '.jpeg'):
            composited.convert('RGB').save(image_path, format='JPEG', quality=88)
        elif ext == '.png':
            composited.save(image_path, format='PNG')
        elif ext == '.webp':
            composited.convert('RGB').save(image_path, format='WEBP', quality=88)
        return image_path.stat().st_size
    except Exception:
        return image_path.stat().st_size


class MobileMetadata(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    upload_id: uuid.UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(ge=0, le=25)
    location_at: AwareDatetime
    selected_at: AwareDatetime
    source: str = Field(pattern='^(camera|gallery)$')
    exif_taken_at: Optional[datetime.datetime] = None
    # Optional for compatibility with older installed APKs. New outbox clients send all three.
    expected_tracker_id: int | None = Field(default=None, gt=0)
    expected_employee_id: int | None = Field(default=None, gt=0)
    expected_employee_code: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode='after')
    def validate_times(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        if self.location_at > now + datetime.timedelta(minutes=5) or self.selected_at > now + datetime.timedelta(minutes=5):
            raise ValueError('Check the date and time on the phone before uploading.')
        if abs((self.location_at - self.selected_at).total_seconds()) > 120:
            raise ValueError('Location must be recorded near the time the photo is selected.')
        return self


@pt_app.post('/mobile-upload', response_model=PhotoOut, status_code=201)
def mobile_upload(request: Request, file: UploadFile = File(...),
                  metadata: str = Form(..., max_length=3000), title: Optional[str] = Form(None, max_length=120), db: Session = Depends(get_db)):
    info = tracker_identity(request)
    try:
        meta = MobileMetadata.model_validate_json(metadata)
    except ValueError:
        raise HTTPException(422, 'Photo location or time is invalid. Enable precise location and automatic date/time, then select the photo again.')
    supplied_title = meta.title if meta.title is not None else title
    if supplied_title is not None and not supplied_title.strip():
        raise HTTPException(422, 'Please enter a photo title before sending.')
    if meta.title is not None and title is not None and meta.title.strip() != title.strip():
        raise HTTPException(422, 'Photo titles do not match. Please retry with the saved title.')
    photo_title = supplied_title.strip() if supplied_title is not None else 'Untitled Photo'
    expected = (meta.expected_tracker_id, meta.expected_employee_id, meta.expected_employee_code)
    if any(value is not None for value in expected) and expected != (info['tracker_id'], info['employee_id'], info['employee_code']):
        raise HTTPException(409, 'This photo was saved for a different employee account. Contact HR; the photo remains on this phone.')
    # Original selection/GPS timestamps may be days old after an offline period.
    # Validation compares them to each other, never to upload/receipt time.
    key = f"{info['tracker_id']}:{meta.upload_id}"
    previous = db.query(PhotoRecord).filter_by(upload_key=key).first()
    if previous:
        return serialize(previous)
    ext = Path(file.filename or '').suffix.lower()
    # Keep the mobile preview compatible with the browser; reject mislabeled data.
    signatures = file.file.read(16)
    file.file.seek(0)
    valid = ((ext in ('.jpg', '.jpeg') and signatures.startswith(b'\xff\xd8\xff')) or
             (ext == '.png' and signatures.startswith(b'\x89PNG\r\n\x1a\n')) or
             (ext == '.webp' and signatures[:4] == b'RIFF' and signatures[8:12] == b'WEBP'))
    if not valid:
        raise HTTPException(415, 'Choose a JPG, PNG, or WebP photo, or take a new picture in the app.')
    name = f'mobile_{uuid.uuid4().hex}{ext}'
    path = UPLOAD_DIR / name
    size = save_upload(file, str(path), MAX_UPLOAD_BYTES)
    now = datetime.datetime.now(datetime.timezone.utc)
    now_manila = now.astimezone(MANILA_TZ)
    local = meta.selected_at.astimezone(MANILA_TZ)
    exif_taken_manila = (
        _to_manila_aware(meta.exif_taken_at)
        if meta.exif_taken_at is not None
        else _extract_pillow_exif_taken_at(path)
    )
    effective_taken_manila = (
        exif_taken_manila
        if meta.source == 'gallery' and exif_taken_manila is not None
        else local
    )
    resolved_location = _resolve_location_name(db, meta.latitude, meta.longitude)
    size = _apply_photo_watermark(
        path, ext,
        employee_name=info['full_name'], photo_title=photo_title,
        verified_dt=effective_taken_manila, location_name=resolved_location,
        latitude=meta.latitude, longitude=meta.longitude, source=meta.source, has_exif=(exif_taken_manila is not None),
    )
    label = 'Camera photo selected' if meta.source == 'camera' else 'Gallery photo selected'
    details = {**meta.model_dump(mode='json'), **info,
               'exif_taken_at': exif_taken_manila.isoformat() if exif_taken_manila else None,
               'uploaded_at': now.isoformat(), 'context_radius_m': 250}
    exif_line = f"Original photo time (EXIF): {exif_taken_manila:%d %b %Y, %I:%M:%S %p} (Philippine time)\n" if exif_taken_manila else ''
    description = (f"Uploaded by: {info['full_name']}\n{label}: {local:%d %b %Y, %I:%M:%S %p} (Philippine time)\n"
                   f"{exif_line}"
                   f"Location when selected: {meta.latitude:.6f}, {meta.longitude:.6f}\n"
                   f"GPS accuracy: ±{meta.accuracy_m:.0f} m. Context radius: 250 m.\n"
                   f"Uploaded: {now_manila:%d %b %Y, %I:%M:%S %p} (Philippine time)")
    record = PhotoRecord(title=photo_title, location_name=resolved_location, owner_name=info['full_name'], filename=name, filepath=f'uploads/{name}',
                         original_filename=Path(file.filename).name, display_name=info['full_name'],
                         description=description, tags='Mobile upload', size_bytes=size,
                         content_type={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp'}[ext],
                         timestamp=effective_taken_manila.replace(tzinfo=None),
                         mobile_metadata=json.dumps(details, ensure_ascii=False), upload_key=key)
    try:
        db.add(record)
        db.flush()
        log_activity(db, info['full_name'], 'upload', record, details=details)
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        path.unlink(missing_ok=True)
        previous = db.query(PhotoRecord).filter_by(upload_key=key).first()
        if previous:
            return serialize(previous)
        raise
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return serialize(record)


class MobileTitleEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    upload_id: uuid.UUID
    revision: int = Field(gt=0, le=2147483647)
    title: str = Field(min_length=1, max_length=120)
    expected_tracker_id: int = Field(gt=0)
    expected_employee_id: int = Field(gt=0)
    expected_employee_code: str = Field(min_length=1, max_length=200)


@pt_app.patch('/mobile-photos/{photo_id}/title')
def edit_mobile_title(photo_id: int, payload: MobileTitleEdit, request: Request,
                      db: Session = Depends(get_db)):
    info = tracker_identity(request)
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, 'Please enter a photo title (up to 120 characters).')
    identity = (info['tracker_id'], info['employee_id'], info['employee_code'])
    if identity != (payload.expected_tracker_id, payload.expected_employee_id, payload.expected_employee_code):
        raise HTTPException(403, 'Sign in with the employee account that uploaded this photo.')
    # Serialize competing edits/retries. A late request cannot undo a newer title.
    db.execute(text('BEGIN IMMEDIATE'))
    photo = get_photo_or_404(db, photo_id)
    key = f"{info['tracker_id']}:{payload.upload_id}"
    try:
        meta = json.loads(photo.mobile_metadata or '{}')
    except (ValueError, TypeError):
        meta = {}
    if not isinstance(meta, dict) or photo.upload_key != key or identity != (
        meta.get('tracker_id'), meta.get('employee_id'), meta.get('employee_code')
    ):
        raise HTTPException(403, 'Only the employee who uploaded this photo can edit its title.')
    saved = db.get(PhotoTitleRevision, key)
    if saved and payload.revision <= saved.revision:
        if payload.revision == saved.revision and title != saved.title:
            raise HTTPException(409, 'This title edit conflicts with a previously saved edit.')
        return {'id': photo.id, 'upload_id': str(payload.upload_id), 'revision': saved.revision,
                'title': saved.title, **{k: info[k] for k in ('tracker_id','employee_id','employee_code')}}
    before = photo.title or 'Untitled Photo'
    if before != title:
        photo.title = title
        log_activity(db, info['full_name'], 'edit', photo=photo,
                     details={'changes': {'title': {'from': before, 'to': title}},
                              'upload_id': str(payload.upload_id), 'revision': payload.revision})
    # Keep original capture metadata, location, filenames and upload time unchanged.
    if saved:
        saved.revision, saved.title = payload.revision, title
    else:
        db.add(PhotoTitleRevision(upload_key=key, revision=payload.revision, title=title))
    db.commit()
    return {'id': photo.id, 'upload_id': str(payload.upload_id), 'revision': payload.revision,
            'title': title, **{k: info[k] for k in ('tracker_id','employee_id','employee_code')}}
