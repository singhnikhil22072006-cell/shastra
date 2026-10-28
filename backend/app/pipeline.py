import hashlib
import io
from datetime import date, datetime, timezone

import pymupdf as fitz
from PIL import Image

from . import watermark as wmk
from .anomaly import EDIT_TOOLS, run_checks, score
from .authenticity import authenticity_findings, build_signals, verdict
from .config import settings
from .crossdoc import cross_checks
from .extract import _ocr, extract_pages, open_document, render_page
from .parser import parse_fields
from .registry import match_registry, regulatory_findings
from .signature import inspect_signatures
from .structure import inspect_pdf
from .visual import decode_qr, ela


def _exif_tool(data: bytes, ext: str) -> str | None:
    if ext == "pdf":
        return None
    try:
        sw = str(Image.open(io.BytesIO(data)).getexif().get(305) or "").lower()  # EXIF Software tag
    except Exception:
        return None
    return sw if any(t in sw for t in EDIT_TOOLS) else None


def analyze(data: bytes, ext: str, mime: str, filename: str, user_id: str, stored: list[dict], registry: list[dict]) -> dict:
    sha = hashlib.sha256(data).hexdigest()
    doc = open_document(data, ext, settings.max_pages)
    try:
        pages = extract_pages(doc)
        parsed = parse_fields(pages)
        pdfinfo = inspect_pdf(data, doc) if ext == "pdf" else None
        sigs = inspect_signatures(data) if ext == "pdf" else None
        visual = {"qr": [], "ela": [], "ela_note": "ELA runs only on scanned/image pages; native-text PDFs render losslessly so ELA is not meaningful."}
        wm_parts = [wmk.pdf_watermarks(doc)] if ext == "pdf" else []
        match = match_registry(parsed, sha, registry)
        for i, page in enumerate(doc):
            img = render_page(page, 150)
            qr = decode_qr(img)
            if qr:
                visual["qr"].append({"page": i + 1, "data": qr})
            if pages[i]["method"] == "ocr":
                stats, _ = ela(img)
                visual["ela"].append({"page": i + 1, **stats})
            if pages[i]["method"] == "ocr" or ext != "pdf":
                wm_parts.append(wmk.raster_watermark(img, _ocr()))
        expected = (match["record"] or {}).get("expected_watermark")
        wm = wmk.merge(wm_parts, expected)
        ref_val = parsed["fields"]["reference_no"]["value"] if parsed["fields"]["reference_no"] else None

        findings = run_checks(pages, parsed, pdfinfo, visual)
        findings += regulatory_findings(parsed, match, date.today())
        findings += cross_checks(parsed, sha, user_id, stored)
        findings += authenticity_findings(parsed, visual, sigs, wm, match, ref_val)
        exif = _exif_tool(data, ext)
        if exif:
            findings.append({"id": "exif_tool", "severity": "medium", "category": "structure", "title": "Image saved by an editing tool",
                             "detail": f"EXIF Software tag: '{exif}'.", "evidence": exif})
        signals = build_signals(parsed, visual, sigs, wm, match, findings, pdfinfo, exif)
        ver = verdict(signals, findings, match)
        page_count = doc.page_count
    finally:
        doc.close()
    f = parsed["fields"]
    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "file": {"name": filename, "sha256": sha, "size": len(data), "type": mime, "pages": page_count},
        "engine": {"text": "PyMuPDF text layer", "ocr": "RapidOCR (pretrained PP-OCR, ONNX) - used only on pages without a text layer",
                   "parsing": "regex rules", "forensics": "ELA + PDF structure + watermark + signature checks (classical, not learned)",
                   "verification": "issuer registry match + corroborating authenticity signals"},
        "extraction": [{"page": p["page"], "method": p["method"], "ocr_confidence": p["ocr_confidence"], "chars": len(p["text"])} for p in pages],
        "text_excerpt": [{"page": p["page"], "text": p["text"][:6000]} for p in pages],
        "fields": f, "courses": parsed["courses"], "reference_parts": parsed["reference_parts"],
        "pdf_structure": pdfinfo, "signatures": sigs, "watermark": wm, "visual": visual, "registry_match": match,
        "findings": findings, "risk": score(findings), "verification": ver,
        "official_verification": {
            "status": "ISSUER_REGISTRY_" + ("MATCH" if match["matched"] else "NO_RECORD"), "supported": True,
            "reason": "Checked against records uploaded by issuing organizations on this platform. This is NOT a live query of AICTE's own database."},
    }


def report_assets(data: bytes, ext: str):
    """First-page thumbnail and (for scanned pages only) an ELA heatmap for the PDF report."""
    doc = open_document(data, ext, settings.max_pages)
    try:
        page = doc[0]
        thumb = render_page(page, 100, 1400)
        heat = None
        if ext != "pdf" or len(page.get_text("text").strip()) < 40:
            _, heat = ela(render_page(page, 150))
        return thumb, heat
    finally:
        doc.close()
