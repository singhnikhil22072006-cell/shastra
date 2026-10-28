import { useState } from "react";
import { Card, COLORS } from "./ui.jsx";

const PAGES = [["home", "Overview"], ["how", "How it works"], ["arch", "Architecture"], ["applicants", "Applicants"], ["deploy", "Deployment"], ["economics", "Economics"], ["trust", "Security & limits"], ["judges", "Judges' view"]];
const STAGES = [
  ["Upload", "Submit PDF, PNG or JPEG letters (single or batch of up to 20)."],
  ["Extract", "Read the text layer, or OCR scanned pages, and parse reference, institute, year and validity."],
  ["Verify", "Compare with approved issuers' registries and check watermark, signature, QR and file fingerprint where present."],
  ["Investigate", "Surface conflicts across stored documents, regulatory flags and metadata traces, each with evidence."],
  ["Report", "Produce a verdict, a PDF report, history and an audit trail. Reviewers make the final decision."],
];
// state: impl = in this codebase, ext = external service/dependency, plan = not built
const NODES = [
  ["Applicant / Institution / Reviewer", "impl", "Roles: user, org, admin"],
  ["React + Vite + three.js frontend", "impl", "frontend/src"],
  ["FastAPI backend", "impl", "backend/app/routes.py"],
  ["Auth and access control", "ext", "Supabase Auth, enforced by FastAPI role checks"],
  ["Document pipeline", "impl", "PyMuPDF, RapidOCR (ONNX), regex field parsing"],
  ["Registry, authenticity, cross-document checks", "impl", "issuer registry, watermark, pyHanko signatures, QR, ELA, duplicates"],
  ["Verdict and evidence", "impl", "VERIFIED / PARTIAL / UNVERIFIED / SUSPICIOUS / MISMATCH"],
  ["PDF report, history, audit trail", "impl", "reportlab, Postgres audit_log"],
  ["PostgreSQL and private file storage", "ext", "Supabase (hosted)"],
  ["Live AICTE / government database queries", "plan", "Not connected. Registry is issuer-uploaded."],
  ["Trusted certificate roots for signatures", "plan", "Not configured; signer trust is not established"],
  ["On-premises / offline deployment", "plan", "Planned; not built or tested"],
  ["Multilingual OCR and learned anomaly models", "plan", "Current engine is classical heuristics + pretrained OCR"],
];
const NC = { impl: COLORS.lime, ext: COLORS.cyan, plan: COLORS.amber };
const NL = { impl: "Implemented", ext: "External service", plan: "Planned" };

export default function Site() {
  const [page, setPage] = useState(location.hash.split("/")[2] || "home");
  const go = (p) => { setPage(p); history.replaceState(null, "", `#/site/${p}`); scrollTo(0, 0); };
  return (
    <>
      <header className="top"><div className="brand"><span className="glitch" data-text="SHASTRA">SHASTRA</span><span className="chip user">Document Integrity Grid</span></div>
        <a className="ghost sm btnlink" href={location.pathname}>Sign in / Open app</a></header>
      <nav className="tabs" role="tablist" aria-label="Site sections">{PAGES.map(([id, l]) => <button key={id} role="tab" aria-selected={page === id} className={page === id ? "on" : ""} onClick={() => go(id)}>{l}</button>)}</nav>
      <main className="page grid">
        {page === "home" && <Home go={go} />}
        {page === "how" && <How />}
        {page === "arch" && <Arch />}
        {page === "applicants" && <Applicants />}
        {page === "deploy" && <Deploy />}
        {page === "economics" && <Economics />}
        {page === "trust" && <Trust />}
        {page === "judges" && <Judges />}
      </main>
    </>
  );
}

function Home({ go }) {
  return (<>
    <section className="hero-site">
      <div className="tag">&gt; SIH 2026 · SIH26261 · TEAM A_TECH TITANS</div>
      <h1 className="glitch" data-text="Trust Every Document. Verify Every Detail.">Trust Every Document. Verify Every Detail.</h1>
      <p style={{ fontSize: "1.2rem", maxWidth: "40rem", color: "#b6c8dc" }}>SHASTRA brings document analysis, authenticity signals, issuer-registry checks, and evidence-based review into one verification workflow.</p>
      <div className="row"><a className="btnlink" href={location.pathname}>Start Verification</a><button className="ghost" onClick={() => go("how")}>Explore How It Works</button></div>
      <p className="small muted">SHASTRA flags signals for human review. It does not claim every document can be conclusively authenticated.</p>
    </section>
    <h3>The problem with manual review</h3>
    <div className="grid g4">{["Time-consuming document review", "Missing fields and incomplete applications", "Conflicting details across supporting documents", "Repeated or duplicate submissions", "Potential forgery and manipulation", "Complex regulatory requirements", "Limited traceability of decisions"].map((t) => <Card key={t}><b>{t}</b></Card>)}</div>
    <h3>What it gives reviewers</h3>
    <div className="grid g2">{["Less repetitive manual work", "Earlier identification of missing information", "More consistent cross-document checks", "Visibility into possible duplicates", "Evidence behind every finding", "Traceable verification history", "Human oversight for final decisions"].map((t) => <Card key={t}>{t}</Card>)}</div>
  </>);
}

