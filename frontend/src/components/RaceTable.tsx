import type { DriverState } from "../api/types";
import mockRaceOrder from "../data/mockRaceOrder.json";

const MOCK_DRIVERS = mockRaceOrder as DriverState[];

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "text-red-400",
  MEDIUM: "text-yellow-400",
  HARD: "text-slate-300",
  INTER: "text-green-400",
  WET: "text-blue-400",
};

function ScoreBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-pitwall-muted">—</span>;
  const pct = Math.round(score * 100);
  const color =
    score >= 0.6
      ? "bg-red-500"
      : score >= 0.35
        ? "bg-yellow-500"
        : "bg-green-600";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-pitwall-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-pitwall-muted">{pct}%</span>
    </div>
  );
}

function msToGap(ms: number | null): string {
  if (ms === null || ms === 0) return "—";
  return `+${(ms / 1000).toFixed(3)}s`;
}

interface Props {
  drivers?: DriverState[];
}

export function RaceTable({ drivers = MOCK_DRIVERS }: Props) {
  return (
    <div
      className="overflow-x-auto rounded-lg border border-pitwall-border"
      data-testid="race-table-scroll"
    >
      <table className="min-w-[760px] w-full text-sm">
        <thead>
          <tr className="bg-pitwall-surface text-pitwall-muted uppercase text-xs tracking-wider">
            <th className="px-4 py-3 text-left w-8">P</th>
            <th className="px-4 py-3 text-left">Driver</th>
            <th className="px-4 py-3 text-left">Team</th>
            <th className="px-4 py-3 text-right">Gap</th>
            <th className="px-4 py-3 text-left">Compound</th>
            <th className="px-4 py-3 text-right">Tyre Age</th>
            <th className="px-4 py-3 text-left">Score</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-pitwall-border">
          {drivers.map((d) => (
            <tr
              key={d.driver_code}
              className="hover:bg-pitwall-surface transition-colors"
            >
              <td className="px-4 py-3 font-mono text-pitwall-muted">
                {d.position}
              </td>
              <td className="px-4 py-3 font-semibold">{d.driver_code}</td>
              <td className="px-4 py-3 text-pitwall-muted">
                {d.team_code ?? "—"}
              </td>
              <td className="px-4 py-3 text-right font-mono tabular-nums text-pitwall-muted">
                {msToGap(d.gap_to_leader_ms)}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`font-semibold ${COMPOUND_COLORS[d.compound] ?? ""}`}
                >
                  {d.compound}
                </span>
              </td>
              <td className="px-4 py-3 text-right font-mono tabular-nums text-pitwall-muted">
                {d.tyre_age}
              </td>
              <td className="px-4 py-3">
                <ScoreBar score={d.undercut_score} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
