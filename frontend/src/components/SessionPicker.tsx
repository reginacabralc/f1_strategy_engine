import { useSessions } from "../hooks/useSessions";
import type { SessionSummary } from "../api/types";

interface Props {
  selected: string | null;
  onSelect: (sessionId: string) => void;
}

function sessionLabel(s: SessionSummary): string {
  return `${s.season} — ${s.circuit_id} (Round ${s.round_number})`;
}

export function SessionPicker({ selected, onSelect }: Props) {
  const { data: sessions, isPending, isError } = useSessions();

  if (isPending) {
    return (
      <span className="text-pitwall-muted text-sm">Loading sessions…</span>
    );
  }
  if (isError || !sessions) {
    return (
      <span className="text-red-400 text-sm">Failed to load sessions</span>
    );
  }
  if (sessions.length === 0) {
    return (
      <span className="text-pitwall-muted text-sm">
        No sessions in DB — run <code>make seed</code>
      </span>
    );
  }

  return (
    <select
      className="bg-pitwall-surface border border-pitwall-border text-pitwall-text rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-pitwall-accent"
      value={selected ?? ""}
      onChange={(e) => onSelect(e.target.value)}
    >
      <option value="" disabled>
        Select a session…
      </option>
      {sessions.map((s) => (
        <option key={s.session_id} value={s.session_id}>
          {sessionLabel(s)}
        </option>
      ))}
    </select>
  );
}
