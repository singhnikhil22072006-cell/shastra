"""Open uploads and extract text: native PDF text layer first, pretrained OCR only when needed."""
import pymupdf as fitz
import numpy as np
from PIL import Image

_engine = None


def _ocr():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR  # pretrained PP-OCR detection+recognition (ONNX)
        _engine = RapidOCR()
    return _engine


def open_document(data: bytes, ext: str, max_pages: int) -> fitz.Document:
    try:
        doc = fitz.open(stream=data, filetype=ext)
    except Exception:
        raise ValueError("File could not be parsed")
    if doc.needs_pass:
        raise ValueError("Encrypted or password-protected files are not supported")
    if doc.page_count == 0 or doc.page_count > max_pages:
        raise ValueError(f"Document must have between 1 and {max_pages} pages")
    return doc


def render_page(page: fitz.Page, dpi: int = 150, max_side: int = 3000) -> Image.Image:
    r = page.rect
    zoom = min(dpi / 72, max_side / max(r.width, r.height, 1))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def extract_pages(doc: fitz.Document) -> list[dict]:
    out = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if len(text) >= 40:
            out.append({"page": i + 1, "text": text, "method": "text-layer", "ocr_confidence": None})
            continue
        result, _ = _ocr()(np.array(render_page(page, 200)))
        lines = result or []
        out.append({
            "page": i + 1,
            "text": "\n".join(l[1] for l in lines),
            "method": "ocr",
            "ocr_confidence": round(float(np.mean([float(l[2]) for l in lines])), 3) if lines else 0.0,
        })
    return out
