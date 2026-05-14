import type { DriverState } from "../api/types";
import mockRaceOrder from "../data/mockRaceOrder.json";

const MOCK_DRIVERS = mockRaceOrder as DriverState[];

const COMPOUND_STYLES: Record<
  string,
  { text: string; bg: string; border: string }
> = {
  SOFT: {
    text: "text-red-400",
    bg: "bg-red-950/60",
    border: "border-red-800/50",
  },
  MEDIUM: {
    text: "text-yellow-400",
    bg: "bg-yellow-950/60",
    border: "border-yellow-800/50",
  },
  HARD: {
    text: "text-slate-300",
    bg: "bg-slate-800/40",
    border: "border-slate-600/40",
  },
  INTER: {
    text: "text-green-400",
    bg: "bg-green-950/60",
    border: "border-green-800/50",
  },
  WET: {
    text: "text-blue-400",
    bg: "bg-blue-950/60",
    border: "border-blue-800/50",
  },
};

function ScoreBar({ score }: { score: number | null | undefined }) {
  if (score == null)
    return <span className="text-pitwall-muted font-mono">—</span>;
  const pct = Math.round(score * 100);
  const color =
    score >= 0.6
      ? "bg-pitwall-accent"
      : score >= 0.35
        ? "bg-pitwall-yellow"
        : "bg-pitwall-green";
  const textColor =
    score >= 0.6
      ? "text-pitwall-accent"
      : score >= 0.35
        ? "text-pitwall-yellow"
        : "text-pitwall-green";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-pitwall-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs tabular-nums font-mono font-semibold ${textColor}`}>
        {pct}%
      </span>
    </div>
  );
}

function msToGap(ms: number | null | undefined): string {
  if (ms == null || ms === 0) return "—";
  return `+${(ms / 1000).toFixed(3)}s`;
}

function positionStyle(pos: number): string {
  if (pos === 1) return "text-pitwall-yellow font-bold";
  if (pos <= 3) return "text-pitwall-text font-semibold";
  return "text-pitwall-muted";
}

interface Props {
  drivers?: DriverState[];
}

export function RaceTable({ drivers = MOCK_DRIVERS }: Props) {
  return (
    <div
      className="overflow-x-auto rounded-lg border border-pitwall-border bg-pitwall-surface"
      data-testid="race-table-scroll"
    >
      <table className="min-w-[760px] w-full text-xs">
        <thead>
          <tr className="border-b border-pitwall-border">
            <th
              scope="col"
              className="px-3 py-2.5 text-left w-8 label-caps"
            >
              P
            </th>
            <th scope="col" className="px-3 py-2.5 text-left label-caps">
              Driver
            </th>
            <th scope="col" className="px-3 py-2.5 text-left label-caps">
              Team
            </th>
            <th scope="col" className="px-3 py-2.5 text-right label-caps">
              Gap
            </th>
            <th scope="col" className="px-3 py-2.5 text-left label-caps">
              Compound
            </th>
            <th scope="col" className="px-3 py-2.5 text-right label-caps">
              Tyre Age
            </th>
            <th scope="col" className="px-3 py-2.5 text-left label-caps">
              Score
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-pitwall-border">
          {drivers.map((d) => {
            const compound = COMPOUND_STYLES[d.compound] ?? {
              text: "text-pitwall-muted",
              bg: "bg-pitwall-panel",
              border: "border-pitwall-border",
            };
            return (
              <tr
                key={d.driver_code}
                className="hover:bg-pitwall-panel/60 transition-colors"
              >
                <td
                  className={`px-3 py-2.5 font-mono text-sm ${positionStyle(d.position)}`}
                >
                  {d.position}
                </td>
                <td className="px-3 py-2.5">
                  <span className="font-bold text-sm text-pitwall-text tracking-wide">
                    {d.driver_code}
                  </span>
                  {d.is_in_pit && (
                    <span className="ml-1.5 text-[9px] font-bold text-pitwall-orange uppercase tracking-wider">
                      PIT
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-pitwall-muted">
                  {d.team_code ?? "—"}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-pitwall-muted">
                  {msToGap(d.gap_to_leader_ms)}
                </td>
                <td className="px-3 py-2.5">
                  <span
                    className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border ${compound.bg} ${compound.text} ${compound.border}`}
                  >
                    {d.compound}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-pitwall-muted">
                  {d.tyre_age}
                </td>
                <td className="px-3 py-2.5">
                  <ScoreBar score={d.undercut_score} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
