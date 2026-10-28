"""Evidence-based PDF report. All document-derived text is XML-escaped before it reaches ReportLab."""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VCOL = {"VERIFIED": "#15803d", "PARTIAL": "#a16207", "UNVERIFIED": "#475569", "SUSPICIOUS": "#c2410c", "MISMATCH": "#b91c1c"}
STATECOL = {"pass": "#15803d", "warn": "#a16207", "fail": "#b91c1c", "na": "#94a3b8"}
SEV = {"high": "#b91c1c", "medium": "#c2410c", "low": "#a16207", "info": "#475569"}
ss = getSampleStyleSheet()
BODY = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor("#334155"))
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)


def P(t, style=BODY):
    return Paragraph(escape(str(t if t is not None else "-")), style)


def _img(pil, width):
    buf = io.BytesIO()
    pil.save(buf, "PNG")
    buf.seek(0)
    return RLImage(buf, width=width, height=width * pil.height / pil.width)


def _table(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]
    t.setStyle(TableStyle(st))
    return t


def _chart(r: dict, W: float):
    """Bar chart: findings per category, coloured by nothing fancy -- readable in greyscale."""
    cats: dict[str, int] = {}
    for f in r["findings"]:
        if f["severity"] != "info":
            cats[f["category"]] = cats.get(f["category"], 0) + 1
    if not cats:
        return None
    items = sorted(cats.items(), key=lambda kv: kv[1])
    d = Drawing(W, 22 * len(items) + 30)
    c = HorizontalBarChart()
    c.x, c.y, c.width, c.height = 70, 12, W - 100, 22 * len(items)
    c.data = [[v for _, v in items]]
    c.categoryAxis.categoryNames = [k for k, _ in items]
    c.categoryAxis.labels.fontSize = 8
    c.valueAxis.valueMin, c.valueAxis.valueStep = 0, 1
    c.valueAxis.valueMax = max(v for _, v in items) + 1
    c.bars[0].fillColor = colors.HexColor("#0f6b7a")
    d.add(c)
    d.add(String(70, 22 * len(items) + 16, "Findings by category (excluding info)", fontSize=8))
    return d


def build_report(row: dict, user_email: str, thumb=None, heat=None) -> bytes:
    r = row["result"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title="SHASTRA document analysis report")
    W = A4[0] - 32 * mm
    s = [Paragraph("SHASTRA - Document Analysis Report", ss["Title"])]

    ver = r["verification"]
    s.append(_table([[Paragraph(f"<font color='{VCOL[ver['status']]}'><b>VERDICT: {escape(ver['status'])}</b></font> &nbsp; trust score {ver['trust_score']}/100<br/>{escape(ver['summary'])}<br/>"
                      f"<font size=7>{escape(r['official_verification']['reason'])}</font>", BODY)]], [W], header=False))
    s.append(Spacer(1, 6))

    f = r["file"]
    s.append(_table([
        [P("File"), P(f["name"])], [P("SHA-256"), P(f["sha256"], SMALL)],
        [P("Type / pages / size"), P(f"{f['type']} / {f['pages']} / {f['size']} bytes")],
        [P("Analysed (UTC)"), P(r["analyzed_at"])], [P("Requested by"), P(user_email)],
        [P("Review priority"), P(f"{r['risk']['level']} (score {r['risk']['score']}/100)")],
    ], [38 * mm, W - 38 * mm], header=False))
    s.append(P(r["risk"]["note"], SMALL))

    s.append(Paragraph("Extracted fields (with evidence)", H2))
    rows = [[P("Field"), P("Value"), P("Page / method"), P("Source text")]]
    for k, v in r["fields"].items():
        rows.append([P(k), P(v["value"] if v else "NOT FOUND"), P(f"{v['page']} / {v['method']}" if v else "-", SMALL), P(v["evidence"] if v else "-", SMALL)])
    s.append(_table(rows, [28 * mm, 42 * mm, 36 * mm, W - 106 * mm]))
    if r["courses"]:
        s.append(Spacer(1, 4))
        s.append(P("Programme lines detected: " + " | ".join(c["text"] for c in r["courses"][:8]), SMALL))

    s.append(Paragraph("Authenticity signals", H2))
    rows = [[P("Signal"), P("Result"), P("Detail")]]
    for x in ver["signals"]:
        rows.append([P(x["label"]), Paragraph(f"<font color='{STATECOL[x['state']]}'><b>{x['state'].upper()}</b></font>", BODY), P(x["detail"], SMALL)])
    s.append(_table(rows, [48 * mm, 18 * mm, W - 66 * mm]))
    rm = r["registry_match"]
    if rm["matched"] and rm["diffs"]:
        s.append(Paragraph("Mismatches against the issuer's record", H2))
        s.append(_table([[P("Field"), P("Document"), P("Registry"), P("Severity")]] +
                        [[P(d["field"]), P(d["document"]), P(d["registry"]), P(d["severity"])] for d in rm["diffs"]],
                        [32 * mm, (W - 52 * mm) / 2, (W - 52 * mm) / 2, 20 * mm]))
    ch = _chart(r, W)
    if ch:
        s.append(Spacer(1, 6))
        s.append(ch)

    s.append(Paragraph("Findings", H2))
    if r["findings"]:
        rows = [[P("Severity"), P("Check"), P("Detail and evidence")]]
        for x in r["findings"]:
            sev = Paragraph(f"<font color='{SEV[x['severity']]}'><b>{x['severity'].upper()}</b></font>", BODY)
            det = x["detail"] + (f"  [evidence: {x['evidence']}]" if x.get("evidence") else "")
            rows.append([sev, P(x["title"]), P(det, SMALL)])
        s.append(_table(rows, [20 * mm, 50 * mm, W - 70 * mm]))
    else:
        s.append(P("No rule-based findings were triggered. This is not proof of authenticity."))

    s.append(Paragraph("Extraction method", H2))
    s.append(_table([[P("Page"), P("Method"), P("OCR confidence"), P("Characters")]] +
                    [[P(e["page"]), P(e["method"]), P(e["ocr_confidence"] if e["ocr_confidence"] is not None else "n/a"), P(e["chars"])] for e in r["extraction"]],
                    [20 * mm, 50 * mm, 40 * mm, W - 110 * mm]))
    s.append(P("Engines: " + "; ".join(f"{k}: {v}" for k, v in r["engine"].items()), SMALL))

    if thumb is not None:
        s.append(Paragraph("First page (as analysed)", H2))
        s.append(_img(thumb, min(W, 110 * mm)))
    if heat is not None:
        s.append(Paragraph("Error-level-analysis heatmap, first page", H2))
        s.append(_img(heat, min(W, 110 * mm)))
        s.append(P("Heuristic visual aid. Bright regions are not proof of tampering.", SMALL))

    s.append(Paragraph("Limitations", H2))
    for t in ("Verification is against records uploaded by issuing organizations to this platform, not a live query of AICTE systems. Where no record exists the document is UNVERIFIED, not fake.",
              "Watermark and signature results are supporting signals: watermarks can be copied, and signer certificate trust is not established unless trust roots are configured.",
              "Field extraction uses heuristic patterns and OCR; wrong or missing values are possible.",
              "QR codes are decoded and compared to configured domains, never opened.",
              "Findings are indicators for human review, not a legal or forensic determination."):
        s.append(P("- " + t, SMALL))
    doc.build(s)
    return buf.getvalue()
