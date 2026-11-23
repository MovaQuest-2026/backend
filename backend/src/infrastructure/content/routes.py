"""Upload and stream lesson videos stored in PostgreSQL."""

from hashlib import sha256
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ...infrastructure.auth.deps import CurrentSuperUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import HTTPException
from ...modules.content.models import MediaVideo
from ...wiring.settings import settings
from .schemas import MediaFileResponse

router = APIRouter(tags=["Content"])

VideoName = Annotated[
    str,
    Query(
        min_length=5,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{4,127}$",
        description="Stable video object name, including extension",
    ),
]

_ALLOWED_EXTENSIONS = frozenset({".mp4", ".m4v", ".mov", ".webm"})
_CHUNK_SIZE = 1024 * 1024


def _content_type(name: str, submitted: str | None = None) -> str:
    if submitted and submitted.startswith("video/"):
        return submitted
    extension = Path(name).suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
    }.get(extension, "application/octet-stream")


def _validate_name(name: str) -> None:
    if Path(name).suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported video format.")


def _response(video: MediaVideo) -> MediaFileResponse:
    return MediaFileResponse(
        name=video.name,
        size_bytes=video.size_bytes,
        content_type=video.content_type,
        checksum_sha256=video.checksum_sha256,
    )


@router.get("/videos", response_model=list[MediaFileResponse], summary="List stored videos")
async def list_videos(_: CurrentSuperUserDep, db: AsyncSessionDep) -> list[MediaFileResponse]:
    """List video metadata; the binary payload is never included in this response."""
    videos = (await db.execute(select(MediaVideo).order_by(MediaVideo.created_at, MediaVideo.id))).scalars().all()
    return [_response(video) for video in videos]


@router.post("/videos", response_model=MediaFileResponse, status_code=status.HTTP_201_CREATED, summary="Upload a video")
async def upload_video(
    _: CurrentSuperUserDep,
    db: AsyncSessionDep,
    video: Annotated[UploadFile, File(description="MP4, M4V, MOV or WebM lesson video")],
    name: VideoName,
    replace: Annotated[bool, Query(description="Replace an existing object with the same name")] = False,
) -> MediaFileResponse:
    """Read a bounded upload and commit it as one PostgreSQL BYTEA value."""
    _validate_name(name)
    submitted_content_type = video.content_type
    if submitted_content_type and not submitted_content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Upload must be a video file.")

    payload = bytearray()
    try:
        while chunk := await video.read(_CHUNK_SIZE):
            payload.extend(chunk)
            if len(payload) > settings.MEDIA_MAX_FILE_BYTES:
                raise HTTPException(status_code=413, detail="Video file is too large.")
    finally:
        await video.close()

    content = bytes(payload)
    content_type = _content_type(name, submitted_content_type)
    existing = await db.scalar(select(MediaVideo).where(MediaVideo.name == name))
    if existing is not None:
        if not replace:
            raise HTTPException(status_code=409, detail="A video with this name already exists.")
        existing.content_type = content_type
        existing.size_bytes = len(content)
        existing.checksum_sha256 = sha256(content).hexdigest()
        existing.content = content
        await db.commit()
        await db.refresh(existing)
        return _response(existing)

    stored = MediaVideo(
        name=name,
        content_type=content_type,
        size_bytes=len(content),
        checksum_sha256=sha256(content).hexdigest(),
        content=content,
    )
    db.add(stored)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A video with this name already exists.") from error
    await db.refresh(stored)
    return _response(stored)


@router.get("/videos/{name}", response_model=None, summary="Stream a video")
async def stream_video(name: str, request: Request, db: AsyncSessionDep) -> Response:
    """Serve a DB-backed video and honor a single HTTP byte range for media players."""
    _validate_name(name)
    video = await db.scalar(select(MediaVideo).where(MediaVideo.name == name))
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    start, end = _requested_range(request.headers.get("range"), video.size_bytes)
    body = video.content[start : end + 1]
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(body)),
        "Content-Disposition": f'inline; filename="{video.name}"',
        "ETag": f'"{video.checksum_sha256}"',
    }
    if start != 0 or end != video.size_bytes - 1:
        headers["Content-Range"] = f"bytes {start}-{end}/{video.size_bytes}"
        return Response(
            content=body,
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=video.content_type,
            headers=headers,
        )
    return Response(content=body, media_type=video.content_type, headers=headers)


@router.delete("/videos/{name}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a video")
async def delete_video(name: str, _: CurrentSuperUserDep, db: AsyncSessionDep) -> None:
    _validate_name(name)
    result = await db.execute(delete(MediaVideo).where(MediaVideo.name == name))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Video not found.")
    await db.commit()


def _requested_range(value: str | None, size: int) -> tuple[int, int]:
    """Parse one ``bytes=start-end`` range; malformed or multi-range requests are refused."""
    if size <= 0:
        raise HTTPException(status_code=416, detail="Video has no content.", headers={"Content-Range": "bytes */0"})
    if not value:
        return 0, size - 1
    if not value.startswith("bytes=") or "," in value:
        raise HTTPException(status_code=416, detail="Invalid byte range.", headers={"Content-Range": f"bytes */{size}"})
    raw_start, raw_end = value.removeprefix("bytes=").split("-", 1)
    try:
        if raw_start == "":
            suffix = int(raw_end)
            if suffix <= 0:
                raise ValueError
            return max(0, size - suffix), size - 1
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
    except ValueError as error:
        raise HTTPException(
            status_code=416,
            detail="Invalid byte range.",
            headers={"Content-Range": f"bytes */{size}"},
        ) from error
    if start < 0 or start >= size or end < start:
        raise HTTPException(status_code=416, detail="Invalid byte range.", headers={"Content-Range": f"bytes */{size}"})
    return start, min(end, size - 1)