function How() {
  const [i, setI] = useState(0);
  return (<>
    <h3>Five-stage workflow</h3>
    <div className="steps" role="tablist">{STAGES.map(([n], k) => <button key={n} role="tab" aria-selected={i === k} className={`step ${i === k ? "on" : ""}`} onClick={() => setI(k)}><span>{k + 1}</span>{n}</button>)}</div>
    <Card className="pink"><h2 style={{ wordBreak: "normal" }}>{i + 1}. {STAGES[i][0]}</h2><p>{STAGES[i][1]}</p></Card>
    <h3>Verdicts</h3>
    <Card className="small">VERIFIED, PARTIAL, UNVERIFIED, SUSPICIOUS and MISMATCH. A missing registry entry is UNVERIFIED, never automatically fraud. An intact signature is not proof the signer is trusted. Open any result in the app for evidence, why it matters and a next step.</Card>
  </>);
}

function Arch() {
  return (<>
    <h3>Architecture (reflects the actual codebase)</h3>
    <div className="legend" style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>{Object.keys(NC).map((k) => <span key={k} style={{ color: NC[k] }}><i style={{ background: "currentColor" }} /> {NL[k]}</span>)}</div>
    <ol className="arch">{NODES.map(([t, s, d]) => <li key={t} style={{ "--c": NC[s] }}><b>{t}</b><span className="small muted">{NL[s]} · {d}</span></li>)}</ol>
    <p className="note-box">The submission deck mentions Node/Express, MongoDB, PaddleOCR, Redis, Kubernetes and government API integrations. None of these are in the current code, so they are not shown as implemented.</p>
  </>);
}

function Applicants() {
  const J = ["Prepare documents", "Submit for verification", "Review findings", "Correct issues", "Track outcome"];
  return (<>
    <h3>Applicant journey</h3>
    <div className="steps">{J.map((t, k) => <div key={t} className="step on"><span>{k + 1}</span>{t}</div>)}</div>
    <Card><ul className="feat">
      <li>Spot missing or inconsistent details earlier, with a next step for each finding.</li>
      <li>Check a reference number against configured issuer records without uploading anything.</li>
      <li>Understand outcomes in plain language and download a PDF report.</li>
      <li>Keep searchable history and share an expiring, revocable verdict link.</li>
    </ul><p className="small muted">SHASTRA does not independently verify every academic document and gives no official admissions approval.</p></Card>
  </>);
}

function Deploy() {
  return (<div className="grid g2">
    <Card><h3 style={{ marginTop: 0 }}>Current deployment</h3><p>Web application using hosted Supabase authentication, PostgreSQL and private storage with a FastAPI backend. It is <b>not</b> an offline product.</p></Card>
    <Card className="pink"><h3 style={{ marginTop: 0 }}>Future institutional deployment (PLANNED)</h3><p>Locally hosted version for data control or limited connectivity. Not built or tested.</p>
      <ul className="small">{["Local authentication", "Local database and private document storage", "Locally available verification components", "Secure access inside the institutional network", "Synchronisation and conflict handling on reconnect", "Local audit logs and backup procedures"].map((t) => <li key={t}>{t}</li>)}</ul></Card>
  </div>);
}

