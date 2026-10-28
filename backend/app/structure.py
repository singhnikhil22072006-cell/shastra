"""PDF structural inspection: metadata, incremental updates, active content, signatures, fonts."""
import re

import pymupdf as fitz

ACTIVE = re.compile(r"/(JavaScript|JS|Launch|EmbeddedFile|OpenAction)\b")


def _pdf_date(s: str | None):
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", s or "")
    if not m:
        return None
    from datetime import datetime
    try:
        return datetime(*[int(x or 0) for x in m.groups()[:3]], *[int(x or 0) for x in m.groups()[3:]])
    except ValueError:
        return None


def inspect_pdf(data: bytes, doc: fitz.Document) -> dict:
    meta = doc.metadata or {}
    active, has_sig = set(), False
    for xref in range(1, min(doc.xref_length(), 5000)):
        try:
            obj = doc.xref_object(xref)
        except Exception:
            continue
        active.update(m.group(1) for m in ACTIVE.finditer(obj))
        has_sig = has_sig or "/ByteRange" in obj
    fonts = set()
    for page in doc:
        for f in page.get_fonts():
            fonts.add(re.sub(r"^[A-Z]{6}\+", "", f[3] or "unnamed"))
    created, modified = _pdf_date(meta.get("creationDate")), _pdf_date(meta.get("modDate"))
    return {
        "producer": meta.get("producer") or None,
        "creator": meta.get("creator") or None,
        "creation_date": created.isoformat() if created else None,
        "mod_date": modified.isoformat() if modified else None,
        "eof_markers": data.count(b"%%EOF"),
        "active_content": sorted(active),
        "has_signature_object": has_sig,
        "font_count": len(fonts),
        "fonts": sorted(fonts)[:20],
    }
