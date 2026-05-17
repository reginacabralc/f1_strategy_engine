import { usePredictor } from "../hooks/usePredictor";
import type { PredictorName } from "../api/types";

// Three independent decision paths — all three are real options at runtime.
// `causal` uses scipy for pace projection and runs the causal observer in
// parallel (see docs/causal_model_performance.md).
const PREDICTORS: PredictorName[] = ["scipy", "xgboost", "causal"];

interface Props {
  activePredictor?: PredictorName;
}

export function PredictorToggle({ activePredictor }: Props) {
  // Pass activePredictor into the hook so it can clear the optimistic
  // pending state as soon as the next snapshot confirms the switch.
  const { pendingTarget, error, switchPredictor } = usePredictor({
    activePredictor,
  });
  const pending = pendingTarget !== null;
  // While switching show target optimistically; fall back to prop then "scipy"
  const displayed: PredictorName = pendingTarget ?? activePredictor ?? "scipy";

  return (
    <section
      aria-label="Predictor selection"
      className="panel flex flex-col overflow-hidden"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <span className="label-caps">Pace Predictor</span>
        {pending && (
          <span className="text-[10px] font-mono text-pitwall-muted animate-pulse">
            Switching…
          </span>
        )}
      </div>

      <div className="px-3 py-2.5 flex gap-2">
        {PREDICTORS.map((p) => {
          const isActive = p === displayed;
          return (
            <button
              key={p}
              role="radio"
              aria-checked={isActive}
              disabled={pending}
              onClick={() => switchPredictor(p)}
              data-testid={`predictor-${p}`}
              className={[
                "flex-1 h-7 rounded text-[10px] font-bold border transition-colors uppercase tracking-wider",
                isActive
                  ? "bg-pitwall-accent/15 border-pitwall-accent/50 text-pitwall-accent"
                  : "border-pitwall-border text-pitwall-muted hover:text-pitwall-text hover:border-pitwall-muted",
                pending ? "opacity-50 cursor-not-allowed" : "",
              ].join(" ")}
            >
              {p}
            </button>
          );
        })}
      </div>

      {error && (
        <p
          className="px-3 pb-2.5 text-[10px] text-pitwall-yellow leading-snug"
          data-testid="predictor-error"
        >
          {error}
        </p>
      )}
    </section>
  );
}
