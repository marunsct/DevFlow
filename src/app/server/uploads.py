"""Server-side file upload handling with validation.

Step 6.1 of the workflow plan: the server, not the browser, must validate
file type, file size, ownership, and run permissions.  Documents are stored
outside executable paths so a malicious upload can never be imported or
eval'd.

Why server-side?  A browser can forge any Content-Type header or skip
client-side size checks entirely.  The only trustworthy gate is the one
that runs on the server, so every check here is authoritative and every
client-side check is cosmetic.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

CHUNK_SIZE_BYTES = 64 * 1024

# Derived from the reader's own dispatch table so the two cannot drift: the
# reader handled .pdf and .csv while this set rejected them, making working
# functionality unreachable.
ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".docx", ".pdf", ".csv"})
"""File extensions the workflow knows how to read.

Anything else is rejected before a single byte is stored.  This is not a
guess about what might work — it's the exact set ``app.documents`` supports.
"""

DEFAULT_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
"""Maximum upload size.  Matches ``app.documents.read_document``'s default."""


class UploadError(ValueError):
    """Raised when an upload fails server-side validation."""


class UnsupportedFileType(UploadError):
    """The uploaded file's extension is not in ``ALLOWED_EXTENSIONS``."""


class FileTooLarge(UploadError):
    """The uploaded file exceeds ``DEFAULT_MAX_FILE_SIZE_BYTES``."""


@dataclass(frozen=True)
class UploadResult:
    """Metadata about a successfully validated and stored upload.

    ``stored_path`` is the absolute path where the document now lives.
    It is inside the configured upload directory, which is outside any
    executable path.  The original filename is preserved in ``original_name``
    for display, but the stored file is renamed to avoid collisions and
    path-traversal tricks.
    """

    original_name: str
    stored_path: str
    file_size_bytes: int
    content_type: str


def _safe_stem(original_name: str) -> str:
    """Derive a safe filename stem from the user-supplied name.

    Strips directory components and restricts to alphanumeric plus hyphens
    and underscores, so a name like ``../../etc/passwd`` becomes ``etcpasswd``.
    """
    basename = Path(original_name).name
    stem = Path(basename).stem
    safe = "".join(c if c.isalnum() or c in "-_" else "" for c in stem)
    return safe[:80] or "upload"


def _content_type_for(extension: str) -> str:
    """Return a safe Content-Type for a known extension."""
    return {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(extension, "application/octet-stream")


def validate_and_store(
    file_obj: BinaryIO,
    original_filename: str,
    upload_dir: str | Path,
    *,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> UploadResult:
    """Validate an uploaded file and store it safely.

    Args:
        file_obj: the file-like object to read from (e.g. ``UploadFile.file``).
        original_filename: the filename the browser reported.  Used only for
            display and extension checking, never for storage paths.
        upload_dir: directory where validated uploads are stored.  Must exist.
        max_size_bytes: reject files larger than this.

    Returns:
        An ``UploadResult`` with the stored path and metadata.

    Raises:
        UnsupportedFileType: extension not in ``ALLOWED_EXTENSIONS``.
        FileTooLarge: file exceeds ``max_size_bytes``.
        UploadError: the upload directory does not exist or is not writable.
    """
    upload_path = Path(upload_dir)
    if not upload_path.is_dir():
        raise UploadError(f"Upload directory does not exist: {upload_dir}")

    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileType(
            f"File type '{extension}' is not supported. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Stream to disk in chunks, stopping the moment the running total exceeds
    # the cap. Reading the whole object first - as this used to - meant a
    # multi-gigabyte upload exhausted memory *before* the size check ran.
    safe_stem = _safe_stem(original_filename)
    unique_name = f"{safe_stem}_{uuid.uuid4().hex[:8]}{extension}"
    stored_path = upload_path / unique_name

    total = 0
    try:
        with stored_path.open("wb") as destination:
            while True:
                chunk = file_obj.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size_bytes:
                    raise FileTooLarge(
                        f"File exceeds the {max_size_bytes:,}-byte limit."
                    )
                destination.write(chunk)
    except BaseException:
        # Never leave a partial or oversized file behind.
        stored_path.unlink(missing_ok=True)
        raise

    if total == 0:
        stored_path.unlink(missing_ok=True)
        raise UploadError("The uploaded file is empty.")

    return UploadResult(
        original_name=original_filename,
        stored_path=str(stored_path),
        file_size_bytes=total,
        content_type=_content_type_for(extension),
    )


def ensure_upload_dir(base_dir: str | Path) -> Path:
    """Create the upload directory if it does not exist.

    Returns the absolute path.  The directory is created with mode 0o700
    so only the owner can read uploaded product documents.
    """
    path = Path(base_dir).resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


__all__ = [
    "ALLOWED_EXTENSIONS",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "FileTooLarge",
    "UploadError",
    "UploadResult",
    "UnsupportedFileType",
    "ensure_upload_dir",
    "validate_and_store",
]
