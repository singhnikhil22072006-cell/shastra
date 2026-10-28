"""Combine every signal into a transparent verification verdict.

VERIFIED    issuer's registry matches field-by-field AND at least one authenticity feature corroborates
            (file hash, intact signature, expected watermark, official QR) AND nothing high-severity.
PARTIAL     registry data matches but nothing corroborates (a forger could copy public data).
UNVERIFIED  no issuer record and no strong red flags.
SUSPICIOUS  high-severity indicators, or several medium ones, without a registry record.
MISMATCH    registry record exists but the document conflicts with it, or the approval is revoked.
Trust score is shown for transparency; the verdict rules above decide the label.
"""
import re
from urllib.parse import urlparse

from .config import settings
from .registry import norm_ref

W = {"registry": (35, -35), "hash": (10, -25), "signature": (15, -30), "watermark": (10, -10), "qr": (8, -15),
     "metadata": (4, -10), "forensics": (2, -5), "crossdoc": (3, -15), "consistency": (5, -20)}


def _f(fid, sev, cat, title, detail, evidence=None):
    return {"id": fid, "severity": sev, "category": cat, "title": title, "detail": detail, "evidence": evidence}


def _sig(i, label, state, detail):
    return {"id": i, "label": label, "state": state, "detail": detail}


def qr_host_ok(url: str) -> bool | None:
    u = url.strip()
    if not re.match(r"^https?://", u, re.I):
        return None
    host = (urlparse(u).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in settings.domain_list)


def authenticity_findings(parsed, visual, sigs, wm, match, ref_no) -> list[dict]:
    out = []
    if sigs and sigs["count"]:
        if sigs["covers_whole_file"] is False:
            out.append(_f("sig_appended", "high", "structure", "Content added after the digital signature",
                          "Bytes exist after the signed range, so the signature does not protect the whole file."))
        for s in sigs["signatures"]:
            if not s["intact"] or not s["valid"]:
                out.append(_f("sig_broken", "high", "structure", "Digital signature does not validate",
                              f"Signature '{s['field']}' (signer: {s['signer'] or 'unknown'}) no longer matches the document content."))
        if sigs["crypto"] == "performed" and sigs["signatures"] and all(s["intact"] and s["valid"] for s in sigs["signatures"]) and sigs["trust"] != "chain_trusted":
            out.append(_f("sig_untrusted", "info", "structure", "Signature intact but signer not trusted",
                          "No trust roots are configured, so the signer's certificate chain was not validated. Anyone can self-sign."))
    rec = match["record"] or {}
    if rec.get("expected_watermark") and wm["expected_found"] is False:
        out.append(_f("wm_missing", "medium", "watermark", "Issuer's expected watermark not found",
                      f"The issuer registered the watermark text '{rec['expected_watermark']}'. It was not detected "
                      "(detection can fail on poor scans)."))
    for q in visual["qr"]:
        ok = qr_host_ok(q["data"])
        if ok is False:
            out.append(_f("qr_offsite", "medium", "image", f"QR code points outside configured official domains (page {q['page']})",
                          "The QR was decoded, not opened.", q["data"]))
        if ref_no:
            m = re.search(r"[A-Za-z ]+/\d-\d+/\d{4}/[A-Za-z]+", q["data"])
            if m and norm_ref(m.group(0)) != norm_ref(ref_no):
                out.append(_f("qr_ref_mismatch", "medium", "image", "QR reference differs from printed reference number",
                              f"QR carries '{m.group(0)}', letter prints '{ref_no}'.", q["data"]))
    return out


