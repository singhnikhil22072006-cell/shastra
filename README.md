# SHASTRA — Document Integrity Grid (AICTE approval / extension letters)

React + Vite + three.js frontend (cyberpunk UI), FastAPI backend, Supabase Auth + Postgres + private Storage.

## Three panels (role-based, enforced on the server)
| Role | What they do |
|---|---|
| **User** | Upload letters, see verdict + authenticity signals + findings, re-verify, download PDF report, personal analytics, read published reports |
| **Organization** | (after admin approval) Maintain the **issuer registry** (single add, CSV import, revoke/reinstate), review matching submissions (uploader identity hidden), publish reports, org analytics |
| **Admin** | Global analytics, all documents, approve/suspend organizations, change roles / suspend users, publish or withdraw reports, audit log |

## What's new in v2 (7 features)
| # | Feature | Who | Where |
|---|---|---|---|
| 1 | **Reference lookup** – check a reference number against approved issuers' registries without uploading (exact match only, rate-limited; shows ACTIVE / REVOKED / EXPIRED) | User | *Reference lookup* tab · `GET /api/lookup?ref=` |
| 2 | **History search & verdict filter** (file name, reference, institute, AY) | User | History card · `GET /api/documents?q=&verdict=` |
| 3 | **Batch upload** – up to 20 files, analysed one by one with per-file progress and verdict | User | *Upload letters* (multi-select / drop several) |
| 4 | **Share links** – expiring (1–90 days), revocable, no-login page showing only the identity-free verdict snapshot; max 5 live links per document | User | *Share* button · `POST /api/documents/{id}/share`, `DELETE /api/shares/{id}`, public `GET /api/public/share/{token}` (page: `/?share=TOKEN`) |
| 5 | **Review workflow + internal notes** – flagged → under review → resolved / dismissed, with a note trail visible only to org reviewers and admins (uploaders see the status, never the notes); re-verifying keeps the decision | Org, Admin | *Review* card on a submission · `POST /api/{org,admin}/documents/{id}/review` |
| 6 | **CSV exports** (spreadsheet-formula-injection safe, Excel-friendly UTF-8): my documents, org submissions (uploader-blind), registry (re-importable), all documents, audit log | all | *Export CSV* buttons |
| 7 | **Registry editing + expiry alerts** – edit any record field (duplicate-reference guard), "approvals expiring within 60 days" card, EXPIRING badge in the table | Org | *Registry* tab · `PATCH /api/org/registry/{id}` |
| + | **Most-flagged institutes** chart in every analytics view | all | Analytics |

**Upgrade:** re-run `supabase/schema.sql` (idempotent) – it adds `documents.review_notes` and the `share_links` table.

Notes: a share link is a *frozen snapshot* (re-verifying later does not change it). Batch uploads still obey the 10-uploads-per-10-minutes limit in `routes.rate_limit`; raise `limit` there if your users batch more.

## How "verified" is decided
Verification is **against the issuing organization's registry**, not a live AICTE query. Verdicts:
- **VERIFIED** – registry record matches field-by-field AND at least one independent feature corroborates (file SHA-256 pinned by issuer, intact signature, issuer's expected watermark, official-domain QR) AND no high-severity finding.
- **PARTIAL** – registry matches, nothing independent corroborates (a forger can copy public data).
- **UNVERIFIED** – no issuer record exists (not the same as fake).
- **SUSPICIOUS** – high-severity indicators without a registry record.
- **MISMATCH** – registry record exists but the document conflicts with it (year, institute, validity, unapproved programmes) or the approval is revoked.

Signals: issuer registry, file fingerprint, **watermark** (PDF diagonal/light/transparent text, /Watermark artifacts, layers; raster faint-overlay + OCR), **digital signature** (ByteRange coverage + cryptographic intactness via pyHanko), **QR** (decoded, never opened; host vs `OFFICIAL_DOMAINS`; reference cross-check), metadata/EXIF editing traces, ELA on scans, **cross-document conflicts** across all stored submissions, regulatory flags (expired, revoked, past year, unapproved programme).

## Honest limits
- Signer **certificate trust is not established** (no trust roots configured): a self-signed signature shows as "intact, untrusted". Add trust roots in `signature.py` to change this.
- Watermarks can be copied; they only help when the issuer registers the expected text.
- ELA is a noisy heuristic. Regex field parsing needs tuning on real letters. Confirm `OFFICIAL_DOMAINS` with AICTE.
- Stats are computed in Python (fine to a few thousand documents; move to SQL views beyond that).

## Set up
1. Supabase → SQL Editor → run `supabase/schema.sql` (idempotent; upgrades an existing install).
2. `powershell -ExecutionPolicy Bypass -File .\setup.ps1`, then fill `backend\.env` and `frontend\.env`.
   Set `ADMIN_EMAILS` to your e-mail: it becomes admin on first login **only if that e-mail is confirmed** in Supabase.
3. Run:
        cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000
        cd frontend; npm run dev        # http://localhost:5173

## Tests
    cd backend; pip install pytest httpx; python -m pytest tests -q

## v3 additions (SIH redesign, increment 1)
| Addition | Where | Notes |
|---|---|---|
| Duplicate & inconsistency analysis (repeated submission / shared file / new version / conflict) | *Duplicates* tab in all three panels · `GET /api/duplicates`, `/api/org/duplicates` (uploader-blind), `/api/admin/duplicates` | Only *conflict* groups are marked for review. Average verification time is reported as "not measured". |
| Measured impact baseline | Admin → Duplicates · `GET/PUT /api/admin/impact` | Admin enters the real baseline; reduction = ((baseline − post) / baseline) × 100. Empty state until a baseline exists. |
| Explained findings | Result page | Each finding shows Detected / Why it matters / Evidence / Next step, plus a plain-language verdict explanation and a signature-trust caveat. Copy lives in `components/guide.js`. |
| Public platform tour | `/#/site/home` (works signed in or out) | Overview, workflow, architecture (implemented / external / planned), applicants, deployment, economics calculator, security & limits, judges' view. |

**Migration:** re-run `supabase/schema.sql` (adds `impact_baselines`). **New env vars / dependencies:** none.
**Tests:** `python -m pytest tests -q` → 21 passed. Frontend: `npm run build` succeeds.

### Not done yet
Per-document processing-time measurement; verdict-over-time stacked chart; browser/accessibility audit (axe, mobile pass); 3D document-through-pipeline hero (existing Scene3D kept); guided demo with labelled sample data; PDF report additions (duplicate section); multilingual OCR, trusted certificate roots, on-prem/offline mode (all planned, not built).
