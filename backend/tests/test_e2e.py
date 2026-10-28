import datetime
import io
import os
import sys
import types

import pymupdf as fitz
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.update(SUPABASE_URL="http://x", SUPABASE_SERVICE_ROLE_KEY="k", ADMIN_EMAILS="boss@gov.test")
from fake_supabase import FakeSB  # noqa: E402

FAKE = FakeSB()
sys.modules["supabase"] = types.SimpleNamespace(create_client=lambda *a, **k: FAKE)
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
T = datetime.date.today()
FUTURE = (T + datetime.timedelta(days=200)).strftime("%d/%m/%Y")
AYS = T.year if T.month >= 6 else T.year - 1
AY = f"{AYS}-{str(AYS + 1)[2:]}"


def letter(ref="Western/1-12345/%d/EOA" % AYS, inst="Sunrise Institute of Technology", ay=AY, courses=("B.Tech Computer Science",),
           wm="AICTE ORIGINAL", valid=FUTURE, producer=None):
    doc = fitz.open(); p = doc.new_page()
    y = 90
    for line in ["All India Council for Technical Education (AICTE)", f"F.No. {ref}", f"Date: 01/07/{AYS}",
                 "Extension of Approval", f"Name of the Institution: {inst}", f"Academic Year: {ay}",
                 f"Approval is valid upto {valid}", *courses]:
        p.insert_text((60, y), line, fontsize=11); y += 22
    if wm:
        p.insert_text((110, 620), wm, fontsize=60, color=(0.86, 0.86, 0.86), morph=(fitz.Point(110, 620), fitz.Matrix(35)))
    if producer:
        doc.set_metadata({"producer": producer})
    return doc.tobytes()


def H(tok): return {"Authorization": f"Bearer {tok}"}
def up(tok, data, name="letter.pdf"): return client.post("/api/analyze", files={"file": (name, data, "application/pdf")}, headers=H(tok))


@pytest.fixture(scope="module", autouse=True)
def people():
    FAKE.add_user("adm", "boss@gov.test")
    FAKE.add_user("org", "reg@sunrise.test", meta={"requested_role": "organization", "org_name": "AICTE Western Office"})
    FAKE.add_user("u1", "student@x.test")
    FAKE.add_user("u2", "other@x.test")
    FAKE.add_user("fakeadm", "boss@gov.test", confirmed=False)  # same e-mail but unconfirmed must NOT become admin


def test_roles_and_org_approval():
    assert client.get("/api/me", headers=H("adm")).json()["role"] == "admin"
    assert client.get("/api/me", headers=H("fakeadm")).json()["role"] == "user"
    assert client.get("/api/me", headers=H("org")).json()["role"] == "org"
    assert client.get("/api/org/registry", headers=H("org")).status_code == 403          # pending org: no access
    assert client.get("/api/admin/stats", headers=H("u1")).status_code == 403            # user cannot reach admin
    assert client.get("/api/admin/stats", headers=H("org")).status_code == 403
    assert client.get("/api/me").status_code == 401
    oid = client.get("/api/admin/orgs", headers=H("adm")).json()[0]["id"]
    assert client.patch(f"/api/admin/orgs/{oid}", json={"status": "approved"}, headers=H("adm")).status_code == 200
    assert client.get("/api/org/registry", headers=H("org")).status_code == 200


def test_registry_import_and_validation():
    csv_text = ("reference_no,institute_name,academic_year,valid_upto,courses,expected_watermark\n"
                f"Western/1-12345/{AYS}/EOA,Sunrise Institute of Technology,{AY},{(T + datetime.timedelta(days=200)).isoformat()},B.Tech,AICTE ORIGINAL\n"
                f"Western/1-55555/{AYS}/EOA,Lakeview College,{AY},,MBA,\n"
                ",missing ref,,,,\n")
    r = client.post("/api/org/registry/import", json={"csv": csv_text}, headers=H("org")).json()
    assert r["added"] == 2 and len(r["errors"]) == 1
    assert client.post("/api/org/registry", json={"reference_no": "A/1/2/B", "institute_name": "X", "sha256": "zz"}, headers=H("org")).status_code == 422


