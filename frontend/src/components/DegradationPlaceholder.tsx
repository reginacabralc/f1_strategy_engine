// Placeholder for the tyre degradation Recharts chart — implemented in Day 6.

const COMPOUNDS = [
  { label: "SOFT", color: "#ef4444", dots: [85, 82, 79, 75, 71, 66, 60] },
  { label: "MEDIUM", color: "#eab308", dots: [84, 83, 82, 80, 78, 76, 74] },
  { label: "HARD", color: "#94a3b8", dots: [83, 83, 82, 82, 81, 80, 80] },
];

export function DegradationPlaceholder() {
  return (
    <section
      aria-label="Tyre degradation chart"
      className="panel flex flex-col overflow-hidden"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <span className="label-caps">Tyre Degradation</span>
        <div className="flex items-center gap-3">
          {COMPOUNDS.map((c) => (
            <span key={c.label} className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: c.color }}
              />
              <span className="text-[10px] text-pitwall-muted">{c.label}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Sparkline preview — dummy SVG shapes, not real data */}
      <div className="flex-1 flex items-center justify-center px-4 py-3 relative">
        <svg
          viewBox="0 0 280 80"
          className="w-full opacity-40"
          aria-hidden="true"
        >
          {/* Grid lines */}
          {[20, 40, 60].map((y) => (
            <line
              key={y}
              x1="0"
              y1={y}
              x2="280"
              y2={y}
              stroke="#1e2130"
              strokeWidth="1"
            />
          ))}
          {/* Curves */}
          {COMPOUNDS.map((c, ci) => {
            const xs = c.dots.map((_, i) => (i / (c.dots.length - 1)) * 280);
            const ys = c.dots.map((v) => ((100 - v) / 40) * 80);
            const d =
              `M ${xs[0]} ${ys[0]} ` +
              xs
                .slice(1)
                .map((x, i) => `L ${x} ${ys[i + 1]}`)
                .join(" ");
            return (
              <path
                key={ci}
                d={d}
                fill="none"
                stroke={c.color}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}
        </svg>

        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-[11px] text-pitwall-muted text-center bg-pitwall-surface/90 px-3 py-1.5 rounded border border-pitwall-border">
            Recharts chart — Day 6
          </p>
        </div>
      </div>
    </section>
  );
}
