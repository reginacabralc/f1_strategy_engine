import { SessionPicker } from "./SessionPicker";
import type { ConnectionStatus } from "../hooks/useRaceFeed";

interface Props {
  selectedSession: string | null;
  onSelectSession: (id: string) => void;
  connectionStatus?: ConnectionStatus;
}

function StatusDot({ color }: { color: "green" | "yellow" | "red" | "white" }) {
  const cls = {
    green: "bg-pitwall-green shadow-[0_0_6px_#22c55e]",
    yellow: "bg-pitwall-yellow shadow-[0_0_6px_#eab308]",
    red: "bg-pitwall-accent shadow-[0_0_6px_#e10600]",
    white: "bg-pitwall-muted",
  }[color];
  return <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${cls}`} />;
}

function connectionDotColor(
  status: ConnectionStatus | undefined,
): "green" | "yellow" | "red" | "white" {
  if (status === "open") return "green";
  if (status === "connecting" || status === "reconnecting") return "yellow";
  if (status === "error" || status === "closed") return "red";
  return "white";
}

export function TopBar({ selectedSession, onSelectSession, connectionStatus }: Props) {
  return (
    <header className="h-11 shrink-0 flex items-center gap-0 border-b border-pitwall-border bg-pitwall-surface px-3">
      {/* Brand */}
      <div className="flex items-center gap-2 pr-4 border-r border-pitwall-border mr-4">
        <span className="text-pitwall-accent font-black text-sm tracking-tighter leading-none">
          PIT<span className="text-pitwall-text">WALL</span>
        </span>
      </div>

      {/* Session label */}
      <div className="flex items-center gap-2 text-xs">
        <StatusDot color={connectionDotColor(connectionStatus)} />
        <span className="text-pitwall-muted">Session</span>
        <span className="text-pitwall-text font-mono font-semibold">
          {selectedSession ?? "—"}
        </span>
      </div>

      <div className="w-px h-5 bg-pitwall-border mx-4" />

      {/* Lap placeholder */}
      <div className="flex items-center gap-1.5 text-xs">
        <span className="text-pitwall-muted">LAP</span>
        <span className="text-pitwall-text font-mono font-bold">—/—</span>
      </div>

      <div className="w-px h-5 bg-pitwall-border mx-4" />

      {/* Track status badge */}
      <div className="flex items-center gap-1.5">
        <StatusDot color="green" />
        <span className="text-[10px] font-semibold tracking-wider text-pitwall-green uppercase">
          Green Flag
        </span>
      </div>

      <div className="w-px h-5 bg-pitwall-border mx-4" />

      {/* Predictor badge */}
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-pitwall-muted uppercase tracking-wider">
          Predictor
        </span>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-pitwall-accent/10 text-pitwall-accent border border-pitwall-accent/30 uppercase tracking-wide">
          scipy
        </span>
      </div>

      {/* Right: session picker */}
      <div className="ml-auto">
        <SessionPicker selected={selectedSession} onSelect={onSelectSession} />
      </div>
    </header>
  );
}