def test_verified_genuine_letter():
    d = up("u1", letter()).json()
    v = d["result"]["verification"]
    assert v["status"] == "VERIFIED", (v, d["result"]["findings"])
    assert d["result"]["watermark"]["expected_found"] is True
    assert d["org_id"]


def test_mismatch_forged_letter():
    d = up("u2", letter(ay="2019-20", courses=("B.Tech Computer Science", "MBA Finance"), wm=None, valid=FUTURE)).json()
    r = d["result"]
    assert r["verification"]["status"] == "MISMATCH", r["verification"]
    fields = {x["field"] for x in r["registry_match"]["diffs"]}
    assert {"academic_year", "programmes"} <= fields
    ids = {f["id"] for f in r["findings"]}
    assert "wm_missing" in ids and "ref_ay_conflict" in ids       # missing watermark + conflict with the genuine copy
    assert d["review_status"] == "flagged"


def test_reuse_of_reference_with_other_institute():
    r = up("u2", letter(inst="Totally Different Polytechnic College", wm=None)).json()["result"]
    assert "ref_reuse" in {f["id"] for f in r["findings"]}
    assert r["verification"]["status"] in ("MISMATCH", "SUSPICIOUS")


def test_unknown_letter_is_unverified_not_fake():
    r = up("u1", letter(ref="South/9-99999/%d/EOA" % AYS, inst="Nowhere Institute", wm=None)).json()["result"]
    assert r["verification"]["status"] == "UNVERIFIED", r["verification"]


def test_expired_and_revoked():
    r = up("u1", letter(ref="South/9-11111/%d/EOA" % AYS, inst="Old College", wm=None, valid="01/01/2020")).json()["result"]
    assert "expired" in {f["id"] for f in r["findings"]}


