import { useCallback, useEffect, useState } from "react";
import { downloadFile, getJSON, send } from "../api";
import Result from "./Result.jsx";
import { ExpiryCard, ReviewPanel } from "./features.jsx";
import { Analytics, DocTable, Err, PublishModal, Reports, Tabs } from "./shared.jsx";
import Duplicates from "./Duplicates.jsx";
import { Card, COLORS, Stat, fmtDate } from "./ui.jsx";

const EMPTY = { reference_no: "", institute_name: "", academic_year: "", issue_date: "", valid_upto: "", permanent_id: "", courses: "", sha256: "", expected_watermark: "" };
const CSV_HINT = "reference_no,institute_name,academic_year,issue_date,valid_upto,permanent_id,courses,sha256,expected_watermark\nWestern/1-12345/2026/EOA,Sunrise Institute of Technology,2026-27,2026-07-01,2027-03-31,1-1234567,B.Tech;MBA,,AICTE ORIGINAL";

export default function OrgPanel({ me }) {
  const approved = me.org?.status === "approved";
  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState(null), [reg, setReg] = useState([]), [docs, setDocs] = useState([]), [pub, setPub] = useState([]);
  const [form, setForm] = useState(EMPTY), [editing, setEditing] = useState(null), [csv, setCsv] = useState(""), [current, setCurrent] = useState(null), [publishing, setPublishing] = useState(false);
  const [error, setError] = useState(""), [info, setInfo] = useState("");

  const refresh = useCallback(async () => {
    if (!approved) return;
    try { const [s, r, d, p] = await Promise.all([getJSON("/api/org/stats"), getJSON("/api/org/registry"), getJSON("/api/org/documents"), getJSON("/api/published")]); setStats(s); setReg(r); setDocs(d); setPub(p); }
    catch (e) { setError(e.message); }
  }, [approved]);
  useEffect(() => { refresh(); }, [refresh]);
  const run = (fn) => async (...a) => { setError(""); setInfo(""); try { await fn(...a); } catch (e) { setError(e.message); } };

  if (!approved) return (
    <main className="page"><Card className="pink"><h3 style={{ marginTop: 0 }}>Organization {me.org?.status || "not linked"}</h3>
      <p>Your organization <b>{me.org?.name}</b> must be approved by an administrator before you can manage a registry or review submissions.</p></Card></main>);

  const add = run(async (e) => {
    e.preventDefault();
    if (editing) { await send("PATCH", `/api/org/registry/${editing}`, form); setInfo("Record updated. Users can re-verify existing documents to pick up the change."); }
    else { await send("POST", "/api/org/registry", form); setInfo("Record added."); }
    setForm(EMPTY); setEditing(null); refresh();
  });
  const edit = (r) => { setForm({ ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, k === "courses" ? (r.courses || []).join("; ") : r[k] ?? ""])) }); setEditing(r.id); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const cancelEdit = () => { setForm(EMPTY); setEditing(null); };
  const importCsv = run(async () => { const r = await send("POST", "/api/org/registry/import", { csv }); setInfo(`Imported ${r.added} record(s).` + (r.errors.length ? ` Skipped: ${r.errors.map((x) => `line ${x.line} (${x.error})`).join(", ")}` : "")); setCsv(""); refresh(); });
  const setStatus = run(async (r) => { await send("PATCH", `/api/org/registry/${r.id}`, { status: r.status === "active" ? "revoked" : "active" }); refresh(); });
  const del = run(async (r) => { if (confirm(`Delete ${r.reference_no} from the registry?`)) { await send("DELETE", `/api/org/registry/${r.id}`); refresh(); } });
  const open = run(async (id) => { setCurrent(await getJSON(`/api/org/documents/${id}`)); setTab("submissions"); });
  const expSoon = new Set((stats?.registry.expiring_soon || []).map((x) => x.id));
  const f = (k) => ({ value: form[k], onChange: (e) => setForm({ ...form, [k]: e.target.value }) });

  return (
    <>
      <Tabs value={tab} onChange={setTab} tabs={[["overview", "Overview"], ["registry", `Registry (${reg.length})`], ["submissions", `Submissions (${docs.length})`], ["duplicates", "Duplicates"], ["published", "Published"]]} />
      <main className="page">
        <Err msg={error} />{info && <p className="notice">{info}</p>}
        {tab === "overview" && <div className="grid"><div className="grid g4"><Stat k="Registry records" v={stats?.registry.total} color={COLORS.amber} /><Stat k="Revoked" v={stats?.registry.revoked} color={COLORS.red} />
          <Stat k="Expiring soon" v={stats?.registry.expiring_soon.length} color={COLORS.orange} sub={`${stats?.registry.expired_active ?? 0} already lapsed`} /><Stat k="Under review" v={stats?.review.under_review} color={COLORS.violet} sub={`${stats?.review.flagged ?? 0} awaiting triage`} /></div>
          <ExpiryCard registry={stats?.registry} /><Analytics s={stats} /></div>}

        {tab === "registry" && (
          <div className="grid">
            <p className="note-box">The registry is the ground truth uploads are matched against. Add only letters your organization really issued. Optional <b>sha256</b> pins the exact file; <b>expected watermark</b> makes a missing watermark a finding.</p>
            <div className="grid g2">
              <Card><h3 style={{ marginTop: 0 }}>{editing ? "Edit record" : "Add record"}</h3>
                <form onSubmit={add}>
                  <label>Reference no *<input required placeholder="Western/1-12345/2026/EOA" {...f("reference_no")} /></label>
                  <label>Institute name *<input required {...f("institute_name")} /></label>
                  <div className="grid g2" style={{ gap: "0 1rem" }}>
                    <label>Academic year<input placeholder="2026-27" {...f("academic_year")} /></label><label>Permanent ID<input placeholder="1-1234567" {...f("permanent_id")} /></label>
                    <label>Issue date<input type="date" {...f("issue_date")} /></label><label>Valid up to<input type="date" {...f("valid_upto")} /></label>
                  </div>
                  <label>Approved programmes (separate with ;)<input placeholder="B.Tech; MBA" {...f("courses")} /></label>
                  <label>Expected watermark text<input placeholder="AICTE ORIGINAL" {...f("expected_watermark")} /></label>
                  <label>File SHA-256 (optional)<input pattern="[0-9a-fA-F]{64}" {...f("sha256")} /></label>
                  <div className="row"><button>{editing ? "Save changes" : "Add to registry"}</button>{editing && <button type="button" className="ghost" onClick={cancelEdit}>Cancel</button>}</div>
                </form></Card>
              <Card className="pink"><h3 style={{ marginTop: 0 }}>Bulk import CSV</h3>
                <textarea rows={9} className="mono" placeholder={CSV_HINT} value={csv} onChange={(e) => setCsv(e.target.value)} />
                <div className="row" style={{ marginTop: ".7rem" }}><button className="pink" disabled={!csv.trim()} onClick={importCsv}>Import</button>
                  <input type="file" accept=".csv,text/csv" aria-label="Load CSV file" style={{ width: "auto" }} onChange={async (e) => e.target.files[0] && setCsv(await e.target.files[0].text())} /></div>
                <p className="small muted">Max 500 rows. Duplicates and invalid rows are skipped and listed.</p></Card>
            </div>
            <div className="row between"><span className="muted small">{reg.length} record(s)</span><button className="sm ghost" onClick={run(() => downloadFile("/api/org/registry/export.csv", "shastra-registry.csv"))}>Export registry CSV</button></div>
            <Card className="scroll-x"><table><thead><tr><th>Reference</th><th>Institute</th><th>AY</th><th>Valid up to</th><th>Programmes</th><th>Status</th><th /></tr></thead>
              <tbody>{reg.map((r) => <tr key={r.id}><td className="mono">{r.reference_no}</td><td>{r.institute_name}</td><td>{r.academic_year}</td><td>{r.valid_upto}{expSoon.has(r.id) && <span className="badge" style={{ "--c": COLORS.orange, marginLeft: ".4rem" }}>EXPIRING</span>}</td><td className="small">{(r.courses || []).join(", ")}</td>
                <td><span className="badge" style={{ "--c": r.status === "active" ? COLORS.lime : COLORS.red }}>{r.status}</span></td>
                <td className="row"><button className="sm ghost" onClick={() => edit(r)}>Edit</button><button className="sm ghost" onClick={() => setStatus(r)}>{r.status === "active" ? "Revoke" : "Reinstate"}</button><button className="sm danger" onClick={() => del(r)}>Delete</button></td></tr>)}</tbody></table>
              {reg.length === 0 && <p className="muted">No records yet.</p>}</Card>
          </div>
        )}

        {tab === "submissions" && (current
          ? <><button className="ghost sm" onClick={() => setCurrent(null)} style={{ marginBottom: "1rem" }}>← All submissions</button>
              <Result doc={current} actions={<button className="pink" onClick={() => setPublishing(true)}>Publish report</button>} />
              <div style={{ marginTop: "1rem" }}><ReviewPanel doc={current} base="/api/org/documents" onChanged={refresh} /></div>
              {publishing && <PublishModal defaultTitle={`Verification report ${current.reference_no || ""}`} onClose={() => setPublishing(false)}
                onSubmit={async (b) => { await send("POST", `/api/org/documents/${current.id}/publish`, b); setInfo("Report published."); refresh(); }} />}</>
          : <><div className="row between"><p className="muted small">Documents users uploaded that match one of your registry records. Uploader identity is hidden.</p>
              <button className="sm ghost" onClick={run(() => downloadFile("/api/org/documents/export.csv", "shastra-submissions.csv"))}>Export CSV</button></div><DocTable rows={docs} onOpen={open} /></>)}

        {tab === "duplicates" && <Duplicates scope="org" />}
        {tab === "published" && <Reports rows={pub.filter((r) => r.org_id === me.org.id)} />}
      </main>
    </>
  );
}
