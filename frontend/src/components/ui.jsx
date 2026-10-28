import { useEffect, useRef, useState } from "react";

export const COLORS = { cyan: "#00f0ff", pink: "#ff2bd6", violet: "#8a5cff", lime: "#39ff88", amber: "#ffd23f", red: "#ff3860", orange: "#ff8a3d", slate: "#64748b" };
export const VERDICT_COLOR = { VERIFIED: COLORS.lime, PARTIAL: COLORS.amber, UNVERIFIED: COLORS.slate, SUSPICIOUS: COLORS.orange, MISMATCH: COLORS.red };
export const RISK_COLOR = { LOW: COLORS.lime, MEDIUM: COLORS.amber, HIGH: COLORS.red };
export const SEV_COLOR = { high: COLORS.red, medium: COLORS.orange, low: COLORS.amber, info: COLORS.slate };
const CAT_COLORS = [COLORS.cyan, COLORS.pink, COLORS.violet, COLORS.amber, COLORS.lime, COLORS.orange, COLORS.red];

/** Card that tilts toward the pointer in 3D. */
export function Tilt({ children, className = "", max = 7, ...rest }) {
  const ref = useRef(null);
  const move = (e) => {
    const r = ref.current.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
    ref.current.style.transform = `perspective(900px) rotateY(${x * max}deg) rotateX(${-y * max}deg)`;
  };
  const leave = () => { ref.current.style.transform = ""; };
  return <div ref={ref} className={`card tilt ${className}`} onMouseMove={move} onMouseLeave={leave} {...rest}>{children}</div>;
}

export function Card({ children, className = "", ...rest }) { return <div className={`card ${className}`} {...rest}>{children}</div>; }

export function Stat({ k, v, color = COLORS.cyan, sub }) {
  return <Tilt className="stat" style={{ "--c": color }} max={9}><div className="v">{v ?? "—"}</div><div className="k">{k}</div>{sub && <div className="small muted">{sub}</div>}</Tilt>;
}

export function VerdictBadge({ v }) { return <span className={`badge v-${v}`}>{v}</span>; }
export function RiskBadge({ v }) { return <span className={`badge r-${v}`}>{v}</span>; }

function useMounted() { const [m, set] = useState(false); useEffect(() => { const t = requestAnimationFrame(() => set(true)); return () => cancelAnimationFrame(t); }, []); return m; }

/** Semi-circular gauge 0-100. */
export function Gauge({ value = 0, label = "TRUST", color = COLORS.cyan, size = 190 }) {
  const m = useMounted(), R = 70, C = Math.PI * R, off = C * (1 - (m ? value : 0) / 100);
  return (
    <svg className="chart" width={size} height={size * 0.62} viewBox="0 0 180 112" role="img" aria-label={`${label} ${value} out of 100`}>
      <defs><filter id="glow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
      <path d="M20 95 A70 70 0 0 1 160 95" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="12" strokeLinecap="round" />
      <path className="arc" d="M20 95 A70 70 0 0 1 160 95" fill="none" stroke={color} strokeWidth="12" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={off} filter="url(#glow)" />
      <text x="90" y="82" textAnchor="middle" style={{ fontFamily: "Orbitron", fontSize: 30, fontWeight: 900, fill: "#fff" }}>{value}</text>
      <text x="90" y="104" textAnchor="middle" style={{ letterSpacing: 3 }}>{label}</text>
    </svg>
  );
}