def test_signature_tamper_detected():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nm = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Reg Office")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nm).issuer_name(nm).public_key(key.public_key()).serial_number(2)
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=9)).sign(key, hashes.SHA256()))
    open("/tmp/_k.pem", "wb").write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    open("/tmp/_c.pem", "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    signer = signers.SimpleSigner.load("/tmp/_k.pem", "/tmp/_c.pem", key_passphrase=None)
    base = letter(ref="East/2-22222/%d/EOA" % AYS, inst="Signed Institute", wm=None)
    w = IncrementalPdfFileWriter(io.BytesIO(base)); fields.append_signature_field(w, fields.SigFieldSpec("S"))
    out = io.BytesIO(); signers.sign_pdf(w, signers.PdfSignatureMetadata(field_name="S"), signer=signer, output=out)
    good = out.getvalue()
    r = up("u1", good).json()["result"]
    sig = next(s for s in r["verification"]["signals"] if s["id"] == "signature")
    assert sig["state"] == "warn" and r["signatures"]["signatures"][0]["intact"] is True    # intact but untrusted
    bad = good + b"\n%% appended after signing\n"
    r2 = up("u1", bad).json()["result"]
    assert "sig_appended" in {f["id"] for f in r2["findings"]}
    assert r2["verification"]["status"] == "SUSPICIOUS"


def test_isolation_and_org_view():
    mine = client.get("/api/documents", headers=H("u2")).json()
    assert all(d["user_id"] for d in mine)
    other = client.get("/api/documents", headers=H("u1")).json()[0]["id"]
    assert client.get(f"/api/documents/{other}", headers=H("u2")).status_code == 404     # users cannot read each other's docs
    odocs = client.get("/api/org/documents", headers=H("org")).json()
    assert odocs and all("filename" not in d and "user_id" not in d for d in odocs)      # org never sees uploader identity
    full = client.get(f"/api/org/documents/{odocs[0]['id']}", headers=H("org")).json()
    assert "text_excerpt" not in full["result"]
    assert client.get(f"/api/org/documents/{other}", headers=H("org")).status_code in (200, 404)


def test_publish_flow_and_stats():
    flagged = [d for d in client.get("/api/org/documents", headers=H("org")).json() if d["review_status"] == "flagged"]
    assert flagged
    pub = client.post(f"/api/org/documents/{flagged[0]['id']}/publish", json={"title": "Mismatch in AY", "note": "n", "scope": "public"}, headers=H("org"))
    assert pub.status_code == 200 and "filename" not in str(pub.json()["snapshot"])
    seen = client.get("/api/published", headers=H("u1")).json()
    assert len(seen) == 1 and seen[0]["snapshot"]["verdict"] in ("MISMATCH", "SUSPICIOUS")
    assert client.patch(f"/api/admin/reports/{seen[0]['id']}", json={"status": "withdrawn"}, headers=H("adm")).status_code == 200
    assert client.get("/api/published", headers=H("u1")).json() == []
    s = client.get("/api/admin/stats", headers=H("adm")).json()
    assert s["total"] >= 6 and s["flagged"] >= 2 and s["by_verdict"]["VERIFIED"] == 1 and s["orgs"]["approved"] == 1
    assert len(s["timeline"]) == 14 and sum(t["documents"] for t in s["timeline"]) == s["total"]
    assert client.get("/api/stats", headers=H("u2")).json()["total"] >= 2
    assert len(client.get("/api/admin/audit", headers=H("adm")).json()) >= 3


def test_reverify_after_registry_addition_and_report_pdf():
    ref = "South/9-99999/%d/EOA" % AYS
    doc = next(d for d in client.get("/api/documents", headers=H("u1")).json() if d["reference_no"] == ref)
    assert doc["verification_status"] == "UNVERIFIED"
    client.post("/api/org/registry", json={"reference_no": ref, "institute_name": "Nowhere Institute", "academic_year": AY}, headers=H("org"))
    r = client.post(f"/api/documents/{doc['id']}/reverify", headers=H("u1")).json()
    assert r["verification_status"] == "PARTIAL"                                       # registry matches, nothing corroborates
    pdf = client.get(f"/api/documents/{doc['id']}/report.pdf", headers=H("u1"))
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    bad = [d for d in client.get("/api/admin/documents", headers=H("adm")).json() if d["verification_status"] == "MISMATCH"][0]
    assert client.get(f"/api/admin/documents/{bad['id']}/report.pdf", headers=H("adm")).content[:5] == b"%PDF-"


# ============================================================== v2 features
REF = "Western/1-12345/%d/EOA" % AYS


def test_lookup_by_reference():
    r = client.get("/api/lookup", params={"ref": REF}, headers=H("u1")).json()
    assert r["found"] and r["records"][0]["state"] == "ACTIVE" and r["records"][0]["institute_name"].startswith("Sunrise")
    assert "sha256" not in r["records"][0] and "notes" not in r["records"][0]            # only public fields
    assert client.get("/api/lookup", params={"ref": REF.lower().replace("/", " / ")}, headers=H("u1")).status_code == 200
    assert client.get("/api/lookup", params={"ref": "Nope/0-00000/1999/EOA"}, headers=H("u1")).json() == {"found": False, "records": []}
    assert client.get("/api/lookup", params={"ref": "ab"}, headers=H("u1")).status_code == 422
    assert client.get("/api/lookup", params={"ref": REF[:8]}, headers=H("u1")).json()["found"] is False   # no prefix enumeration
    assert client.get("/api/lookup", params={"ref": REF}).status_code == 401


def test_history_search_and_filter():
    allv = client.get("/api/documents", headers=H("u1")).json()
    assert len(allv) >= 3
    assert all(d["verification_status"] == "VERIFIED" for d in client.get("/api/documents", params={"verdict": "verified"}, headers=H("u1")).json())
    hit = client.get("/api/documents", params={"q": "sunrise"}, headers=H("u1")).json()
    assert hit and all("sunrise" in (d["institute_name"] or "").lower() for d in hit)
    assert client.get("/api/documents", params={"q": "zzz-no-such"}, headers=H("u1")).json() == []
    assert all(d["verification_status"] in ("MISMATCH", "SUSPICIOUS") for d in client.get("/api/documents", params={"verdict": "flagged"}, headers=H("u2")).json())


def test_csv_exports_and_formula_injection_guard():
    from app.features import csv_safe
    assert csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)" and csv_safe("@x") == "'@x" and csv_safe("+1") == "'+1" and csv_safe(None) == ""
    assert csv_safe(["a", "b"]) == "a; b" and csv_safe("plain") == "plain"
    mine = client.get("/api/documents/export.csv", headers=H("u1"))
    assert mine.status_code == 200 and mine.headers["content-type"].startswith("text/csv") and "letter.pdf" in mine.text
    org = client.get("/api/org/documents/export.csv", headers=H("org"))
    assert org.status_code == 200 and "filename" not in org.text.splitlines()[0] and "letter.pdf" not in org.text   # uploader-blind
    reg = client.get("/api/org/registry/export.csv", headers=H("org")).text
    assert reg.splitlines()[0].lstrip("﻿").startswith("reference_no,") and REF in reg
    assert client.get("/api/admin/documents/export.csv", headers=H("adm")).status_code == 200
    assert "action" in client.get("/api/admin/audit/export.csv", headers=H("adm")).text
    assert client.get("/api/admin/documents/export.csv", headers=H("u1")).status_code == 403
    assert client.get("/api/admin/audit/export.csv", headers=H("org")).status_code == 403
    assert client.get("/api/org/registry/export.csv", headers=H("u1")).status_code == 403


