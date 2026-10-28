import { useCallback, useEffect, useState } from "react";
import { downloadFile, getJSON, send } from "../api";
import Result from "./Result.jsx";
import { Lookup, ShareModal } from "./features.jsx";
import { Analytics, Err, Reports, Tabs } from "./shared.jsx";
import Duplicates from "./Duplicates.jsx";
import { Card, Tilt, VerdictBadge } from "./ui.jsx";

const FILTERS = ["all", "flagged", "VERIFIED", "PARTIAL", "UNVERIFIED", "SUSPICIOUS", "MISMATCH"];
const Q_ICON = { queued: "·", scanning: "…", done: "✔", failed: "✖" };

export default function UserPanel() {
  const [tab, setTab] = useState("scan");
  const [docs, setDocs] = useState([]), [stats, setStats] = useState(null), [pub, setPub] = useState([]), [tick, setTick] = useState(0);
  const [current, setCurrent] = useState(null), [files, setFiles] = useState([]), [queue, setQueue] = useState([]), [busy, setBusy] = useState(false), [over, setOver] = useState(false), [error, setError] = useState("");
  const [q, setQ] = useState(""), [verdict, setVerdict] = useState("all"), [sharing, setSharing] = useState(false);

  const refresh = useCallback(async () => {
    try { const [s, p] = await Promise.all([getJSON("/api/stats"), getJSON("/api/published")]); setStats(s); setPub(p); setTick((t) => t + 1); }
    catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  // history list: server-side search + verdict filter, debounced while typing
  useEffect(() => {
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ ...(q.trim() && { q: q.trim() }), ...(verdict !== "all" && { verdict }) });
      getJSON(`/api/documents?${qs}`).then(setDocs).catch((e) => setError(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [q, verdict, tick]);

  const run = (fn) => async (...a) => { setError(""); try { return await fn(...a); } catch (e) { setError(e.message); } };
  const open = run(async (id) => { setCurrent(await getJSON(`/api/documents/${id}`)); setTab("scan"); });

  // batch upload: files are analysed one after another so the rate limiter and the server are never flooded
  const upload = async (e) => {
    e.preventDefault(); if (!files.length || busy) return;
    setBusy(true); setError("");
    const items = files.map((f) => ({ name: f.name, status: "queued" }));
    setQueue(items); let last = null;
    for (let i = 0; i < files.length; i++) {
      items[i] = { ...items[i], status: "scanning" }; setQueue([...items]);
      try { const body = new FormData(); body.append("file", files[i]); last = await getJSON("/api/analyze", { method: "POST", body }); items[i] = { ...items[i], status: "done", id: last.id, verdict: last.verification_status }; }
      catch (x) { items[i] = { ...items[i], status: "failed", error: x.message }; }
      setQueue([...items]);
    }
    if (last) setCurrent(last);
    setFiles([]); setBusy(false); refresh();
  };
  const remove = run(async (id) => { if (!confirm("Delete this document and its analysis permanently?")) return; await send("DELETE", `/api/documents/${id}`); setCurrent(null); refresh(); });
  const reverify = run(async (id) => { await send("POST", `/api/documents/${id}/reverify`); setCurrent(await getJSON(`/api/documents/${id}`)); refresh(); });
  const original = run(async (id) => window.open((await getJSON(`/api/documents/${id}/file-url`)).url, "_blank", "noopener"));
  const drop = (e) => { e.preventDefault(); setOver(false); setFiles([...e.dataTransfer.files].slice(0, 20)); };

  return (
    <>
      <Tabs value={tab} onChange={setTab} tabs={[["scan", "Scan & verify"], ["lookup", "Reference lookup"], ["analytics", "My analytics"], ["duplicates", "Duplicates"], ["published", `Published reports (${pub.length})`]]} />
      <main className="page">
        <Err msg={error} />
        {tab === "lookup" && <Lookup />}
        {tab === "duplicates" && <Duplicates scope="user" />}
        {tab === "analytics" && <Analytics s={stats} />}
        {tab === "published" && <Reports rows={pub} />}
        {tab === "scan" && (
          <div className="split">
            <aside>
              <Tilt>
                <h3 style={{ marginTop: 0 }}>Upload letters</h3>
                <form onSubmit={upload}>
                  <div className={`drop ${over ? "over" : ""} ${busy ? "busy" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}>
                    <input type="file" multiple aria-label="Choose letters" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={(e) => setFiles([...e.target.files].slice(0, 20))} />
                    <div className="mono">{files.length === 0 ? "DROP FILES OR CLICK" : files.length === 1 ? files[0].name : `${files.length} FILES SELECTED`}</div>
                    <div className="small muted">PDF · PNG · JPEG · 10 MB each · up to 20 at once</div>
                  </div>
                  <button style={{ marginTop: ".8rem", width: "100%" }} disabled={!files.length || busy}>{busy ? "Scanning… (first scan may take a minute)" : files.length > 1 ? `Analyse ${files.length} files` : "Analyse & verify"}</button>
                </form>
                {queue.length > 1 && <ul className="docs" style={{ maxHeight: "22vh" }} aria-label="Batch progress">
                  {queue.map((x, i) => <li key={i}><button className="link" disabled={!x.id} onClick={() => open(x.id)} title={x.error || x.name}>{Q_ICON[x.status]} {x.name}</button>
                    {x.verdict ? <VerdictBadge v={x.verdict} /> : <span className="small muted">{x.status === "failed" ? "failed" : x.status}</span>}</li>)}</ul>}
                {queue.some((x) => x.status === "failed") && <p className="small" style={{ color: "#ffb3c1" }}>{queue.filter((x) => x.status === "failed").map((x) => `${x.name}: ${x.error}`).join(" · ")}</p>}
              </Tilt>
              <Card style={{ marginTop: "1rem" }}>
                <div className="row between"><h3 style={{ margin: 0 }}>History</h3>
                  <button className="sm ghost" onClick={run(() => downloadFile("/api/documents/export.csv", "shastra-my-documents.csv"))} title="Download all your results as CSV">Export CSV</button></div>
                <input type="search" aria-label="Search history" placeholder="Search file, reference, institute…" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginTop: ".7rem" }} />
                <select aria-label="Filter by verdict" value={verdict} onChange={(e) => setVerdict(e.target.value)} style={{ marginTop: ".5rem" }}>{FILTERS.map((f) => <option key={f} value={f}>{f === "all" ? "All verdicts" : f}</option>)}</select>
                <ul className="docs">
                  {docs.length === 0 && <li className="muted small">{q || verdict !== "all" ? "No matches." : "No documents yet."}</li>}
                  {docs.map((d) => <li key={d.id} className={current?.id === d.id ? "active" : ""}><button className="link" onClick={() => open(d.id)}>{d.filename}</button><VerdictBadge v={d.verification_status || "UNVERIFIED"} /></li>)}
                </ul>
              </Card>
            </aside>
            <section>
              {current
                ? <Result doc={current} actions={<>
                    <button onClick={run(() => downloadFile(`/api/documents/${current.id}/report.pdf`, `shastra-${current.id.slice(0, 8)}.pdf`))}>PDF report</button>
                    <button className="pink" onClick={() => setSharing(true)} title="Create a revocable public link to the verdict">Share</button>
                    <button className="ghost" onClick={() => reverify(current.id)} title="Re-run against the latest issuer registry">Re-verify</button>
                    <button className="ghost" onClick={() => original(current.id)}>Original</button>
                    <button className="danger" onClick={() => remove(current.id)}>Delete</button></>} />
                : <Card><p className="mono muted">&gt; SELECT A DOCUMENT OR UPLOAD ONE TO BEGIN_</p></Card>}
              {sharing && current && <ShareModal doc={current} onClose={() => setSharing(false)} />}
            </section>
          </div>
        )}
      </main>
    </>
  );
}
