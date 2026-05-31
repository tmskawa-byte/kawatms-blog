"""
Image helpers for the auto-article pipeline.

- `fetch_image_bytes`: accept either a data URL (data:image/png;base64,...)
  or an http(s) URL → return (bytes, mime_type).
  Nano Banana Pro normally returns a data URL; the http branch is a safety
  net in case the API ever changes.

- `extension_for_mime`: pick a sensible file extension for a mime string.

Mirror of ig-autopost/lib/image_gen.py to keep behaviour identical across
the IG bot and the blog pipeline. Kept inline (no shared package) because
the two repos do not share a dependency.
"""
from __future__ import annotations

import base64
import logging
from typing import Tuple

import requests

LOG = logging.getLogger(__name__)


class ImageFetchError(RuntimeError):
    """Raised when the image URL cannot be turned into bytes."""


_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg":  ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
    "image/gif":  ".gif",
}


def extension_for_mime(mime: str) -> str:
    """Return a sensible file extension for the given mime type."""
    return _MIME_EXT.get((mime or "").lower(), ".jpg")


def fetch_image_bytes(url: str, timeout: int = 60) -> Tuple[bytes, str]:
    """
    Returns (raw_bytes, mime_type).
    Raises ImageFetchError on any failure.
    """
    if not url:
        raise ImageFetchError("Empty image URL")

    if url.startswith("data:"):
        try:
            header, payload = url.split(",", 1)
        except ValueError as e:
            raise ImageFetchError(f"Malformed data URL: {e}") from e
        mime = "image/jpeg"
        if header.startswith("data:") and ";" in header:
            mime = header[len("data:"):].split(";")[0] or "image/jpeg"
        try:
            data = base64.b64decode(payload, validate=False)
        except Exception as e:  # base64 errors vary
            raise ImageFetchError(f"Base64 decode failed: {e}") from e
        return data, mime

    if url.startswith("http://") or url.startswith("https://"):
        try:
            resp = requests.get(url, timeout=timeout)
        except requests.RequestException as e:
            raise ImageFetchError(f"HTTP error fetching image: {e}") from e
        if resp.status_code >= 400:
            raise ImageFetchError(
                f"HTTP {resp.status_code} fetching image: {resp.text[:200]}"
            )
        mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        return resp.content, (mime or "image/jpeg")

    raise ImageFetchError(f"Unsupported URL scheme: {url[:40]}")