def test_share_link_lifecycle():
    doc = next(d for d in client.get("/api/documents", headers=H("u1")).json() if d["verification_status"] == "VERIFIED")
    assert client.post(f"/api/documents/{doc['id']}/share", json={"days": 3}, headers=H("u2")).status_code == 404   # not your document
    assert client.post(f"/api/documents/{doc['id']}/share", json={"days": 0}, headers=H("u1")).status_code == 422
    assert client.post(f"/api/documents/{doc['id']}/share", json={"days": "x"}, headers=H("u1")).status_code == 422
    link = client.post(f"/api/documents/{doc['id']}/share", json={"days": 3}, headers=H("u1")).json()
    assert len(link["token"]) >= 30
    pub = client.get(f"/api/public/share/{link['token']}")                          # NO auth header
    assert pub.status_code == 200
    snap = pub.json()["snapshot"]
    assert snap["verdict"] == "VERIFIED" and "letter.pdf" not in pub.text and "user_id" not in pub.text and "filename" not in pub.text
    assert client.get("/api/public/share/not-a-real-token").status_code == 404
    listed = client.get(f"/api/documents/{doc['id']}/shares", headers=H("u1")).json()
    assert listed[0]["live"] is True and listed[0]["views"] == 1 and "snapshot" not in listed[0]
    assert client.get(f"/api/documents/{doc['id']}/shares", headers=H("u2")).status_code == 404
    assert client.delete(f"/api/shares/{link['id']}", headers=H("u2")).status_code == 404       # only the owner can revoke
    assert client.delete(f"/api/shares/{link['id']}", headers=H("u1")).status_code == 200
    assert client.get(f"/api/public/share/{link['token']}").status_code == 404                  # revoked
    # expired links fail closed
    exp = client.post(f"/api/documents/{doc['id']}/share", json={"days": 1}, headers=H("u1")).json()
    for row in FAKE.tables["share_links"]:
        if row["id"] == exp["id"]:
            row["expires_at"] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)).isoformat()
    assert client.get(f"/api/public/share/{exp['token']}").status_code == 404


def test_share_limit_and_cascade_on_delete():
    d = next(d for d in client.get("/api/documents", headers=H("u1")).json() if d["verification_status"] == "UNVERIFIED")
    for _ in range(5):
        assert client.post(f"/api/documents/{d['id']}/share", headers=H("u1")).status_code == 200
    assert client.post(f"/api/documents/{d['id']}/share", headers=H("u1")).status_code == 409
    tok = FAKE.tables["share_links"][-1]["token"]
    assert client.get(f"/api/public/share/{tok}").status_code == 200
    # deleting the document must kill its links
    assert client.delete(f"/api/documents/{d['id']}", headers=H("u1")).status_code == 200
    assert client.get(f"/api/public/share/{tok}").status_code == 404


