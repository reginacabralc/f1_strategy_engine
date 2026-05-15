// Monaco-inspired track map — visual base only.
// Live driver positions wire in after Stream C Day 4 (useRaceFeed).

export interface TrackMapDriver {
  number: string;
  code: string;
  team?: string;
  color?: string;
  x: number;
  y: number;
  gap?: string;
  labelOffset?: { dx: number; dy: number };
}

// Centerline path, 280×200 viewBox, clockwise from top of main straight.
// Not topographically accurate — stylised approximation only.
const CIRCUIT_PATH =
  "M 220 52 " +
  "C 232 46,244 54,252 68 " +
  "C 258 80,255 96,246 107 " +
  "L 232 115 " +
  "C 222 119,212 117,204 111 " +
  "L 178 109 " +
  "C 166 107,158 99,158 87 " +
  "L 158 67 " +
  "C 158 53,149 45,137 45 " +
  "C 124 45,116 55,116 68 " +
  "L 116 84 " +
  "C 116 98,106 107,93 108 " +
  "C 79 109,70 121,70 135 " +
  "C 70 149,81 158,95 157 " +
  "L 112 154 " +
  "C 122 153,128 162,126 174 " +
  "C 124 185,113 190,100 189 " +
  "L 66 188 " +
  "C 47 188,36 173,36 155 " +
  "C 36 137,50 128,66 129 " +
  "L 192 129 " +
  "C 207 129,216 141,214 157 " +
  "L 215 170 " +
  "C 217 178,219 168,220 155 " +
  "L 220 52";

const MOCK_DRIVERS: TrackMapDriver[] = [
  {
    number: "1",
    code: "VER",
    team: "Red Bull",
    color: "#3671C6",
    x: 220,
    y: 98,
    labelOffset: { dx: 8, dy: -3 },
  },
  {
    number: "16",
    code: "LEC",
    team: "Ferrari",
    color: "#E8002D",
    x: 249,
    y: 87,
    labelOffset: { dx: -30, dy: -6 },
  },
  {
    number: "4",
    code: "NOR",
    team: "McLaren",
    color: "#FF8000",
    x: 142,
    y: 45,
    labelOffset: { dx: -4, dy: -7 },
  },
  {
    number: "81",
    code: "PIA",
    team: "McLaren",
    color: "#FF8000",
    x: 90,
    y: 108,
    labelOffset: { dx: -30, dy: -5 },
  },
  {
    number: "44",
    code: "HAM",
    team: "Mercedes",
    color: "#27F4D2",
    x: 128,
    y: 129,
    labelOffset: { dx: -4, dy: 11 },
  },
  {
    number: "55",
    code: "SAI",
    team: "Ferrari",
    color: "#E8002D",
    x: 50,
    y: 162,
    labelOffset: { dx: -30, dy: -5 },
  },
];

function DriverMarker({ driver }: { driver: TrackMapDriver }) {
  const color = driver.color ?? "#e2e8f0";
  const { dx = 8, dy = -4 } = driver.labelOffset ?? {};

  return (
    <g role="img" aria-label={`${driver.code} car ${driver.number}`}>
      <circle cx={driver.x} cy={driver.y} r={7} fill={color} opacity={0.18} />
      <circle
        cx={driver.x}
        cy={driver.y}
        r={4}
        fill={color}
        stroke="#0a0c12"
        strokeWidth={1.5}
      />
      <text
        x={driver.x + dx}
        y={driver.y + dy}
        fontSize="6.5"
        fontFamily="ui-monospace,monospace"
        fontWeight="700"
        fill={color}
        opacity={0.92}
      >
        {driver.number} {driver.code}
      </text>
    </g>
  );
}

interface Props {
  drivers?: TrackMapDriver[];
}

export function TrackMapPanel({ drivers = MOCK_DRIVERS }: Props) {
  return (
    <section
      aria-label="Track map"
      className="panel flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-pitwall-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="label-caps">Track Map</span>
          <span className="text-[9px] text-pitwall-muted">
            Circuit de Monaco
          </span>
        </div>
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold bg-pitwall-accent/10 text-pitwall-accent border border-pitwall-accent/30 uppercase tracking-wide">
          Static preview
        </span>
      </div>

      {/* Map */}
      <div className="flex-1 flex items-center justify-center p-2 min-h-0">
        <svg
          viewBox="0 0 280 200"
          className="w-full"
          style={{ maxHeight: 172 }}
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          {/* DRS zone — main straight */}
          <line
            x1="220"
            y1="60"
            x2="220"
            y2="132"
            stroke="#22c55e"
            strokeWidth="3.5"
            strokeOpacity="0.22"
            strokeLinecap="round"
          />

          {/* Track width (wide stroke = asphalt) */}
          <path
            d={CIRCUIT_PATH}
            fill="none"
            stroke="#252836"
            strokeWidth="9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Track surface highlight */}
          <path
            d={CIRCUIT_PATH}
            fill="none"
            stroke="#32374a"
            strokeWidth="5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Centreline */}
          <path
            d={CIRCUIT_PATH}
            fill="none"
            stroke="#3e4558"
            strokeWidth="1"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="3 4"
          />

          {/* Start / finish line */}
          <line
            x1="215"
            y1="52"
            x2="225"
            y2="52"
            stroke="#ffffff"
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          {/* Pit lane entry mark */}
          <line
            x1="215"
            y1="148"
            x2="225"
            y2="148"
            stroke="#eab308"
            strokeWidth="1.5"
            strokeOpacity="0.55"
            strokeLinecap="round"
          />

          {/* Sector boundary S1→S2 (near top hairpin) */}
          <line
            x1="128"
            y1="38"
            x2="146"
            y2="38"
            stroke="#3b82f6"
            strokeWidth="1.5"
            strokeOpacity="0.5"
          />

          {/* Sector boundary S2→S3 (Rascasse) */}
          <line
            x1="28"
            y1="148"
            x2="28"
            y2="163"
            stroke="#8b5cf6"
            strokeWidth="1.5"
            strokeOpacity="0.5"
          />

          {/* Corner / zone labels */}
          <text
            x="227"
            y="56"
            fontSize="5.5"
            fill="#9ca3af"
            fontFamily="ui-monospace,monospace"
          >
            S/F
          </text>
          <text
            x="227"
            y="146"
            fontSize="5.5"
            fill="#eab308"
            fontFamily="ui-monospace,monospace"
            opacity="0.65"
          >
            PIT
          </text>
          <text
            x="227"
            y="74"
            fontSize="5"
            fill="#22c55e"
            fontFamily="ui-monospace,monospace"
            opacity="0.55"
          >
            DRS
          </text>
          <text
            x="129"
            y="35"
            fontSize="5"
            fill="#3b82f6"
            fontFamily="ui-monospace,monospace"
            opacity="0.6"
          >
            S2
          </text>
          <text
            x="16"
            y="158"
            fontSize="5"
            fill="#8b5cf6"
            fontFamily="ui-monospace,monospace"
            opacity="0.6"
          >
            S3
          </text>

          {/* Driver markers */}
          {drivers.map((d) => (
            <DriverMarker key={d.code} driver={d} />
          ))}
        </svg>
      </div>

      {/* Footer */}
      <p className="px-3 py-1.5 text-[10px] text-pitwall-muted border-t border-pitwall-border text-center shrink-0">
        Static preview — live positions via race feed
      </p>
    </section>
  );
}
