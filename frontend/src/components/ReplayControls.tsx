// Replay playback bar — controls wired to replay engine in Day 4.

const SPEEDS = ["×1", "×10", "×30", "×100"] as const;

function SkipBackIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="7,2 1,7 7,12" />
      <polygon points="13,2 7,7 13,12" />
    </svg>
  );
}

function StepBackIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="10,2 4,7 10,12" />
      <rect x="2" y="2" width="2" height="10" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="3,1 13,7 3,13" />
    </svg>
  );
}

function StepForwardIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="4,2 10,7 4,12" />
      <rect x="10" y="2" width="2" height="10" />
    </svg>
  );
}

function SkipForwardIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <polygon points="1,2 7,7 1,12" />
      <polygon points="7,2 13,7 7,12" />
    </svg>
  );
}

const CONTROL_BUTTONS = [
  { icon: <SkipBackIcon />, label: "Skip to start" },
  { icon: <StepBackIcon />, label: "Step back" },
  { icon: <PlayIcon />, label: "Play / Pause" },
  { icon: <StepForwardIcon />, label: "Step forward" },
  { icon: <SkipForwardIcon />, label: "Skip to end" },
];

export function ReplayControls() {
  return (
    <footer
      aria-label="Replay controls"
      className="h-12 shrink-0 bg-pitwall-surface border-t border-pitwall-border flex items-center gap-4 px-4"
    >
      {/* Transport buttons */}
      <div className="flex items-center gap-1">
        {CONTROL_BUTTONS.map((btn) => (
          <button
            key={btn.label}
            aria-label={btn.label}
            disabled
            className="w-8 h-8 rounded flex items-center justify-center text-pitwall-muted hover:text-pitwall-text hover:bg-pitwall-panel transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {btn.icon}
          </button>
        ))}
      </div>

      <div className="w-px h-6 bg-pitwall-border" />

      {/* Speed selector */}
      <div className="flex items-center gap-1">
        <span className="label-caps mr-1">Speed</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            disabled
            aria-label={`Set speed ${s}`}
            className={[
              "h-6 px-2 rounded text-[10px] font-mono font-bold border transition-colors",
              s === "×30"
                ? "bg-pitwall-accent/10 border-pitwall-accent/40 text-pitwall-accent"
                : "border-pitwall-border text-pitwall-muted opacity-50 cursor-not-allowed",
            ].join(" ")}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="w-px h-6 bg-pitwall-border" />

      {/* Lap counter */}
      <div className="flex items-center gap-1.5 text-xs font-mono">
        <span className="text-pitwall-muted">LAP</span>
        <span className="text-pitwall-text font-bold">—</span>
        <span className="text-pitwall-muted">/</span>
        <span className="text-pitwall-muted">—</span>
      </div>

      {/* Timeline track */}
      <div className="flex-1 flex items-center gap-2">
        <div
          className="flex-1 h-1 bg-pitwall-border rounded-full relative cursor-not-allowed"
          aria-label="Replay timeline"
        >
          <div className="absolute left-0 top-0 bottom-0 w-[35%] bg-pitwall-accent/60 rounded-full" />
          <div className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-pitwall-accent border-2 border-pitwall-surface shadow left-[35%] -translate-x-1/2" />
        </div>
      </div>

      <span className="text-[10px] text-pitwall-muted ml-1">
        Replay — Day 4
      </span>
    </footer>
  );
}
