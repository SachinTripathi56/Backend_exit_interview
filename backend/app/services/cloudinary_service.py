"""
Cloudinary file storage abstraction.

Employee/HR data is sensitive, so nothing uploaded through this service is
ever a public/unsigned resource — everything uses `type="authenticated"`
and access happens only through short-lived signed URLs generated here on
the backend. The Cloudinary API secret never leaves this process.

If Cloudinary isn't configured (e.g. local development without real
credentials), every method degrades gracefully to a no-op / None instead of
raising, so the rest of the import flow (which only *optionally* archives
the original file) keeps working without it.
"""
from __future__ import annotations

import io
import logging
from typing import BinaryIO

from app.core.config import settings

logger = logging.getLogger(__name__)

_configured = False


def _ensure_configured() -> bool:
    """Lazily configure the Cloudinary SDK. Returns False if not set up."""
    global _configured
    if not settings.CLOUDINARY_CLOUD_NAME or not settings.CLOUDINARY_API_KEY or not settings.CLOUDINARY_API_SECRET:
        return False
    if not _configured:
        import cloudinary

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        _configured = True
    return True


def upload_file(
    file_bytes: bytes,
    *,
    folder: str,
    public_id: str | None = None,
    resource_type: str = "raw",
) -> str | None:
    """
    Upload a file as a PRIVATE, authenticated Cloudinary resource.

    Returns the Cloudinary public_id on success, or None if Cloudinary is
    not configured (caller should treat this as "archival skipped", not as
    an error — the import/report itself must not fail because of it).
    """
    if not _ensure_configured():
        logger.warning("Cloudinary is not configured; skipping file archival for %s", folder)
        return None

    import cloudinary.uploader

    stream: BinaryIO = io.BytesIO(file_bytes)
    result = cloudinary.uploader.upload(
        stream,
        folder=folder,
        public_id=public_id,
        resource_type=resource_type,
        type="authenticated",  # never publicly accessible without a signed URL
        overwrite=False,
        unique_filename=True,
    )
    return result.get("public_id")


def delete_file(public_id: str, *, resource_type: str = "raw") -> None:
    if not _ensure_configured():
        logger.warning("Cloudinary is not configured; skipping delete for %s", public_id)
        return

    import cloudinary.uploader

    cloudinary.uploader.destroy(public_id, resource_type=resource_type, type="authenticated")


def generate_secure_url(
    public_id: str, *, resource_type: str = "raw", expires_in_seconds: int = 300
) -> str | None:
    """
    Generate a short-lived signed URL for a private/authenticated resource.
    Returns None if Cloudinary is not configured.
    """
    if not _ensure_configured():
        return None

    import time

    import cloudinary.utils

    expires_at = int(time.time()) + expires_in_seconds
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type=resource_type,
        type="authenticated",
        sign_url=True,
        secure=True,
        auth_token={"duration": expires_in_seconds},
    )
    return url
