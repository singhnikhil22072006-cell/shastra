"""PDF digital-signature inspection.

Level 1 (always): ByteRange coverage. A signature protects only the bytes it covers; if the file has
extra bytes after the signed range, content was appended after signing.
Level 2 (when pyHanko is installed): cryptographic check that the signed digest still matches the
document ("intact") and that the signature itself is valid. Certificate TRUST (chain to a recognised
root such as the Indian CCA) is NOT established, because no trust roots are configured -- the result
says so explicitly.
"""
import io
import logging
import re

logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)

RANGE = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")


def inspect_signatures(data: bytes) -> dict:
    ranges = [tuple(int(x) for x in m.groups()) for m in RANGE.finditer(data)]
    out = {"count": len(ranges), "covers_whole_file": None, "crypto": "not_available",
           "signatures": [], "trust": "not_established"}
    if not ranges:
        return out
    signed_end = max(c + d for _, _, c, d in ranges)
    out["covers_whole_file"] = signed_end >= len(data.rstrip(b"\r\n \t\x00"))
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko_certvalidator import ValidationContext
    except ImportError:
        return out
    try:
        reader = PdfFileReader(io.BytesIO(data))
        vc = ValidationContext(trust_roots=[], allow_fetching=False)  # no network, no OS trust store: trust is deliberately unset
        for emb in reader.embedded_signatures:
            st = validate_pdf_signature(emb, signer_validation_context=vc)
            try:
                signer = emb.signer_cert.subject.human_friendly
            except Exception:
                signer = None
            out["signatures"].append({"field": emb.field_name, "signer": signer, "intact": bool(st.intact),
                                      "valid": bool(st.valid), "trusted": bool(st.trusted)})
        out["crypto"] = "performed"
        if any(s["trusted"] for s in out["signatures"]):
            out["trust"] = "chain_trusted"
    except Exception as e:  # malformed signature objects are themselves suspicious, but report neutrally
        out["crypto"] = "error"
        out["error"] = type(e).__name__
    return out
