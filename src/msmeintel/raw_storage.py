"""Immutable, content-addressed PDF bytes; no PDF parsing or execution."""

import hashlib
import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from uuid import uuid4

MAX_PDF_BYTES = 50 * 1024 * 1024
CHUNK_SIZE = 65536
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
STAGING_PATTERN = re.compile(r"raw/\.tmp/msmeintel-[0-9a-f]{32}\.part")


class ArtifactError(ValueError):
    """Safe, classified validation error; messages contain no transport secrets."""

    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def storage_path(digest: str) -> str:
    if not isinstance(digest, str) or not HASH_PATTERN.fullmatch(digest):
        raise ArtifactError("INVALID_PATH", "Invalid SHA-256 identity.")
    return f"raw/{digest[:2]}/{digest}.pdf"


def safe_path(data_dir: Path, relative: str) -> Path:
    """Only generated raw paths are accepted, including on Windows."""
    if not isinstance(relative, str) or not (
        STAGING_PATTERN.fullmatch(relative)
        or re.fullmatch(r"raw/([0-9a-f]{2})/\1[0-9a-f]{62}\.pdf", relative)
    ):
        raise ArtifactError("INVALID_PATH", "Unsafe raw storage path.")
    root = data_dir.absolute()
    path = root / relative
    for part in (root, *reversed(path.relative_to(root).parents)):
        candidate = part if part == root else root / part
        if candidate.is_symlink() or candidate.is_junction():
            raise ArtifactError("INVALID_PATH", "Linked raw storage directories are forbidden.")
    if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root.resolve()):
        raise ArtifactError("INVALID_PATH", "Raw storage path escapes the data directory.")
    return path


def new_staging_path() -> str:
    return f"raw/.tmp/msmeintel-{uuid4().hex}.part"


def discard_staging(data_dir: Path, relative: str | None) -> None:
    if relative is not None:
        if not STAGING_PATTERN.fullmatch(relative):
            raise ArtifactError("INVALID_PATH", "Not an owned staging file.")
        safe_path(data_dir, relative).unlink(missing_ok=True)


def _check_pdf(header: bytes, tail: bytes, size: int) -> None:
    if not size or not re.match(rb"%PDF-[12]\.\d[\r\n\t ]", header):
        raise ArtifactError("INVALID_PDF", "Missing PDF version signature.")
    if b"%%EOF" not in tail:
        raise ArtifactError("INVALID_PDF", "Missing PDF end marker in final 1 KiB.")


def write_pdf(
    data_dir: Path,
    relative: str,
    chunks: Iterable[bytes],
    *,
    length: int | None,
    check_time: Callable[[], None],
) -> tuple[str, int]:
    path = safe_path(data_dir, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest, size, header, tail = hashlib.sha256(), 0, b"", b""
    with path.open("xb") as output:
        for chunk in chunks:
            check_time()
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ArtifactError("SIZE_LIMIT", "PDF exceeds the 50 MiB limit.")
            header = (header + chunk)[:16]
            tail = (tail + chunk)[-1024:]
            output.write(chunk)
            digest.update(chunk)
        check_time()
        if length is not None and size != length:
            raise ArtifactError("LENGTH_MISMATCH", "Declared and received lengths differ.")
        _check_pdf(header, tail, size)
        output.flush()
        os.fsync(output.fileno())
    return digest.hexdigest(), size


def verify_file(data_dir: Path, relative: str, digest: str, byte_count: int) -> None:
    storage_path(digest)
    path = safe_path(data_dir, relative)
    checksum, size, header, tail = hashlib.sha256(), 0, b"", b""
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ArtifactError("CORRUPT_FILE", "Stored artifact exceeds the size limit.")
            header = (header + chunk)[:16]
            tail = (tail + chunk)[-1024:]
            checksum.update(chunk)
    if checksum.hexdigest() != digest or size != byte_count:
        raise ArtifactError("CORRUPT_FILE", "Stored artifact hash or byte count differs.")
    _check_pdf(header, tail, size)


def publish(data_dir: Path, staging: str, digest: str, byte_count: int) -> bool:
    """Hard-link publication is atomic and cannot clobber an existing hash path."""
    source = safe_path(data_dir, staging)
    destination = safe_path(data_dir, storage_path(digest))
    verify_file(data_dir, staging, digest, byte_count)
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        os.link(source, destination)
        created = True
    except FileExistsError:
        pass
    verify_file(data_dir, storage_path(digest), digest, byte_count)
    discard_staging(data_dir, staging)
    return created
