"""
Hardened handling for the two places this app accepts an uploaded image
(marking photo, hand-drawn diagram). Previously: no size limit, no
content-type validation, no magic-byte check, no extension allowlist, no
re-encode -- the client-supplied filename's extension was trusted verbatim,
so a ".html" or ".svg" upload was stored and, if ever served back, would be
served with a Content-Type derived from that extension. Also a quiet
privacy gap: a phone photo's EXIF data (GPS coordinates, device
identifiers) was stored and served indefinitely, unstripped.

The fix here is structural, not a filter: every upload is decoded as a real
image and RE-ENCODED to a fresh, normalised JPEG before anything touches
disk. Only genuine pixel data survives that round trip -- there is no
representation in which arbitrary HTML/SVG/JS content, or the original
file's EXIF block, comes out the other end. The stored filename's
extension is always server-determined (".jpg"), never taken from the
client.
"""
import os
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings

# H14: sourced from Settings (env-overridable). Re-exported under their old
# names for any existing caller/test that imports these directly.
MAX_UPLOAD_BYTES = settings.max_upload_bytes
JPEG_QUALITY = settings.upload_jpeg_quality


@dataclass
class SavedImage:
    path: str
    filename: str


def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Reads the upload in chunks, aborting as soon as the cap is exceeded
    -- rather than reading an arbitrarily large body fully into memory
    first and only then checking its size, which is itself a resource-
    exhaustion vector on a machine nobody is monitoring disk/memory on."""
    chunks = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = file.file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"Upload too large -- the limit is {max_bytes // (1024 * 1024)} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def save_uploaded_image(file: UploadFile, dest_dir: str, name_prefix: str) -> SavedImage:
    """Validates, re-encodes, and saves an uploaded image. Raises
    HTTPException(400/413) on anything that isn't a genuine, decodable
    image within the size cap. Returns the path actually written (always
    ending in .jpg) and the server-generated filename."""
    raw = _read_capped(file, MAX_UPLOAD_BYTES)
    if not raw:
        raise HTTPException(400, "Uploaded file is empty.")

    # Pillow's own two-step contract: .verify() checks structural validity
    # but leaves the image object unusable for anything else afterwards, so
    # actually processing the pixel data requires re-opening from the same
    # bytes. This also means broken/truncated/non-image content (an HTML
    # file renamed to .jpg, a corrupted upload) is rejected here rather
    # than silently stored.
    import io
    try:
        Image.open(io.BytesIO(raw)).verify()
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise HTTPException(400, "Uploaded file is not a valid image (JPEG/PNG/etc).") from e

    # Re-encoding to a fresh RGB JPEG is what actually strips EXIF (GPS,
    # device identifiers) and any non-pixel payload -- .save() below is
    # never passed the source's `exif`/`icc_profile`/`info`, so none of it
    # survives into the output file, regardless of what the input carried.
    if img.mode not in ("RGB", "L"):
        # Pillow's own type stubs return the base Image.Image type from
        # .convert(), narrower than the ImageFile.ImageFile subtype .open()
        # produced -- both are genuinely valid, save()-able images at
        # runtime; this is a stub-typing gap, not a real type mismatch.
        img = img.convert("RGB")  # type: ignore[assignment]

    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{name_prefix}_{uuid.uuid4().hex[:8]}.jpg"
    dest_path = os.path.join(dest_dir, filename)
    img.save(dest_path, format="JPEG", quality=JPEG_QUALITY)
    return SavedImage(path=dest_path, filename=filename)
