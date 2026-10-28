"""Image-level checks. ELA is a classical forensic heuristic and QR decoding is classical OpenCV --
neither is a learned model, and the report labels them accordingly."""
import io

import cv2
import numpy as np
from PIL import Image


def ela(img: Image.Image, quality: int = 90, block: int = 32):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    again = Image.open(buf).convert("RGB")
    diff = np.abs(np.asarray(img, dtype=np.int16) - np.asarray(again, dtype=np.int16)).max(axis=2).astype(np.float32)
    h, w = diff.shape
    H, W = h // block, w // block
    if H < 3 or W < 3:
        return {"outlier_blocks": 0, "total_blocks": 0, "max_z": 0.0}, None
    blocks = diff[: H * block, : W * block].reshape(H, block, W, block).mean(axis=(1, 3))
    med = float(np.median(blocks))
    mad = float(np.median(np.abs(blocks - med))) * 1.4826 + 1e-3
    z = (blocks - med) / mad
    outliers = int(((z > 8) & (blocks > 4.0)).sum())
    heat = np.clip(diff * (255.0 / max(float(diff.max()), 1.0)), 0, 255).astype(np.uint8)
    heat = Image.fromarray(cv2.cvtColor(cv2.applyColorMap(heat, cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB))
    return {"outlier_blocks": outliers, "total_blocks": int(H * W), "max_z": round(float(z.max()), 1)}, heat


def decode_qr(img: Image.Image) -> str | None:
    try:
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(np.asarray(img)[:, :, ::-1].copy())
        return text[:300] or None
    except Exception:
        return None