def build_signals(parsed, visual, sigs, wm, match, findings, pdfinfo, exif_tool) -> list[dict]:
    ids = {f["id"] for f in findings}
    sev = lambda cats: {f["severity"] for f in findings if f["category"] in cats}  # noqa: E731
    S = []
    # registry
    if not match["matched"]:
        S.append(_sig("registry", "Issuer registry", "na", "No issuing-organization record matches this reference number or file."))
    elif match["diffs"] or match["revoked"]:
        S.append(_sig("registry", "Issuer registry", "fail", f"Record found ({match['record']['reference_no']}) but {len(match['diffs'])} field(s) differ" + ("; approval revoked" if match["revoked"] else "") + "."))
    else:
        S.append(_sig("registry", "Issuer registry", "pass", f"All compared fields match the issuer's record ({match['record']['reference_no']})."))
    # hash
    h = match.get("hash_ok")
    S.append(_sig("hash", "File fingerprint (SHA-256)", "pass" if h else "fail" if h is False else "na",
                  "Identical to the file the issuer registered." if h else "Differs from the file the issuer registered." if h is False else "Issuer did not register a file fingerprint."))
    # signature
    if not sigs or not sigs["count"]:
        S.append(_sig("signature", "Digital signature", "na", "No digital signature in this file."))
    elif "sig_broken" in ids or "sig_appended" in ids:
        S.append(_sig("signature", "Digital signature", "fail", "Signature invalid or does not cover the whole file."))
    elif sigs["crypto"] == "performed":
        trusted = sigs["trust"] == "chain_trusted"
        S.append(_sig("signature", "Digital signature", "pass" if trusted else "warn",
                      "Intact and chain-trusted." if trusted else "Cryptographically intact, but signer trust is not established (no trust roots configured)."))
    else:
        S.append(_sig("signature", "Digital signature", "warn", "Signature present; cryptographic check unavailable (install pyHanko)."))
    # watermark
    if wm["expected_found"] is True:
        S.append(_sig("watermark", "Watermark", "pass", f"Issuer's expected watermark detected: {', '.join(wm['texts'][:2])}."))
    elif wm["expected_found"] is False:
        S.append(_sig("watermark", "Watermark", "fail", "Issuer's expected watermark not detected."))
    elif wm["detected"]:
        S.append(_sig("watermark", "Watermark", "warn", "Watermark-like layer detected (" + ", ".join(wm["kinds"]) + ")" + (f": {', '.join(wm['texts'][:2])}" if wm["texts"] else "") + ". Issuer has not registered an expected watermark, so it can't be confirmed."))
    else:
        S.append(_sig("watermark", "Watermark", "na", "No watermark detected."))
    # qr
    if not visual["qr"]:
        S.append(_sig("qr", "QR code", "na", "No QR code found."))
    elif {"qr_offsite", "qr_ref_mismatch"} & ids:
        S.append(_sig("qr", "QR code", "fail", "QR points off official domains or disagrees with the printed reference."))
    elif any(qr_host_ok(q["data"]) for q in visual["qr"]):
        S.append(_sig("qr", "QR code", "pass", "QR URL is on a configured official domain (not opened or fetched)."))
    else:
        S.append(_sig("qr", "QR code", "warn", "QR decoded but is not a URL we can check."))
    # metadata
    if "edit_tool" in ids or exif_tool:
        S.append(_sig("metadata", "File metadata", "fail", "Produced or last saved by an image/PDF editing tool."))
    elif ids & {"mod_after_create", "incremental"}:
        S.append(_sig("metadata", "File metadata", "warn", "Modified after creation or saved with appended revisions."))
    elif pdfinfo is not None:
        S.append(_sig("metadata", "File metadata", "pass", "No editing-tool traces or late modification."))
    else:
        S.append(_sig("metadata", "File metadata", "na", "Image file: no document metadata to assess."))
    # forensics
    if visual["ela"]:
        S.append(_sig("forensics", "Image forensics (ELA)", "warn" if "ela" in ids else "pass",
                      "Localised compression inconsistency." if "ela" in ids else "No localised compression anomaly on scanned pages."))
    else:
        S.append(_sig("forensics", "Image forensics (ELA)", "na", "Only applies to scans/images."))
    # cross-document
    cx = sev({"integrity"}) & {"medium", "high"}
    S.append(_sig("crossdoc", "Cross-document consistency", "fail" if cx else "pass",
                  "Conflicts with other stored documents." if cx else "No conflicts with other stored documents."))
    # internal consistency
    c = sev({"content", "regulatory", "mismatch"})
    S.append(_sig("consistency", "Internal consistency & regulation", "fail" if "high" in c else "warn" if "medium" in c else "pass",
                  "High-severity inconsistency or regulatory issue." if "high" in c else "Moderate inconsistencies." if "medium" in c else "Fields are consistent and no regulatory flags."))
    return S


def verdict(signals: list[dict], findings: list[dict], match: dict) -> dict:
    trust = 30
    for s in signals:
        pos, neg = W[s["id"]]
        if s["state"] == "pass":
            trust += pos
        elif s["state"] == "fail":
            trust += neg
        elif s["state"] == "warn":
            trust += 3 if s["id"] in ("signature", "watermark") else neg // 3
    trust = max(0, min(100, trust))
    st = {s["id"]: s["state"] for s in signals}
    high = sum(f["severity"] == "high" for f in findings)
    med = sum(f["severity"] == "medium" for f in findings)
    corroborated = st["hash"] == "pass" or st["watermark"] == "pass" or st["qr"] == "pass" or st["signature"] == "pass"
    if match["matched"] and (match["revoked"] or any(d["severity"] == "high" for d in match["diffs"])):
        v, why = "MISMATCH", "The document conflicts with the issuing organization's record."
    elif match["matched"] and high:
        v, why = "SUSPICIOUS", "Registry record found, but high-severity indicators were raised."
    elif match["matched"] and corroborated and not match["diffs"] and trust >= 70:
        v, why = "VERIFIED", "Matches the issuer's record and is corroborated by independent authenticity features."
    elif match["matched"]:
        v, why = "PARTIAL", "Matches the issuer's record, but nothing independent (hash, signature, watermark, QR) corroborates it."
    elif high or med >= 2:
        v, why = "SUSPICIOUS", "No issuer record, and multiple notable indicators were raised."
    else:
        v, why = "UNVERIFIED", "No issuing-organization record exists for this document, so authenticity cannot be confirmed."
    return {"status": v, "trust_score": trust, "summary": why, "signals": signals}
