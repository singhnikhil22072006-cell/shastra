"""Rule-based field extraction with evidence. Every value carries page, method and source snippet.

The patterns are HEURISTICS written from the general shape of AICTE letters. Validate and tune
them against real sample letters before relying on them (see REGEX block).
"""
import re
from datetime import date, datetime

DATE = r"(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})"
REGEX = {
    "reference_no": r"F\.?\s*No\.?\s*[:.\-]?\s*(\S+/\S+(?:/\S+)*)",
    "permanent_id": r"Permanent\s*(?:ID|Id|No\.?)\s*[:\-]?\s*(\d-\d+)",
    "application_id": r"Application\s*(?:ID|Id|No\.?)\s*[:\-]?\s*(\d-\d+)",
    "academic_year": r"(?:Academic\s*Year|Approval\s*Process|Session|A\.?Y\.?)\s*[:\-]?\s*(20\d{2}\s*[-–/]\s*\d{2,4})",
    "institute_label": r"(?:Name\s+of\s+the\s+(?:Institution|Institute|College)|Institut(?:ion|e)\s+Name)\s*[:\-]?\s*(.+)",
    "issue_date": r"(?:Date|Dated)\s*[:\-]?\s*" + DATE,
    "valid_upto": r"(?:valid(?:ity)?\s*(?:up\s*to|upto|till|until)|till)\s*[:\-]?\s*" + DATE,
}
COURSE_RX = (r"\b(B\.?\s?Tech|B\.?E\.?|M\.?\s?Tech|MBA|MCA|PGDM|PGCM|Diploma|B\.?\s?Arch|M\.?\s?Arch|"
             r"B\.?\s?Pharm|M\.?\s?Pharm|B\.?\s?Des|BCA|BHMCT)\b")


def parse_date(s: str) -> date | None:
    s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", s.replace(",", " "))
    s = " ".join(s.split())
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _find(pages, rx, flags=re.I | re.M):
    for p in pages:
        m = re.search(rx, p["text"], flags)
        if m:
            s, e = max(0, m.start() - 30), min(len(p["text"]), m.end() + 30)
            return {
                "value": " ".join(m.group(1).split()),
                "page": p["page"],
                "method": f"regex on {p['method']}",
                "evidence": " ".join(p["text"][s:e].split()),
            }
    return None


def parse_fields(pages: list[dict]) -> dict:
    full = "\n".join(p["text"] for p in pages)
    fields: dict[str, dict | None] = {}

    # Letter type: "extension of approval" is checked first because those letters also say "approval".
    if re.search(r"extension\s*of\s*approval", full, re.I):
        lt = "Extension of Approval"
    elif re.search(r"approval", full, re.I):
        lt = "Approval"
    else:
        lt = None
    ev = _find(pages, r"(extension\s*of\s*approval|approval)")
    fields["letter_type"] = {**ev, "value": lt} if (ev and lt) else None

    for key in ("reference_no", "permanent_id", "application_id", "academic_year", "issue_date", "valid_upto"):
        fields[key] = _find(pages, REGEX[key])

    if not fields["issue_date"]:  # fallback: first numeric date on page 1
        fields["issue_date"] = _find(pages[:1], r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{4})\b")
    if fields["academic_year"]:
        fields["academic_year"]["value"] = re.sub(r"\s*[–/]\s*", "-", fields["academic_year"]["value"]).replace(" ", "")
    else:
        fields["academic_year"] = _find(pages, r"\b(20\d{2}\s*[-–]\s*\d{2,4})\b")

    inst = _find(pages, REGEX["institute_label"])
    if inst:
        inst["method"] += " (labelled field)"
    else:  # heuristic: first plausible institution-looking line on page 1
        for line in pages[0]["text"].splitlines():
            line = line.strip()
            if (8 <= len(line) <= 120 and re.search(r"\b(College|Institute|University|Institution|Polytechnic)\b", line, re.I)
                    and not re.search(r"AICTE|All India Council|Ministry|Government of India", line, re.I)):
                inst = {"value": line, "page": 1, "method": f"line heuristic on {pages[0]['method']} (low confidence)", "evidence": line}
                break
    fields["institute_name"] = inst

    # Derived parts of the reference number (only if it matches the expected shape)
    parts = None
    ref = fields["reference_no"]["value"] if fields["reference_no"] else None
    if ref:
        m = re.match(r"^([A-Za-z ]+)/(\d-\d+)/(\d{4})/([A-Za-z]+)$", ref)
        if m:
            parts = {"region": m[1].strip(), "application_id": m[2], "year": int(m[3]), "suffix": m[4]}

    ay_start = None
    if fields["academic_year"]:
        m = re.match(r"(20\d{2})-(\d{2,4})", fields["academic_year"]["value"])
        if m:
            end = int(m[2]) if len(m[2]) == 4 else int(m[1][:2] + m[2])
            ay_start = (int(m[1]), end)

    courses = []
    for p in pages:
        for line in p["text"].splitlines():
            if re.search(COURSE_RX, line, re.I) and len(line.strip()) <= 150 and len(courses) < 15:
                courses.append({"text": line.strip(), "page": p["page"]})

    return {
        "fields": fields,
        "reference_parts": parts,
        "academic_year_span": ay_start,
        "courses": courses,
        "mentions_aicte": bool(re.search(r"AICTE|All India Council for Technical Education", full, re.I)),
        "total_chars": len(full.strip()),
    }