def test_review_workflow_and_internal_notes():
    flagged = next(d for d in client.get("/api/org/documents", headers=H("org")).json() if d["verification_status"] == "MISMATCH")
    did = flagged["id"]
    assert client.post(f"/api/org/documents/{did}/review", json={"status": "nonsense"}, headers=H("org")).status_code == 422
    assert client.post(f"/api/org/documents/{did}/review", json={"status": "resolved"}, headers=H("u1")).status_code == 403
    r = client.post(f"/api/org/documents/{did}/review", json={"status": "under_review", "note": "Calling the institute"}, headers=H("org")).json()
    assert r["review_status"] == "under_review" and r["review_notes"][0]["note"] == "Calling the institute"
    assert client.post(f"/api/admin/documents/{did}/review", json={"status": "resolved", "note": "Confirmed forged"}, headers=H("adm")).json()["review_notes"][-1]["role"] == "admin"
    assert len(client.get(f"/api/org/documents/{did}", headers=H("org")).json()["review_notes"]) == 2
    assert len(client.get(f"/api/admin/documents/{did}", headers=H("adm")).json()["review_notes"]) == 2
    owner_view = client.get(f"/api/documents/{did}", headers=H("u2")).json()                 # u2 uploaded the mismatch letter
    assert owner_view["review_status"] == "resolved" and "review_notes" not in owner_view    # decision visible, notes internal
    after = client.post(f"/api/documents/{did}/reverify", headers=H("u2")).json()
    assert after["review_status"] == "resolved"                                              # re-verify keeps the reviewer's decision
    assert client.get(f"/api/org/documents", headers=H("org")).json()
    assert client.get("/api/org/stats", headers=H("org")).json()["review"]["resolved"] >= 1


def test_registry_edit_duplicate_and_expiry_alerts():
    soon = (T + datetime.timedelta(days=20)).isoformat()
    client.post("/api/org/registry", json={"reference_no": "North/3-33333/%d/EOA" % AYS, "institute_name": "Edge College", "valid_upto": soon}, headers=H("org"))
    reg = {r["reference_no"]: r for r in client.get("/api/org/registry", headers=H("org")).json()}
    rec = reg["North/3-33333/%d/EOA" % AYS]
    st = client.get("/api/org/stats", headers=H("org")).json()["registry"]
    assert any(x["reference_no"] == rec["reference_no"] and x["days_left"] == 20 for x in st["expiring_soon"])
    assert not any(x["reference_no"] == REF for x in st["expiring_soon"])                    # 200 days out: not flagged
    ok = client.patch(f"/api/org/registry/{rec['id']}", json={"institute_name": "Edge College (Renamed)", "valid_upto": (T + datetime.timedelta(days=400)).isoformat(), "courses": "B.Tech; MBA"}, headers=H("org"))
    assert ok.status_code == 200
    new = next(r for r in client.get("/api/org/registry", headers=H("org")).json() if r["id"] == rec["id"])
    assert new["institute_name"] == "Edge College (Renamed)" and new["courses"] == ["B.Tech", "MBA"] and new["reference_no"] == rec["reference_no"]
    st2 = client.get("/api/org/stats", headers=H("org")).json()["registry"]
    assert not any(x["reference_no"] == rec["reference_no"] for x in st2["expiring_soon"])
    assert client.patch(f"/api/org/registry/{rec['id']}", json={"reference_no": REF}, headers=H("org")).status_code == 409   # duplicate ref
    assert client.patch(f"/api/org/registry/{rec['id']}", json={"sha256": "zz"}, headers=H("org")).status_code == 422
    assert client.patch(f"/api/org/registry/{rec['id']}", json={"institute_name": ""}, headers=H("org")).status_code == 422
    assert client.patch(f"/api/org/registry/{rec['id']}", json={}, headers=H("org")).status_code == 422
    assert client.patch(f"/api/org/registry/{rec['id']}", json={"status": "revoked"}, headers=H("org")).status_code == 200  # legacy revoke still works
    assert client.patch(f"/api/org/registry/{rec['id']}", json={"institute_name": "x"}, headers=H("u1")).status_code == 403
    assert client.get("/api/lookup", params={"ref": rec["reference_no"]}, headers=H("u1")).json()["records"][0]["state"] == "REVOKED"