/** Donut + legend. data = { label: number }. colorMap optional. */
export function Donut({ data = {}, colorMap = {}, size = 170, center }) {
  const m = useMounted(), entries = Object.entries(data).filter(([, v]) => v > 0), total = entries.reduce((a, [, v]) => a + v, 0);
  const R = 56, C = 2 * Math.PI * R; let acc = 0;
  return (
    <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap" }}>
      <svg className="chart" width={size} height={size} viewBox="0 0 150 150" role="img" aria-label="Distribution chart">
        <circle cx="75" cy="75" r={R} fill="none" stroke="rgba(255,255,255,.07)" strokeWidth="16" />
        {entries.map(([k, v], i) => {
          const len = (v / total) * C, col = colorMap[k] || CAT_COLORS[i % CAT_COLORS.length];
          const el = <circle key={k} className="arc" cx="75" cy="75" r={R} fill="none" stroke={col} strokeWidth="16" strokeDasharray={`${m ? Math.max(len - 2, 0) : 0} ${C}`} strokeDashoffset={-acc} transform="rotate(-90 75 75)" style={{ filter: `drop-shadow(0 0 4px ${col})`, transition: "stroke-dasharray 1.1s cubic-bezier(.2,.8,.2,1)" }} />;
          acc += len; return el;
        })}
        <text x="75" y="80" textAnchor="middle" style={{ fontFamily: "Orbitron", fontSize: 22, fontWeight: 900, fill: "#fff" }}>{center ?? total}</text>
      </svg>
      <div className="legend" style={{ flexDirection: "column" }}>
        {entries.length === 0 && <span className="muted">No data yet</span>}
        {entries.map(([k, v], i) => <span key={k} style={{ color: colorMap[k] || CAT_COLORS[i % CAT_COLORS.length] }}><i style={{ background: "currentColor" }} /><span style={{ color: "var(--ink)" }}>{k.replace(/_/g, " ")}</span> <b>{v}</b></span>)}
      </div>
    </div>
  );
}

/** Horizontal bars. data = { label: number } */
export function HBars({ data = {}, colorMap = {}, color = COLORS.cyan }) {
  const m = useMounted(), entries = Object.entries(data).sort((a, b) => b[1] - a[1]), max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return <p className="muted">No data yet</p>;
  return <div>{entries.map(([k, v], i) => { const col = colorMap[k] || (colorMap === null ? color : CAT_COLORS[i % CAT_COLORS.length]);
    return <div className="hbar" key={k}><span>{k.replace(/_/g, " ")}</span><div className="track"><div className="fill bar" style={{ width: m ? `${(v / max) * 100}%` : 0, background: col, color: col }} /></div><b className="mono">{v}</b></div>; })}</div>;
}

/** Area/line timeline. points = [{date, documents, flagged}] */
export function Timeline({ points = [], height = 170 }) {
  const W = 560, H = height, pad = 26, n = points.length;
  const max = Math.max(3, ...points.map((p) => p.documents));
  const x = (i) => pad + (i * (W - pad * 2)) / Math.max(n - 1, 1), y = (v) => H - pad - (v / max) * (H - pad * 2);
  const path = (k) => points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p[k]).toFixed(1)}`).join(" ");
  const area = `${path("documents")} L${x(n - 1)} ${H - pad} L${x(0)} ${H - pad} Z`;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Documents analysed over time">
      <defs><linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={COLORS.cyan} stopOpacity=".5" /><stop offset="1" stopColor={COLORS.cyan} stopOpacity="0" /></linearGradient></defs>
      {[0, 0.5, 1].map((f) => <g key={f}><line x1={pad} x2={W - pad} y1={y(max * f)} y2={y(max * f)} stroke="rgba(0,240,255,.12)" /><text x="2" y={y(max * f) + 3}>{Math.round(max * f)}</text></g>)}
      <path d={area} fill="url(#ar)" /><path d={path("documents")} fill="none" stroke={COLORS.cyan} strokeWidth="2" style={{ filter: "drop-shadow(0 0 5px #00f0ff)" }} />
      <path d={path("flagged")} fill="none" stroke={COLORS.pink} strokeWidth="2" strokeDasharray="5 3" style={{ filter: "drop-shadow(0 0 5px #ff2bd6)" }} />
      {points.map((p, i) => i % 3 === 0 && <text key={p.date} x={x(i)} y={H - 6} textAnchor="middle">{p.date.slice(5)}</text>)}
      <g transform={`translate(${W - 150} 8)`}><rect width="8" height="8" fill={COLORS.cyan} /><text x="13" y="8">analysed</text><rect x="70" width="8" height="8" fill={COLORS.pink} /><text x="83" y="8">flagged</text></g>
    </svg>
  );
}

export function Modal({ title, onClose, children }) {
  useEffect(() => { const k = (e) => e.key === "Escape" && onClose(); addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [onClose]);
  return <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()} role="dialog" aria-modal="true" aria-label={title}><div className="card pink"><h3 style={{ marginTop: 0 }}>{title}</h3>{children}</div></div>;
}

export const fmtDate = (s) => (s ? new Date(s).toLocaleString() : "-");
