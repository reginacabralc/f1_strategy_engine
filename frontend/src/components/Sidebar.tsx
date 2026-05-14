import { useState } from "react";

type NavId =
  | "overview"
  | "timing"
  | "strategy"
  | "tyres"
  | "track"
  | "weather"
  | "settings";

interface NavItem {
  id: NavId;
  label: string;
  icon: React.ReactNode;
}

function GridIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="1" width="6" height="6" rx="1" />
      <rect x="9" y="1" width="6" height="6" rx="1" />
      <rect x="1" y="9" width="6" height="6" rx="1" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 4.5V8l2.5 1.5" strokeLinecap="round" />
    </svg>
  );
}

function DiamondIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <polygon points="8,1 15,8 8,15 1,8" />
    </svg>
  );
}

function CircleIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <circle cx="8" cy="8" r="5.5" />
      <circle cx="8" cy="8" r="2" fill="currentColor" stroke="none" />
    </svg>
  );
}

function WaveIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    >
      <path d="M1 8 Q3 4 5 8 Q7 12 9 8 Q11 4 13 8 Q14.5 11 16 8" />
    </svg>
  );
}

function CloudIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path
        d="M4 11a3 3 0 1 1 0-6 4 4 0 0 1 7.9 1A2.5 2.5 0 0 1 13 11Z"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
    >
      <circle cx="8" cy="8" r="2.5" />
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" />
    </svg>
  );
}

const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", icon: <GridIcon /> },
  { id: "timing", label: "Timing", icon: <ClockIcon /> },
  { id: "strategy", label: "Strategy", icon: <DiamondIcon /> },
  { id: "tyres", label: "Tyres", icon: <CircleIcon /> },
  { id: "track", label: "Track", icon: <WaveIcon /> },
  { id: "weather", label: "Weather", icon: <CloudIcon /> },
];

export function Sidebar() {
  const [active, setActive] = useState<NavId>("timing");

  return (
    <nav
      aria-label="Dashboard navigation"
      className="w-14 bg-pitwall-surface border-r border-pitwall-border flex flex-col items-center py-3 gap-1 shrink-0"
    >
      {/* Logo mark */}
      <div className="w-8 h-8 rounded flex items-center justify-center mb-3 bg-pitwall-accent">
        <span className="text-white text-xs font-black tracking-tighter">P</span>
      </div>

      {NAV_ITEMS.map((item) => {
        const isActive = active === item.id;
        return (
          <button
            key={item.id}
            aria-label={item.label}
            aria-current={isActive ? "page" : undefined}
            onClick={() => setActive(item.id)}
            className={[
              "relative flex flex-col items-center justify-center gap-1 w-10 h-12 rounded transition-colors",
              isActive
                ? "text-pitwall-accent bg-pitwall-accent-glow"
                : "text-pitwall-muted hover:text-pitwall-text hover:bg-pitwall-panel",
            ].join(" ")}
          >
            {isActive && (
              <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r bg-pitwall-accent" />
            )}
            {item.icon}
            <span className="text-[8px] uppercase tracking-wide leading-none">
              {item.label}
            </span>
          </button>
        );
      })}

      <div className="mt-auto">
        <button
          aria-label="Settings"
          className="flex flex-col items-center justify-center gap-1 w-10 h-12 rounded text-pitwall-muted hover:text-pitwall-text hover:bg-pitwall-panel transition-colors"
        >
          <GearIcon />
          <span className="text-[8px] uppercase tracking-wide leading-none">
            Settings
          </span>
        </button>
      </div>
    </nav>
  );
}