def test_top_flagged_institutes_in_stats():
    s = client.get("/api/admin/stats", headers=H("adm")).json()
    assert s["top_institutes"] and all({"name", "flagged", "total"} <= set(x) and 0 < x["flagged"] <= x["total"] for x in s["top_institutes"])


def test_duplicate_analysis_classification_and_privacy():
    from app.duplicates import reduction_pct
    assert reduction_pct(40, 10) == 75.0 and reduction_pct(0, 5) is None and reduction_pct(None, 1) is None
    ref = "East/9-99999/%d/EOA" % AYS
    a = letter(ref=ref, inst="Dup Test College")
    up("u2", a, "orig.pdf"); up("u2", a, "again.pdf")                                   # same file, same account
    up("u1", a, "mine.pdf")                                                              # same file, other account
    up("u1", letter(ref=ref, inst="Totally Different University", ay="2019-20"), "conf.pdf")  # conflicting details
    d = client.get("/api/duplicates", headers=H("u2")).json()
    kinds = {g["kind"] for g in d["groups"]}
    assert "repeated_submission" in kinds and d["duplicate_files"] >= 1
    assert all(m.get("filename") for g in d["groups"] for m in g["members"])
    assert not any(m["filename"] in ("mine.pdf", "conf.pdf") for g in d["groups"] for m in g["members"])  # u2 never sees u1's files
    assert d["avg_verification_seconds"] is None                                          # not measured -> no invented number
    mine = client.get("/api/duplicates", headers=H("u1")).json()
    conflict = [g for g in mine["groups"] if g["kind"] == "conflict"]
    assert conflict and conflict[0]["needs_review"] and "institute_name" in conflict[0]["differs_in"]
    assert any(g["kind"] == "shared_file" and not g["needs_review"] for g in mine["groups"])   # shared file is NOT flagged
    ad = client.get("/api/admin/duplicates", headers=H("adm"))
    assert ad.status_code == 200 and ad.json()["total_documents"] >= mine["total_documents"]
    assert client.get("/api/admin/duplicates", headers=H("u1")).status_code == 403
    o = client.get("/api/org/duplicates", headers=H("org"))
    assert o.status_code == 200 and not any("filename" in m for g in o.json()["groups"] for m in g["members"])


def test_impact_baseline_is_admin_only_and_never_prefilled():
    empty = client.get("/api/admin/impact", headers=H("adm")).json()
    assert empty["baseline"] is None and empty["reduction_pct"] is None
    assert client.put("/api/admin/impact", json={"baseline_duplicate_cases": 10, "period_label": "x", "post_start": "2026-01-01"}, headers=H("u1")).status_code == 403
    assert client.put("/api/admin/impact", json={"baseline_duplicate_cases": 0, "period_label": "x", "post_start": "2026-01-01"}, headers=H("adm")).status_code == 422
    assert client.put("/api/admin/impact", json={"baseline_duplicate_cases": 10, "period_label": "x", "post_start": "garbage"}, headers=H("adm")).status_code == 422
    ok = client.put("/api/admin/impact", json={"baseline_duplicate_cases": 1000, "period_label": "Test period", "post_start": T.isoformat()}, headers=H("adm")).json()
    assert ok["baseline"]["baseline_duplicate_cases"] == 1000 and ok["post_duplicate_cases"] is not None
    assert ok["reduction_pct"] == round((1000 - ok["post_duplicate_cases"]) / 1000 * 100, 1)
