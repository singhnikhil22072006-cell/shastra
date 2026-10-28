"""Rule-based anomaly checks. Each finding cites its evidence; nothing here claims authenticity."""
from datetime import date

from .parser import parse_date

WEIGHT = {"high": 30, "medium": 15, "low": 5, "info": 0}  # review-priority score; verdict logic lives in authenticity.py
EDIT_TOOLS = ("photoshop", "gimp", "canva", "illustrator", "ilovepdf", "smallpdf", "sejda", "pdfescape", "inkscape", "paint")
REQUIRED = ("letter_type", "reference_no", "institute_name", "academic_year", "issue_date")


def _f(fid, sev, cat, title, detail, evidence=None):
    return {"id": fid, "severity": sev, "category": cat, "title": title, "detail": detail, "evidence": evidence}


def _val(parsed, key):
    x = parsed["fields"].get(key)
    return x["value"] if x else None


def run_checks(pages, parsed, pdfinfo, visual, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out: list[dict] = []
    fields = parsed["fields"]

    # --- content ---
    if parsed["total_chars"] < 50:
        out.append(_f("no_text", "medium", "content", "Little or no readable text",
                      "Fewer than 50 characters were extracted; all content checks below are unreliable."))
    elif not parsed["mentions_aicte"]:
        out.append(_f("no_aicte", "medium", "content", "No AICTE identification in text",
                      "Neither 'AICTE' nor 'All India Council for Technical Education' was found."))
    missing = [k for k in REQUIRED if not fields.get(k)]
    if missing:
        sev = "medium" if {"reference_no", "institute_name"} & set(missing) else "low"
        out.append(_f("missing_fields", sev, "content", "Expected fields not found",
                      "Not extracted: " + ", ".join(missing) + ". This may be an OCR/pattern limitation as well as a document issue."))
    ocr_conf = [p["ocr_confidence"] for p in pages if p["ocr_confidence"] is not None]
    if ocr_conf and min(ocr_conf) < 0.75:
        out.append(_f("low_ocr", "info", "content", "Low OCR confidence",
                      f"Lowest page OCR confidence is {min(ocr_conf):.2f}; extracted values may be wrong."))

    ref, parts = _val(parsed, "reference_no"), parsed["reference_parts"]
    if ref and not parts:
        out.append(_f("ref_format", "low", "content", "Reference number has an unexpected format",
                      "Expected something like <Region>/<id>/<year>/<code>. Heuristic; confirm against real samples.", ref))
    if parts:
        lt = _val(parsed, "letter_type")
        if lt == "Extension of Approval" and "EOA" not in parts["suffix"].upper():
            out.append(_f("type_suffix", "low", "content", "Letter type and reference suffix differ",
                          "Heading says Extension of Approval but the reference code lacks 'EOA' (heuristic).", ref))
        app = _val(parsed, "application_id")
        if app and app != parts["application_id"]:
            out.append(_f("app_id_mismatch", "medium", "content", "Application ID differs from reference number",
                          f"Labelled Application ID is {app}; reference number contains {parts['application_id']}.", ref))

    span = parsed["academic_year_span"]
    if span and span[1] != span[0] + 1:
        out.append(_f("ay_span", "medium", "content", "Academic year is not consecutive",
                      f"Parsed {span[0]}-{span[1]}.", _val(parsed, "academic_year")))
    if span and parts and abs(parts["year"] - span[0]) > 1:
        out.append(_f("ay_ref_year", "low", "content", "Reference year far from academic year",
                      f"Reference year {parts['year']} vs academic year starting {span[0]} (heuristic).", ref))

    issue = parse_date(_val(parsed, "issue_date") or "")
    valid = parse_date(_val(parsed, "valid_upto") or "")
    if issue:
        if issue > today:
            out.append(_f("future_date", "high", "content", "Issue date is in the future", f"{issue} is after {today}.", fields["issue_date"]["evidence"]))
        if issue < date(1987, 1, 1):
            out.append(_f("old_date", "high", "content", "Issue date predates the AICTE Act (1987)", str(issue), fields["issue_date"]["evidence"]))
        if span and not (span[0] - 1 <= issue.year <= span[0] + 2):
            out.append(_f("date_vs_ay", "low", "content", "Issue date far from academic year",
                          f"Issued {issue}; academic year starts {span[0]} (heuristic).", fields["issue_date"]["evidence"]))
    if issue and valid and valid < issue:
        out.append(_f("valid_before_issue", "high", "content", "Validity ends before issue date", f"Valid until {valid}; issued {issue}.", fields["valid_upto"]["evidence"]))

    # --- PDF structure ---
    if pdfinfo:
        tool = f"{pdfinfo['producer'] or ''} {pdfinfo['creator'] or ''}".lower()
        hit = next((t for t in EDIT_TOOLS if t in tool), None)
        if hit:
            out.append(_f("edit_tool", "medium", "structure", "Produced by an editing/conversion tool",
                          f"Metadata mentions '{hit}'. Legitimate for re-saved copies, but unusual for an original letter.", tool.strip()))
        if pdfinfo["creation_date"] and pdfinfo["mod_date"]:
            from datetime import datetime
            delta = datetime.fromisoformat(pdfinfo["mod_date"]) - datetime.fromisoformat(pdfinfo["creation_date"])
            if delta.days >= 1:
                out.append(_f("mod_after_create", "low", "structure", "Modified after creation",
                              f"Modified {delta.days} day(s) after creation.", f"{pdfinfo['creation_date']} -> {pdfinfo['mod_date']}"))
        if pdfinfo["eof_markers"] > 1:
            out.append(_f("incremental", "low", "structure", "Incremental updates present",
                          f"{pdfinfo['eof_markers']} %%EOF markers: the file was saved with appended revisions (also normal for signed PDFs)."))
        if "Launch" in pdfinfo["active_content"]:
            out.append(_f("launch", "high", "structure", "PDF contains a Launch action", "Can start external programs; do not open in an unsafe viewer."))
        other = [a for a in pdfinfo["active_content"] if a != "Launch"]
        if other:
            out.append(_f("active", "medium", "structure", "PDF contains active/embedded content", ", ".join(other)))
        if pdfinfo["font_count"] > 5:
            out.append(_f("fonts", "low", "structure", "Many distinct fonts", f"{pdfinfo['font_count']} fonts: {', '.join(pdfinfo['fonts'][:6])}"))

    # --- visual ---
    for e in visual["ela"]:
        if 3 <= e["outlier_blocks"] <= max(3, int(0.05 * e["total_blocks"])):
            out.append(_f("ela", "low", "image", f"Localised compression inconsistency (page {e['page']})",
                          f"{e['outlier_blocks']} of {e['total_blocks']} blocks are strong ELA outliers (max z={e['max_z']}). "
                          "ELA is noisy on text documents: treat as a prompt to look, not as proof."))
    for q in visual["qr"]:
        out.append(_f("qr", "info", "image", f"QR code found (page {q['page']})",
                      "Decoded but NOT validated or opened (official validation unsupported).", q["data"]))
    return out


def score(findings: list[dict]) -> dict:
    s = min(100, sum(WEIGHT[f["severity"]] for f in findings))
    level = "LOW" if s < 15 else "MEDIUM" if s < 40 else "HIGH"
    return {"score": s, "level": level,
            "note": "Review priority only. A LOW score does not mean the document is genuine."}
