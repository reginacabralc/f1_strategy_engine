import { useEffect, useMemo, useRef, useState } from "react";
import type { DriverState } from "../api/types";
import {
  getTrackLayout,
  type TrackLayout,
} from "../data/trackLayouts";

// ────────────────────────────────────────────────────────────────────────────
// Driver projection
// ────────────────────────────────────────────────────────────────────────────
//
// Backend snapshots contain `position`, `gap_to_leader_ms`, `last_lap_ms` per
// driver — but no telemetry coordinates. We approximate each driver's position
// along the track centerline using:
//
//   fraction_behind_leader = (gap_to_leader_ms mod REFERENCE_LAP_MS) / REFERENCE_LAP_MS
//   fraction_around_track  = (startFinishAt + (1 - fraction_behind_leader)) mod 1
//
// The leader sits at the start/finish line (parametric t = startFinishAt) and
// everyone else trails clockwise around the path by their gap share. This is a
// *spatial approximation* — useful for the demo, not real telemetry.

const REFERENCE_LAP_MS = 90_000;

// Approximate FIA team colours. Falls back to a hash-based hue.
const TEAM_COLORS: Record<string, string> = {
  red_bull: "#3671C6",
  ferrari: "#E8002D",
  mercedes: "#27F4D2",
  mclaren: "#FF8000",
  aston_martin: "#229971",
  alpine: "#0093CC",
  williams: "#37BEDD",
  rb: "#6692FF",
  alphatauri: "#5E8FAA",
  sauber: "#52E252",
  haas: "#B6BABD",
  kick_sauber: "#52E252",
};

function colorForDriver(driver: DriverState): string {
  const team = (driver.team_code ?? "").toLowerCase();
  const hit = TEAM_COLORS[team];
  if (hit) return hit;
  let h = 0;
  for (let i = 0; i < driver.driver_code.length; i++) {
    h = (h * 31 + driver.driver_code.charCodeAt(i)) % 360;
  }
  return `hsl(${h}, 70%, 55%)`;
}

interface Props {
  drivers?: DriverState[];
  circuit?: string;
  currentLap?: number;
  totalLaps?: number;
  isLive?: boolean;
}

