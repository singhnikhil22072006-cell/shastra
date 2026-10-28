"""Watermark detection.

Two independent detectors, both classical (no learned model):
  * PDF-native: diagonal / large / light / transparent text spans, /Watermark annotations, marked-content
    /Watermark artifacts, and optional-content layers named like a watermark.
  * Raster: a faint, large, low-contrast overlay on image uploads and scanned pages, then OCR on that
    isolated layer to read the watermark text.
A detected watermark is a *supporting signal*, never proof: anyone can add a watermark to a forgery.
Its value is when the issuer registered which watermark text its letters carry and it is missing here.
"""
import math
import re
from difflib import SequenceMatcher

import cv2
import numpy as np
import pymupdf as fitz
from PIL import Image

LAYER_RX = re.compile(r"water|confidential|draft|original|seal", re.I)


def _lum(c: int) -> float:
    return (0.2126 * ((c >> 16) & 255) + 0.7152 * ((c >> 8) & 255) + 0.0722 * (c & 255)) / 255


def pdf_watermarks(doc: fitz.Document) -> dict:
    texts: dict[str, set] = {}
    annots = marked = 0
    layers: list[str] = []
    try:
        layers = [v.get("name", "") for v in (doc.get_ocgs() or {}).values() if LAYER_RX.search(v.get("name", ""))]
    except Exception:
        pass
    for page in doc:
        try:
            annots += sum(1 for a in (page.annots() or []) if a.type[0] == fitz.PDF_ANNOT_WATERMARK)
        except Exception:
            pass
        try:
            if b"/Watermark" in page.read_contents():
                marked += 1
        except Exception:
            pass
        for b in page.get_text("dict").get("blocks", []):
            for ln in b.get("lines", []):
                dx, dy = ln.get("dir", (1, 0))
                ang = abs(math.degrees(math.atan2(dy, dx)))
                diagonal = 8 < ang < 82 or 98 < ang < 172
                for s in ln.get("spans", []):
                    t = " ".join(s["text"].split())
                    if len(t) < 3:
                        continue
                    light, big = _lum(s["color"]) > 0.62, s["size"] >= 40
                    transparent = s.get("alpha", 255) < 200
                    why = []
                    if diagonal and (light or big or transparent):
                        why.append("diagonal text")
                    if light and big:
                        why.append("large light text")
                    if transparent and (big or diagonal):
                        why.append("semi-transparent text")
                    if why:
                        texts.setdefault(t, set()).update(why)
    kinds = sorted({w for v in texts.values() for w in v} | ({"watermark annotation"} if annots else set())
                   | ({"marked-content watermark"} if marked else set()) | ({"watermark layer"} if layers else set()))
    return {"method": "pdf-structure", "detected": bool(kinds), "kinds": kinds,
            "texts": sorted(texts)[:10], "layers": layers[:5], "coverage": None}


def _faint_layer(img: Image.Image):
    g = np.asarray(img.convert("L"))
    h, w = g.shape
    if max(h, w) > 1100:
        k = 1100 / max(h, w)
        g = cv2.resize(g, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
        h, w = g.shape
    bg = float(np.median(g))
    blur = cv2.GaussianBlur(g, (0, 0), 2)
    ink = (g < bg - 90).astype(np.uint8)
    ink = cv2.dilate(ink, np.ones((7, 7), np.uint8))
    diff = bg - blur
    faint = ((diff >= 10) & (diff <= 70) & (ink == 0)).astype(np.uint8)
    blob = cv2.morphologyEx(faint, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))  # for area statistics only
    # OCR layer: a grayscale close erases thin dark text strokes but keeps thick watermark glyphs.
    nostroke = cv2.morphologyEx(g, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    d = np.clip(bg - cv2.GaussianBlur(nostroke, (0, 0), 1.2), 0, 90).astype(np.float32)
    ocr_layer = (255 - d * (255.0 / 60.0)).clip(0, 255).astype(np.uint8)
    return blob, ocr_layer, h, w


def raster_watermark(img: Image.Image, ocr=None) -> dict:
    faint, raw, h, w = _faint_layer(img)  # raw = OCR-ready layer
    coverage = float(faint.sum()) / (h * w)
    n, _, stats, _ = cv2.connectedComponentsWithStats(faint, connectivity=8)
    big = int((stats[1:, cv2.CC_STAT_AREA] > 0.0015 * h * w).sum()) if n > 1 else 0
    found = big >= 1 and 0.004 <= coverage <= 0.45
    texts: list[str] = []
    if found and ocr is not None:
        pil = Image.fromarray(raw)
        for ang in (0, 40, -40):
            try:
                res, _ = ocr(np.asarray(pil.rotate(ang, expand=True, fillcolor=255).convert("RGB")))
            except Exception:
                res = None
            for r in res or []:
                t = " ".join(str(r[1]).split())
                if len(t) >= 3 and float(r[2]) >= 0.6 and t not in texts:
                    texts.append(t)
    return {"method": "raster-overlay", "detected": found, "kinds": ["faint overlay"] if found else [],
            "texts": texts[:10], "layers": [], "coverage": round(coverage, 4)}


def merge(parts: list[dict], expected: str | None = None) -> dict:
    """Combine per-page / per-method results and test the issuer's expected watermark text, if any."""
    kinds = sorted({k for p in parts for k in p["kinds"]})
    texts = []
    for p in parts:
        for t in p["texts"]:
            if t not in texts:
                texts.append(t)
    detected = any(p["detected"] for p in parts)
    exp_found = None
    if expected:
        want = re.sub(r"\W+", "", expected).lower()
        def close(t: str) -> bool:  # tolerate OCR dropping/garbling a letter or two
            t = re.sub(r"\W+", "", t).lower()
            return bool(want) and SequenceMatcher(None, want, t).find_longest_match(0, len(want), 0, len(t)).size >= 0.8 * len(want)
        exp_found = any(close(t) for t in texts)
    return {"detected": detected, "kinds": kinds, "texts": texts[:10], "expected": expected,
            "expected_found": exp_found, "methods": sorted({p["method"] for p in parts})}
