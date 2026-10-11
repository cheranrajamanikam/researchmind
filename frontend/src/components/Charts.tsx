/** Small, dependency-free charts that use the design's chart classes and tokens. */

export interface Segment { value: number; color: string; label: string }

export function Donut({ segments, centre, caption }: { segments: Segment[]; centre: string; caption: string }) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  let acc = 0;
  const stops = total
    ? segments.map((s) => {
        const from = (acc / total) * 100;
        acc += s.value;
        return `${s.color} ${from}% ${(acc / total) * 100}%`;
      }).join(", ")
    : "var(--surface-muted) 0 100%";
  return (
    <div className="donut" style={{ background: `conic-gradient(${stops})` }} role="img"
      aria-label={`${caption}: ${segments.map((s) => `${s.value} ${s.label}`).join(", ")}`}>
      <div><strong>{centre}</strong><span>{caption}</span></div>
    </div>
  );
}

export function Ring({ value, caption, label }: { value: number | null; caption: string; label?: string }) {
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="accuracy-ring" style={{ background: `conic-gradient(var(--accent) ${pct}%, var(--surface-muted) 0)` }}
      role="img" aria-label={`${caption}: ${value === null ? "not measured yet" : `${pct.toFixed(1)}%`}`}>
      <strong>{label ?? (value === null ? "n/a" : `${pct.toFixed(1)}%`)}</strong>
      <span>{caption}</span>
    </div>
  );
}

export interface Series { name: string; tone: "teal" | "blue"; values: (number | null)[] }

/** Values are 0..1. Labels are shown under the x axis (e.g. run numbers). */
export function LineChart({ series, labels, ariaLabel }: { series: Series[]; labels: string[]; ariaLabel: string }) {
  const W = 700, H = 210, L = 45, R = 25, T = 20, B = 30;
  const n = Math.max(labels.length, 1);
  const x = (i: number) => (n === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (n - 1));
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel}>
        <g className="chart-grid">
          <path d={ticks.map((t) => `M${L} ${y(t)}H${W - R}`).join("")} />
        </g>
        {ticks.map((t) => <text key={t} className="chart-axis" x={L - 8} y={y(t) + 3} textAnchor="end">{Math.round(t * 100)}%</text>)}
        {labels.map((l, i) => <text key={`${l}-${i}`} className="chart-axis" x={x(i)} y={H - 8} textAnchor="middle">{l}</text>)}
        {series.map((s) => {
          const pts = s.values.map((v, i) => (v === null ? null : [x(i), y(v)] as const));
          const d = pts.reduce<string>((acc, p, i) => (p ? `${acc}${acc && pts[i - 1] ? "L" : "M"}${p[0]} ${p[1]}` : acc), "");
          return (
            <g key={s.name}>
              {d && <path className={`chart-line chart-line--${s.tone}`} d={d} />}
              {pts.map((p, i) => p && <circle key={i} className="chart-dot" cx={p[0]} cy={p[1]} r="4"><title>{`${s.name}: ${Math.round((s.values[i] ?? 0) * 100)}%`}</title></circle>)}
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">{series.map((s) => <span key={s.name}><i className={s.tone} />{s.name}</span>)}</div>
    </>
  );
}
