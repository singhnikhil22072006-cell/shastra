import { guideFor, VERDICT_PLAIN } from "./guide.js";
import { Card, Donut, Gauge, RiskBadge, SEV_COLOR, VERDICT_COLOR, VerdictBadge, fmtDate } from "./ui.jsx";

const ICON = { pass: "✔", warn: "▲", fail: "✖", na: "·" };

export default function Result({ doc, actions }) {
  const r = doc.result, v = r.verification, rm = r.registry_match, wm = r.watermark, sg = r.signatures;
  const vc = VERDICT_COLOR[v.status];
  const sevCount = r.findings.reduce((a, f) => ({ ...a, [f.severity]: (a[f.severity] || 0) + 1 }), {});
  return (
    <article className="grid">
      <header className="row between">
        <div>
          <h2>{doc.filename || r.file.name}</h2>
          <p className="muted small mono">SHA-256 {r.file.sha256.slice(0, 24)}… · {r.file.pages} page(s) · {fmtDate(r.analyzed_at)}</p>
        </div>
        <div className="row">{actions}</div>
      </header>

      <Card className="hero-v" style={{ "--c": vc }}>
        <div>
          <div className="muted small mono">&gt; VERIFICATION VERDICT</div>
          <div className="big">{v.status}</div>
          <p style={{ margin: ".4rem 0 .4rem" }}>{v.summary}</p>
          <p className="small muted" style={{ margin: "0 0 .6rem" }}><b>In plain language:</b> {VERDICT_PLAIN[v.status]}</p>
          <div className="row"><span className="small muted">Review priority</span><RiskBadge v={r.risk.level} /><span className="small muted mono">score {r.risk.score}/100</span></div>
        </div>
        <Gauge value={v.trust_score} color={vc} />
      </Card>
      <p className="note-box">{r.official_verification.reason} A VERIFIED label requires the issuer's record to match <em>and</em> an independent feature (file fingerprint, signature, watermark or QR) to corroborate it. No label is a legal determination.</p>

      <section>
        <h3>Authenticity signals</h3>
        <div className="signals">
          {v.signals.map((s) => (
            <div key={s.id} className={`signal s-${s.state}`}><b>{s.label}<span className="st">{ICON[s.state]} {s.state}</span></b><p>{s.detail}</p></div>
          ))}
        </div>
      </section>

      {rm.matched && rm.diffs.length > 0 && (
        <section>
          <h3>Mismatches vs issuer record</h3>
          <Card className="pink scroll-x"><table><thead><tr><th>Field</th><th>This document</th><th>Issuer registry</th><th>Severity</th></tr></thead>
            <tbody>{rm.diffs.map((d, i) => <tr key={i}><td>{d.field}</td><td className="mono">{d.document}</td><td className="mono">{d.registry}</td><td><span className="badge" style={{ "--c": SEV_COLOR[d.severity] }}>{d.severity}</span></td></tr>)}</tbody></table></Card>
        </section>
      )}

      <div className="grid g2">
        <Card>
          <h4>Watermark</h4>
          <p className="small" style={{ marginBottom: 0 }}>{wm.detected ? `Detected (${wm.kinds.join(", ")}).` : "None detected."}{wm.texts.length > 0 && <> Text read: <span className="mono">{wm.texts.join(" | ")}</span></>}
            {wm.expected && <> Issuer expects <span className="mono">"{wm.expected}"</span>: <b style={{ color: wm.expected_found ? "var(--lime)" : "var(--red)" }}>{wm.expected_found ? "found" : "not found"}</b>.</>}</p>
        </Card>
        <Card>
          <h4>Digital signature</h4>
          <p className="small" style={{ marginBottom: 0 }}>{!sg || !sg.count ? "No signature in this file." : <>{sg.count} signature(s). Covers whole file: <b>{String(sg.covers_whole_file)}</b>. Crypto check: {sg.crypto}. {sg.signatures.map((s, i) => <span key={i} className="mono"><br />{s.signer || "unknown signer"} · intact {String(s.intact)} · trusted {String(s.trusted)}</span>)}<br /><span className="muted">Intact means unchanged since signing; it does not prove the signer is trustworthy unless "trusted" is true.</span></>}</p>
        </Card>
      </div>

      <section>
        <h3>Findings ({r.findings.length})</h3>
        <div className="grid g2" style={{ alignItems: "start" }}>
          <ul className="findings" style={{ gridColumn: "span 1" }}>
            {r.findings.length === 0 && <li>No rule-based findings triggered. This is not proof of authenticity.</li>}
            {r.findings.map((f, i) => { const g = guideFor(f.id); return (
              <li key={i} className={`sev-${f.severity}`}>
                <strong>{f.title}</strong> <span className="small muted">({f.severity} · {f.category})</span>
                <p><b>Detected:</b> {f.detail}</p>
                <p><b>Why it matters:</b> {g.why}</p>
                {f.evidence && <p className="evidence"><b>Evidence:</b> {f.evidence}</p>}
                <p><b>Next step:</b> {g.next}</p>
              </li>); })}
          </ul>
          <Card><h4 style={{ marginBottom: ".6rem" }}>By severity</h4><Donut data={sevCount} colorMap={SEV_COLOR} /></Card>
        </div>
      </section>

      <section>
        <h3>Extracted fields</h3>
        <Card className="scroll-x"><table><thead><tr><th>Field</th><th>Value</th><th>Page / method</th><th>Source text</th></tr></thead>
          <tbody>{Object.entries(r.fields).map(([k, f]) => (
            <tr key={k}><td>{k}</td><td className="mono">{f ? f.value : <em className="muted">not found</em>}</td><td className="small">{f ? `${f.page} / ${f.method}` : "-"}</td><td className="small muted">{f ? f.evidence : "-"}</td></tr>))}</tbody></table>
          {r.courses.length > 0 && <><h4 style={{ margin: "1rem 0 .4rem" }}>Programme lines</h4><ul className="small">{r.courses.map((c, i) => <li key={i}>{c.text}</li>)}</ul></>}
        </Card>
      </section>

      <p className="small muted mono">{r.extraction.map((e) => `p${e.page}:${e.method}${e.ocr_confidence != null ? `(${e.ocr_confidence})` : ""}`).join("  ")} · {Object.values(r.engine).join(" · ")}</p>
    </article>
  );
}
