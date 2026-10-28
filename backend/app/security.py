"""Upload hardening: size cap, magic-byte sniffing, pixel cap. Client-declared type is never trusted."""
import io
import os
import re

from fastapi import HTTPException, UploadFile
from PIL import Image

MAGIC = {
    b"%PDF-": ("pdf", "application/pdf"),
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
}
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # decompression-bomb guard


async def read_upload(file: UploadFile, max_bytes: int) -> tuple[bytes, str, str]:
    chunks, size = [], 0
    while chunk := await file.read(1 << 20):
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(413, f"File exceeds {max_bytes // (1 << 20)} MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(400, "Empty file")
    kind = next((v for m, v in MAGIC.items() if data.startswith(m)), None)
    if not kind:
        raise HTTPException(415, "Only PDF, PNG and JPEG files are accepted")
    ext, mime = kind
    if ext != "pdf":
        try:
            w, h = Image.open(io.BytesIO(data)).size
        except Exception:
            raise HTTPException(415, "Corrupt or unsupported image")
        if w * h > MAX_PIXELS:
            raise HTTPException(413, "Image resolution too large")
    return data, ext, mime


def safe_filename(name: str | None) -> str:
    name = os.path.basename((name or "upload").replace("\\", "/"))
    name = re.sub(r"[^\w.\- ()]", "_", name)[:120]
    return name or "upload"
