import type { Compound, RaceSnapshot } from "../../api/types";
import { DegradationChart } from "../DegradationChart";

interface Props {
  snapshot: RaceSnapshot | null;
  circuit: string;
}

const COMPOUNDS: Compound[] = ["SOFT", "MEDIUM", "HARD"];

function compoundTone(compound?: string | null): string {
  if (compound === "SOFT") return "text-red-400 bg-red-950/40 border-red-800/40";
  if (compound === "MEDIUM")
    return "text-yellow-400 bg-yellow-950/40 border-yellow-800/40";
  if (compound === "HARD")
    return "text-slate-300 bg-slate-800/40 border-slate-600/40";
  return "text-pitwall-muted bg-pitwall-muted/10 border-pitwall-muted/30";
}

export function TyresPanel({ snapshot, circuit }: Props) {
  const drivers = (snapshot?.drivers ?? []).slice().sort(
    (a, b) => (a.position ?? 99) - (b.position ?? 99),
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 h-full min-h-0">
      <section className="panel flex flex-col min-h-0">
        <div className="px-3 py-2 border-b border-pitwall-border">
          <span className="label-caps">Tyre Status</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {drivers.length === 0 ? (
            <p className="px-3 py-6 text-xs text-pitwall-muted text-center">
              No driver data yet. Start a replay to populate.
            </p>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead className="text-[10px] text-pitwall-muted uppercase tracking-wide">
                <tr className="border-b border-pitwall-border">
                  <th className="text-left px-3 py-1.5">P</th>
                  <th className="text-left px-1 py-1.5">Driver</th>
                  <th className="text-left px-1 py-1.5">Compound</th>
                  <th className="text-right px-1 py-1.5">Age</th>
                  <th className="text-right px-3 py-1.5">Stint</th>
                </tr>
              </thead>
              <tbody>
                {drivers.map((d) => (
                  <tr
                    key={d.driver_code}
                    className="border-b border-pitwall-border/30"
                  >
                    <td className="px-3 py-1.5 text-pitwall-muted">
                      {d.position ?? "—"}
                    </td>
                    <td className="px-1 py-1.5 font-bold text-white">
                      {d.driver_code}
                    </td>
                    <td className="px-1 py-1.5">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-bold ${compoundTone(
                          d.compound,
                        )}`}
                      >
                        {d.compound ?? "—"}
                      </span>
                    </td>
                    <td className="px-1 py-1.5 text-right text-white">
                      {d.tyre_age}
                    </td>
                    <td className="px-3 py-1.5 text-right text-pitwall-muted">
                      #{d.stint_number}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="panel flex flex-col min-h-0">
        <div className="px-3 py-2 border-b border-pitwall-border flex items-center justify-between">
          <span className="label-caps">Degradation Curves</span>
          <span className="text-[10px] text-pitwall-muted font-mono">
            {circuit}
          </span>
        </div>
        <div className="flex-1 min-h-0 p-2">
          <DegradationChart circuit={circuit} />
        </div>
        <div className="px-3 py-2 border-t border-pitwall-border text-[10px] text-pitwall-muted">
          Compounds shown: {COMPOUNDS.join(" / ")}. Lower R² = noisier fit.
        </div>
      </section>
    </div>
  );
}