export function TrackMapPanel({
  drivers = [],
  circuit,
  currentLap = 0,
  totalLaps,
  isLive = false,
}: Props) {
  const { layout, isFallback } = getTrackLayout(circuit);
  const pathRef = useRef<SVGPathElement | null>(null);
  const [pathLength, setPathLength] = useState<number>(0);

  // Re-measure path length whenever the layout changes (selecting a new track
  // swaps `layout.path` and triggers this effect). jsdom (the test runner)
  // does not implement `getTotalLength`, so we guard for that and fall back
  // to the empty state — production browsers always succeed.
  useEffect(() => {
    const node = pathRef.current;
    if (node && typeof node.getTotalLength === "function") {
      try {
        setPathLength(node.getTotalLength());
      } catch {
        setPathLength(0);
      }
    } else {
      setPathLength(0);
    }
  }, [layout.path]);

  // Compute (x, y) for each driver along the path.
  const positionedDrivers = useMemo(() => {
    if (!pathRef.current || pathLength === 0) return [];
    const sorted = [...drivers].sort(
      (a, b) => (a.position ?? 99) - (b.position ?? 99),
    );
    const startFinish = layout.startFinishAt ?? 0;
    return sorted.map((d, idx) => {
      let fractionBehindLeader: number;
      if (d.gap_to_leader_ms != null && d.gap_to_leader_ms > 0) {
        fractionBehindLeader =
          (d.gap_to_leader_ms % REFERENCE_LAP_MS) / REFERENCE_LAP_MS;
      } else if ((d.position ?? 0) > 1) {
        // Spread by grid order when gaps are unknown so dots never collapse.
        fractionBehindLeader = (idx * 0.05) % 1;
      } else {
        fractionBehindLeader = 0;
      }
      const fractionAroundPath = (startFinish + (1.0 - fractionBehindLeader)) % 1;
      const pt = pathRef.current!.getPointAtLength(
        fractionAroundPath * pathLength,
      );
      return { driver: d, x: pt.x, y: pt.y, color: colorForDriver(d) };
    });
  }, [drivers, pathLength, layout.path, layout.startFinishAt]);

  const startFinishPoint = useMemo(() => {
    if (!pathRef.current || pathLength === 0) return null;
    const t = layout.startFinishAt ?? 0;
    try {
      return pathRef.current.getPointAtLength(t * pathLength);
    } catch {
      return null;
    }
  }, [pathLength, layout.startFinishAt]);

  return (
    <section
      aria-label="Track map"
      data-testid={`track-map-${layout.id}`}
      className="panel flex flex-col overflow-hidden h-full"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="label-caps">Track Map</span>
          <span className="text-[10px] text-pitwall-muted font-mono">
            {layout.displayName}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {currentLap > 0 && (
            <span className="text-[10px] font-mono text-pitwall-muted">
              Lap {currentLap}
              {totalLaps ? ` / ${totalLaps}` : ""}
            </span>
          )}
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold border uppercase tracking-wide ${
              isLive
                ? "bg-pitwall-accent/10 text-pitwall-accent border-pitwall-accent/40 animate-pulse"
                : "bg-pitwall-muted/10 text-pitwall-muted border-pitwall-muted/30"
            }`}
          >
            {isLive ? "Live" : "Idle"}
          </span>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-2 min-h-0">
        <svg
          viewBox={layout.viewBox}
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Asphalt outline (wide stroke = track edge halo) */}
          <path
            d={layout.path}
            fill="none"
            stroke="#252836"
            strokeWidth="11"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d={layout.path}
            fill="none"
            stroke="#32374a"
            strokeWidth="6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* Centreline + measurement reference */}
          <path
            ref={pathRef}
            d={layout.path}
            fill="none"
            stroke="#3e4558"
            strokeWidth="1"
            strokeDasharray="2 3"
          />

          {/* Start/finish marker (white tick perpendicular to centerline) */}
          {startFinishPoint && (
            <g>
              <circle
                cx={startFinishPoint.x}
                cy={startFinishPoint.y}
                r={3.2}
                fill="#f3f4f6"
                stroke="#0f1118"
                strokeWidth={0.6}
              />
              <text
                x={startFinishPoint.x + 5}
                y={startFinishPoint.y - 4}
                fontSize={5}
                fontFamily="ui-monospace,monospace"
                fill="#f3f4f6"
                opacity={0.7}
              >
                S/F
              </text>
            </g>
          )}

          {/* Driver dots */}
          {positionedDrivers.map(({ driver, x, y, color }) => {
            const isInPit = driver.is_in_pit;
            return (
              <g key={driver.driver_code}>
                <circle
                  cx={x}
                  cy={y}
                  r={5.5}
                  fill={color}
                  fillOpacity={isInPit ? 0.25 : 0.18}
                />
                <circle
                  cx={x}
                  cy={y}
                  r={3.4}
                  fill={color}
                  stroke="#0f1118"
                  strokeWidth={0.8}
                  fillOpacity={isInPit ? 0.5 : 1}
                />
                <text
                  x={x}
                  y={y - 7}
                  fontSize={5.5}
                  fontFamily="ui-monospace,monospace"
                  fontWeight={700}
                  textAnchor="middle"
                  fill="#e5e7eb"
                  opacity={0.95}
                >
                  {driver.driver_code}
                </text>
              </g>
            );
          })}

          {/* Empty-state message */}
          {positionedDrivers.length === 0 && (
            <text
              x={140}
              y={104}
              textAnchor="middle"
              fontSize={8}
              fontFamily="ui-monospace,monospace"
              fill="#6b7280"
            >
              Waiting for replay snapshot…
            </text>
          )}
        </svg>
      </div>

      {/* Fallback footer when the selected circuit has no dedicated layout. */}
      {isFallback && (
        <div
          data-testid="track-map-fallback-note"
          className="px-3 py-1.5 border-t border-pitwall-border text-[10px] text-pitwall-muted font-mono"
        >
          Custom layout not available for this track — showing generic oval.
        </div>
      )}
    </section>
  );
}
