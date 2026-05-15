import { useBacktest } from "../hooks/useBacktest";
import type { BacktestResult, UndercutMatch } from "../api/types";

// ─── Local helpers ────────────────────────────────────────────────────────────

function fmtPct(v?: number | null): string {
  if (v == null) return "—";
  return `${Math.round(v * 100)}%`;
}

function fmtNum(v?: number | null, decimals = 1): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

function fmtLap(v?: number | null): string {
  if (v == null) return "—";
  return `L${v}`;
}

// ─── Metric row ───────────────────────────────────────────────────────────────

interface MetricRowProps {
  label: string;
  value: string;
  highlight?: boolean;
}

function MetricRow({ label, value, highlight = false }: MetricRowProps) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-pitwall-border/50 last:border-0">
      <span className="text-[10px] text-pitwall-muted uppercase tracking-wide">
        {label}
      </span>
      <span
        className={`text-xs font-mono font-semibold tabular-nums ${highlight ? "text-pitwall-accent" : "text-pitwall-text"}`}
      >
        {value}
      </span>
    </div>
  );
}

// ─── Match table ──────────────────────────────────────────────────────────────

interface MatchTableProps {
  label: string;
  matches: UndercutMatch[] | undefined;
  "data-testid"?: string;
}

function MatchTable({ label, matches, "data-testid": testId }: MatchTableProps) {
  const rows = matches ?? [];
  return (
    <div data-testid={testId}>
      <span className="label-caps block mb-1">{label}</span>
      {rows.length === 0 ? (
        <p className="text-[10px] text-pitwall-muted py-1">—</p>
      ) : (
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-pitwall-muted">
              <th className="text-left font-medium pr-2 pb-0.5">Attacker</th>
              <th className="text-left font-medium pr-2 pb-0.5">Defender</th>
              <th className="text-right font-medium pr-2 pb-0.5">Alerted</th>
              <th className="text-right font-medium pb-0.5">Actual</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-pitwall-border/30">
            {rows.map((m, i) => (
              <tr key={i} className="font-mono tabular-nums">
                <td className="pr-2 py-0.5 font-bold text-pitwall-text">
                  {m.attacker}
                </td>
                <td className="pr-2 py-0.5 text-pitwall-muted">{m.defender}</td>
                <td className="pr-2 py-0.5 text-right text-pitwall-muted">
                  {fmtLap(m.lap_alerted)}
                </td>
                <td className="py-0.5 text-right text-pitwall-muted">
                  {fmtLap(m.lap_actual)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ─── Per-predictor panel ──────────────────────────────────────────────────────

interface PredictorPanelProps {
  label: string;
  isLoading: boolean;
  isError: boolean;
  data: BacktestResult | undefined;
}

function PredictorPanel({ label, isLoading, isError, data }: PredictorPanelProps) {
  return (
    <div
      className="flex flex-col gap-2 bg-pitwall-panel rounded-md p-3 border border-pitwall-border"
      data-testid={`backtest-panel-${label}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 pb-1 border-b border-pitwall-border">
        <span className="text-[11px] font-bold text-pitwall-text uppercase tracking-wider">
          {label}
        </span>
        {data && (
          <span className="ml-auto text-[9px] font-mono text-pitwall-muted">
            {data.true_positives?.length ?? 0} TP ·{" "}
            {data.false_positives?.length ?? 0} FP ·{" "}
            {data.false_negatives?.length ?? 0} FN
          </span>
        )}
      </div>

      {/* States */}
      {isLoading && (
        <p
          className="text-[10px] text-pitwall-muted text-center py-3"
          data-testid={`backtest-loading-${label}`}
        >
          Loading…
        </p>
      )}
      {isError && !isLoading && (
        <p
          className="text-[10px] text-pitwall-muted text-center py-3"
          data-testid={`backtest-unavailable-${label}`}
        >
          No curated backtest data for this session yet.
        </p>
      )}

      {/* Metrics */}
      {data && !isLoading && (
        <>
          <div>
            <MetricRow label="Precision" value={fmtPct(data.precision)} highlight={data.precision >= 0.6} />
            <MetricRow label="Recall" value={fmtPct(data.recall)} highlight={data.recall >= 0.6} />
            <MetricRow label="F1" value={fmtPct(data.f1)} highlight={data.f1 >= 0.6} />
            {data.mean_lead_time_laps != null && (
              <MetricRow label="Lead time" value={`${fmtNum(data.mean_lead_time_laps)} laps`} />
            )}
            {data.mae_k1_ms != null && (
              <MetricRow label="MAE k1" value={`${data.mae_k1_ms} ms`} />
            )}
            {data.mae_k3_ms != null && (
              <MetricRow label="MAE k3" value={`${data.mae_k3_ms} ms`} />
            )}
            {data.mae_k5_ms != null && (
              <MetricRow label="MAE k5" value={`${data.mae_k5_ms} ms`} />
            )}
          </div>

          {/* TP / FP / FN */}
          <div className="flex flex-col gap-2 mt-1">
            <MatchTable
              label="True Positives"
              matches={data.true_positives}
              data-testid={`tp-table-${label}`}
            />
            <MatchTable
              label="False Positives"
              matches={data.false_positives}
              data-testid={`fp-table-${label}`}
            />
            <MatchTable
              label="False Negatives"
              matches={data.false_negatives}
              data-testid={`fn-table-${label}`}
            />
          </div>
        </>
      )}
    </div>
  );
}

// ─── BacktestView ─────────────────────────────────────────────────────────────

interface Props {
  sessionId?: string | null;
}

export function BacktestView({ sessionId }: Props) {
  const scipy = useBacktest(sessionId, "scipy");
  const xgb = useBacktest(sessionId, "xgboost");

  return (
    <section
      aria-label="Backtest results"
      className="panel flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <span className="label-caps">Backtest — scipy vs XGBoost</span>
        {sessionId && (
          <span className="text-[10px] font-mono text-pitwall-muted">
            {sessionId}
          </span>
        )}
      </div>

      <div className="p-3">
        {/* Empty state */}
        {!sessionId ? (
          <p
            className="text-[11px] text-pitwall-muted text-center py-6"
            data-testid="backtest-empty"
          >
            Select a session to load backtest results.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <PredictorPanel
              label="scipy"
              isLoading={scipy.isLoading}
              isError={scipy.isError}
              data={scipy.data}
            />
            <PredictorPanel
              label="xgboost"
              isLoading={xgb.isLoading}
              isError={xgb.isError}
              data={xgb.data}
            />
          </div>
        )}
      </div>
    </section>
  );
}
