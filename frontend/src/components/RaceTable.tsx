import type { DriverState } from "../api/types";

// Mock data — replaced in Day 4 when the WS snapshot feed is live
const MOCK_DRIVERS: DriverState[] = [
  {
    driver_code: "VER",
    team_code: "Red Bull",
    position: 1,
    gap_to_leader_ms: 0,
    gap_to_ahead_ms: null,
    last_lap_ms: 92_450,
    compound: "MEDIUM",
    tyre_age: 12,
    is_in_pit: false,
    is_lapped: false,
    last_pit_lap: 15,
    stint_number: 2,
    undercut_score: 0.15,
  },
  {
    driver_code: "LEC",
    team_code: "Ferrari",
    position: 2,
    gap_to_leader_ms: 3_200,
    gap_to_ahead_ms: 3_200,
    last_lap_ms: 92_810,
    compound: "MEDIUM",
    tyre_age: 14,
    is_in_pit: false,
    is_lapped: false,
    last_pit_lap: 13,
    stint_number: 2,
    undercut_score: 0.72,
  },
  {
    driver_code: "SAI",
    team_code: "Ferrari",
    position: 3,
    gap_to_leader_ms: 5_900,
    gap_to_ahead_ms: 2_700,
    last_lap_ms: 93_020,
    compound: "HARD",
    tyre_age: 8,
    is_in_pit: false,
    is_lapped: false,
    last_pit_lap: 19,
    stint_number: 2,
    undercut_score: 0.38,
  },
  {
    driver_code: "HAM",
    team_code: "Mercedes",
    position: 4,
    gap_to_leader_ms: 9_100,
    gap_to_ahead_ms: 3_200,
    last_lap_ms: 93_400,
    compound: "SOFT",
    tyre_age: 6,
    is_in_pit: false,
    is_lapped: false,
    last_pit_lap: 21,
    stint_number: 3,
    undercut_score: 0.51,
  },
];

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
    <div className="overflow-x-auto rounded-lg border border-pitwall-border">
      <table className="w-full text-sm">
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