const num = (v) => (v === "" ? null : Number(v));
function Economics() {
  const [f, setF] = useState({ volume: "", minutes: "", rate: "", saved: "", monthly: "", initial: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const v = Object.fromEntries(Object.entries(f).map(([k, x]) => [k, num(x)]));
  const ready = v.volume > 0 && v.minutes > 0 && v.rate > 0 && v.saved >= 0 && v.saved <= 100 && v.monthly >= 0 && v.initial >= 0 && f.saved !== "" && f.monthly !== "" && f.initial !== "";
  const gross = ready ? (v.volume * v.minutes / 60) * v.rate * (v.saved / 100) : null, net = ready ? gross - v.monthly : null;
  const inr = (n) => `₹${Math.round(n).toLocaleString("en-IN")}`;
  const L = [["volume", "Monthly application volume"], ["minutes", "Average manual verification time (minutes)"], ["rate", "Staff cost per hour (₹)"], ["saved", "Estimated manual effort saved (%)"], ["monthly", "Monthly hosting and maintenance (₹)"], ["initial", "Initial implementation cost (₹)"]];
  return (<>
    <p>Open-source components lower software-licensing cost, but implementation, hosting, security, storage, maintenance and support still cost money.</p>
    <div className="grid g2">{[["Small institutions", "Affordable subscription or hosted plan."], ["Medium and large institutions", "Annual institutional licence with configurable rules, reporting and admin workflows."], ["Government departments / large organisations", "Tailored deployment, integration, training and maintenance contracts."]].map(([t, d]) => <Card key={t}><b>{t}</b><p className="small" style={{ marginBottom: 0 }}>{d}</p></Card>)}</div>
    <p className="small muted">These are proposed business models, not existing customers or confirmed revenue.</p>
    <h3>Cost-estimation calculator</h3>
    <Card><div className="grid g2">{L.map(([k, l]) => <label key={k}>{l}<input type="number" min="0" inputMode="decimal" value={f[k]} onChange={set(k)} /></label>)}</div>
      {!ready ? <p className="notice" style={{ marginTop: "1rem" }}>Enter all six assumptions to see an estimate. Nothing is pre-filled.</p>
        : <div className="grid g4" style={{ marginTop: "1rem" }}>
          <Card><div className="small muted">Gross monthly saving</div><b className="mono">{inr(gross)}</b></Card>
          <Card><div className="small muted">Net monthly saving</div><b className="mono">{inr(net)}</b></Card>
          <Card><div className="small muted">Payback</div><b className="mono">{net > 0 ? `${(v.initial / net).toFixed(1)} months` : "No payback at these assumptions"}</b></Card></div>}
      <p className="small" style={{ color: "#ffe9a3", marginBottom: 0 }}>Estimates are illustrative and must be validated using institutional pilot data.</p></Card>
    <h3>Potential revenue streams</h3>
    <Card><ul className="feat">{["Institutional subscriptions", "Deployment and configuration", "Custom compliance-rule development", "Training and onboarding", "Maintenance and support"].map((t) => <li key={t}>{t}</li>)}</ul></Card>
  </>);
}

function Trust() {
  return (<div className="grid g2">
    <Card><h3 style={{ marginTop: 0 }}>Implemented controls</h3><ul className="feat">{["Role-based access enforced on the server", "Private document storage (signed URLs, 60 s)", "Supabase authentication; admins need a confirmed e-mail", "Share links: unguessable token, expiring, revocable, identity-free snapshot", "Audit log of administrative and review actions", "CSV exports neutralise spreadsheet-formula injection", "Upload and lookup rate limits", "Human review workflow with internal notes"].map((t) => <li key={t}>{t}</li>)}</ul></Card>
    <Card className="pink"><h3 style={{ marginTop: 0 }}>Limitations</h3><ul className="feat">{["Poor scans reduce extraction accuracy", "Authenticity signals give false positives and negatives", "Registry coverage depends on issuer-uploaded records", "Regulatory rules need ongoing maintenance", "Sensitive documents need retention and access policies", "Not end-to-end encrypted, not certified, not offline, no live government-database link"].map((t) => <li key={t}>{t}</li>)}</ul></Card>
  </div>);
}

function Judges() {
  const rows = [
    ["Problem", "Manual validation of applications is slow, inconsistent and hard to audit (SIH26261)."],
    ["Solution", "One workflow: extraction, registry match, authenticity signals, cross-document checks, evidence-based verdict, human review."],
    ["Innovation", "Explainable findings, configurable registry, duplicate vs conflict separation, human-in-the-loop with audit trail."],
    ["Feasibility", "Runs on open-source Python libraries and Supabase today; classical forensics, not black-box AI."],
    ["Risks and mitigation", "Poor scans → OCR confidence flags; false positives → human review; privacy → access control and private storage."],
    ["Impact", "Measured only via the admin impact baseline (Duplicates tab). No result is claimed until real pilot data exists."],
    ["Roadmap", "Trusted certificate roots, multilingual OCR, SQL analytics, on-premises deployment, measured processing time."],
  ];
  return (<>
    <p className="note-box">Guided demo: sign in, upload a letter you are allowed to use, open the result, check the Duplicates tab and download the PDF. Any demo letters should be labelled as sample data and kept apart from real institutional records.</p>
    <Card className="scroll-x"><table><tbody>{rows.map(([k, t]) => <tr key={k}><td><b>{k}</b></td><td>{t}</td></tr>)}</tbody></table></Card>
  </>);
}
