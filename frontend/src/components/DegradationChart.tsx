import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useDegradation } from "../hooks/useDegradation";
import type { Compound, DegradationCurve } from "../api/types";

const SELECTABLE_COMPOUNDS: Compound[] = ["SOFT", "MEDIUM", "HARD"];

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#ef4444",
  MEDIUM: "#eab308",
  HARD: "#94a3b8",
  INTER: "#22c55e",
  WET: "#3b82f6",
};

interface Props {
  circuit?: string;
}

interface ChartPoint {
  tyre_age: number;
  fitted: number;
  actual?: number;
}

function buildChartData(curve: DegradationCurve): ChartPoint[] {
  const { a, b, c } = curve.coefficients;
  const actualsByAge = new Map<number, number[]>();
  for (const sp of curve.sample_points ?? []) {
    const bucket = actualsByAge.get(sp.tyre_age) ?? [];
    bucket.push(sp.lap_time_ms);
    actualsByAge.set(sp.tyre_age, bucket);
  }
  return Array.from({ length: 41 }, (_, t) => {
    const fitted = Math.round(a + b * t + c * t * t);
    const actuals = actualsByAge.get(t);
    const actual = actuals
      ? Math.round(actuals.reduce((s, v) => s + v, 0) / actuals.length)
      : undefined;
    return { tyre_age: t, fitted, actual };
  });
}

function msToLapTime(ms: number): string {
  const totalSec = ms / 1000;
  const min = Math.floor(totalSec / 60);
  const sec = (totalSec % 60).toFixed(1).padStart(4, "0");
  return `${min}:${sec}`;
}

function msToSecTick(ms: number): string {
  return `${(ms / 1000).toFixed(0)}s`;
}

export function DegradationChart({ circuit = "monaco" }: Props) {
  const [compound, setCompound] = useState<Compound>("MEDIUM");
  const { data, isLoading, isError } = useDegradation(circuit, compound);

  const chartData = useMemo(
    () => (data ? buildChartData(data) : []),
    [data],
  );

  const hasActuals =
    (data?.sample_points?.length ?? 0) > 0;
  const color = COMPOUND_COLORS[compound] ?? "#94a3b8";

  return (
    <section
      aria-label="Tyre degradation chart"
      className="panel flex flex-col overflow-hidden"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="label-caps">Tyre Degradation</span>
          {data?.r_squared != null && (
            <span className="text-[10px] font-mono text-pitwall-muted">
              R²={data.r_squared.toFixed(2)} n={data.n_samples}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {SELECTABLE_COMPOUNDS.map((c) => (
            <button
              key={c}
              onClick={() => setCompound(c)}
              className={[
                "h-5 px-2 rounded text-[9px] font-bold border transition-colors",
                compound === c
                  ? "border-transparent text-pitwall-bg"
                  : "border-pitwall-border text-pitwall-muted hover:text-pitwall-text",
              ].join(" ")}
              style={compound === c ? { backgroundColor: COMPOUND_COLORS[c] } : {}}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="px-2 py-3">
        {isLoading && (
          <div className="h-40 flex items-center justify-center">
            <span className="text-pitwall-muted text-xs">Loading…</span>
          </div>
        )}

        {isError && (
          <div
            className="h-40 flex items-center justify-center"
            data-testid="degradation-error"
          >
            <span className="text-pitwall-muted text-xs text-center">
              No degradation data for {circuit} / {compound} — run{" "}
              <code className="font-mono text-pitwall-text/70">make fit-degradation</code>
            </span>
          </div>
        )}

        {!isLoading && !isError && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart
              data={chartData}
              margin={{ top: 4, right: 8, bottom: 16, left: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
              <XAxis
                dataKey="tyre_age"
                type="number"
                domain={[0, 40]}
                tickCount={9}
                tick={{ fontSize: 9, fill: "#6b7280" }}
                label={{
                  value: "Tyre age (laps)",
                  position: "insideBottom",
                  offset: -8,
                  fontSize: 9,
                  fill: "#6b7280",
                }}
              />
              <YAxis
                tickFormatter={msToSecTick}
                tick={{ fontSize: 9, fill: "#6b7280" }}
                width={36}
                domain={["auto", "auto"]}
              />
              <Tooltip
                formatter={(value: unknown, name: string) => [
                  msToLapTime(value as number),
                  name === "fitted" ? "Model" : "Actual (avg)",
                ]}
                labelFormatter={(label) => `Tyre age: ${label} laps`}
                contentStyle={{
                  backgroundColor: "#141720",
                  border: "1px solid #252836",
                  borderRadius: 4,
                  fontSize: 11,
                }}
                labelStyle={{ color: "#9ca3af" }}
              />
              <Line
                type="monotone"
                dataKey="fitted"
                stroke={color}
                strokeWidth={2}
                dot={false}
                name="fitted"
              />
              {hasActuals && (
                <Line
                  dataKey="actual"
                  stroke={color}
                  strokeWidth={0.5}
                  strokeOpacity={0.15}
                  dot={{ r: 2.5, fill: color, strokeWidth: 0 }}
                  activeDot={{ r: 4 }}
                  name="actual"
                  connectNulls={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
