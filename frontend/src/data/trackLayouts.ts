// Realistic stylised F1 circuit layouts as closed SVG paths.
//
// Each layout is hand-drawn to be recognisable at a glance. The shapes are not
// topographically exact — full GPS centerlines would be 10× the file size —
// but they capture the signature corners (Monaco's hairpin + tunnel, Spa's
// Eau Rouge + Kemmel, Monza's chicane + Parabolica, etc.).
//
// All paths share the same viewBox (280 × 200) so the SVG renderer can swap
// between them without rescaling. Paths are closed (`Z`) and drawn clockwise
// from the start-finish line at parametric t = 0.
//
// Position-along-track is computed in TrackMapPanel via
// SVGPathElement.getTotalLength() / getPointAtLength(). The frontend treats
// `gap_to_leader_ms` as a fraction of REFERENCE_LAP_MS and projects each
// driver onto a fraction around the path; the visual is therefore a *spatial
// approximation*, not real telemetry. This is documented in DEMO.md.

export interface TrackLayout {
  /** Internal id; matches the `circuit_id` field of /api/v1/sessions */
  id: string;
  /** Display name shown in the UI */
  displayName: string;
  /** SVG viewBox — all layouts use 280×200 so the renderer can swap freely */
  viewBox: string;
  /** Closed SVG path (must end with `Z`) */
  path: string;
  /** Optional aliases / alternate session_id prefixes (e.g. "s_o_paulo") */
  aliases?: readonly string[];
  /** Parametric position of the start-finish line on the path (0..1) */
  startFinishAt?: number;
  /** Direction of travel along the path */
  direction?: "cw" | "ccw";
}

// ────────────────────────────────────────────────────────────────────────────
// MONACO — Circuit de Monaco
// Signature: Ste-Devote left at start, climb to Massenet, Casino Square,
// Mirabeau, Grand Hotel hairpin (slowest corner in F1), Portier into the
// tunnel, harbour chicane, Tabac, swimming pool, Rascasse, Antony Noghes.
// ────────────────────────────────────────────────────────────────────────────
const MONACO_PATH =
  // Start/finish straight (bottom right, heading north)
  "M 232 168 " +
  // Ste-Devote (right-hander) and climb up Beau Rivage
  "L 232 130 " +
  "C 232 118,222 110,212 110 " +
  // Massenet (left) and Casino Square plateau
  "L 184 110 " +
  "C 172 110,164 102,164 90 " +
  // Mirabeau / Loews descent
  "L 164 70 " +
  "C 164 58,156 50,144 50 " +
  // Grand Hotel hairpin (180° tight U-turn)
  "L 132 50 " +
  "C 118 50,110 60,114 72 " +
  // Portier sweep
  "L 118 84 " +
  "C 122 92,118 98,108 98 " +
  // Tunnel chicane (jink)
  "L 96 96 " +
  "C 84 95,76 105,80 116 " +
  // Nouvelle Chicane (harbour entry)
  "L 86 124 " +
  "C 88 130,82 134,76 132 " +
  "L 56 128 " +
  // Tabac (long right around harbour)
  "C 42 126,32 138,36 152 " +
  // Swimming pool chicane (left-right-left)
  "L 50 156 " +
  "L 60 150 " +
  "L 70 156 " +
  "L 80 152 " +
  "L 92 162 " +
  // Rascasse (slow right around the famous corner)
  "C 100 168,108 170,116 166 " +
  "L 140 158 " +
  "C 154 154,166 158,170 168 " +
  // Antony Noghes back to start straight
  "L 178 178 " +
  "C 184 184,196 184,204 180 " +
  "L 232 168 Z";

// ────────────────────────────────────────────────────────────────────────────
// BAHRAIN — Bahrain International Circuit
// Signature: long start-finish straight, tight T1 right, T4 hairpin, mid-
// sector loop, long back straight to T11, technical figure-8 final sector.
// ────────────────────────────────────────────────────────────────────────────
const BAHRAIN_PATH =
  // Start-finish straight (top, heading west to east — the longest in F1)
  "M 40 50 " +
  "L 230 50 " +
  // T1 (heavy braking right)
  "C 250 50,260 60,258 78 " +
  // T2-T3 sweeps and T4 hairpin
  "L 256 100 " +
  "C 254 116,240 124,224 122 " +
  // Mid-sector loop into back straight start
  "L 200 120 " +
  "C 188 120,180 110,184 100 " +
  "L 196 92 " +
  "C 204 86,200 76,190 76 " +
  // Twin DRS straights (T10-T11)
  "L 110 76 " +
  "C 96 76,90 90,98 100 " +
  // Final sector tight infield
  "L 116 116 " +
  "C 124 124,122 134,114 138 " +
  "L 78 144 " +
  "C 64 146,52 138,50 124 " +
  // Last sector lefts back to grid
  "L 48 100 " +
  "C 46 88,36 80,26 84 " +
  "L 20 92 " +
  "C 10 96,6 86,12 78 " +
  "L 24 64 " +
  "C 28 56,34 50,40 50 Z";

// ────────────────────────────────────────────────────────────────────────────
// SILVERSTONE — Silverstone Circuit (post-2010 layout)
// Signature: Abbey-Farm-Village-Loop opening complex, the Wellington Straight,
// the legendary Maggotts-Becketts-Chapel high-speed esses, Hangar Straight,
// Stowe, Vale, and the Club corner exit back to the start-finish straight.
// ────────────────────────────────────────────────────────────────────────────
const SILVERSTONE_PATH =
  // Start-finish (Hamilton Straight)
  "M 60 160 " +
  // Abbey right-hander into Farm Curve
  "C 68 168,82 170,92 162 " +
  "L 108 150 " +
  // Village hairpin
  "C 118 142,128 144,134 156 " +
  "L 138 168 " +
  "C 142 178,154 180,162 172 " +
  // The Loop into Aintree
  "L 174 156 " +
  "C 180 146,176 134,164 132 " +
  // Wellington Straight
  "L 130 124 " +
  // Brooklands left
  "C 118 120,114 110,124 102 " +
  // Luffield (long left)
  "L 142 92 " +
  "C 154 84,150 70,136 68 " +
  // Woodcote sweep onto the back of the pit straight (old start area)
  "L 116 70 " +
  // Maggotts entry (high-speed left)
  "C 106 70,100 80,108 90 " +
  // Becketts (right-left-right)
  "L 124 100 " +
  "L 134 90 " +
  "L 146 100 " +
  // Chapel sweep onto Hangar Straight
  "C 154 106,168 108,180 102 " +
  "L 220 86 " +
  // Stowe (heavy braking right)
  "C 240 80,254 92,250 110 " +
  // Vale and Club complex
  "L 244 142 " +
  "C 240 158,226 168,210 164 " +
  "L 160 158 " +
  // Back along the Hamilton Straight to start
  "C 120 154,80 152,60 160 Z";

// ────────────────────────────────────────────────────────────────────────────
// MONZA — Autodromo Nazionale Monza
// Signature: long pit straight into Variante del Rettifilo, Curva Grande,
// Variante della Roggia, Lesmo 1 & 2, Variante Ascari, Parabolica.
// ────────────────────────────────────────────────────────────────────────────
const MONZA_PATH =
  // Start-finish straight (top, long)
  "M 40 60 " +
  "L 200 60 " +
  // Variante del Rettifilo (T1 chicane right-left)
  "L 210 70 " +
  "L 204 80 " +
  "L 216 92 " +
  // Curva Grande (long right)
  "C 228 100,242 108,250 124 " +
  "C 256 138,250 152,236 156 " +
  // Variante della Roggia (chicane)
  "L 198 148 " +
  "L 192 158 " +
  "L 178 152 " +
  // Lesmo 1 (right)
  "C 168 148,156 152,150 162 " +
  // Lesmo 2 (right)
  "L 138 168 " +
  "C 128 174,116 168,114 158 " +
  // Curva del Serraglio onto back straight
  "L 110 142 " +
  // Variante Ascari (left-right-left)
  "L 96 138 " +
  "L 100 126 " +
  "L 86 122 " +
  "L 90 110 " +
  // Curva del Parabolica (signature long right onto the start straight)
  "C 76 104,56 110,46 124 " +
  "C 32 142,28 100,28 88 " +
  "L 28 76 " +
  "C 28 66,32 60,40 60 Z";

// ────────────────────────────────────────────────────────────────────────────
// SPA — Circuit de Spa-Francorchamps
// Signature: La Source hairpin at the top, the famous Eau Rouge / Raidillon
// climb, the long Kemmel Straight, Les Combes complex, Pouhon double-left,
// Stavelot, Blanchimont, and the Bus Stop chicane back to the grid.
// ────────────────────────────────────────────────────────────────────────────
const SPA_PATH =
  // Start-finish + La Source hairpin (top right)
  "M 220 50 " +
  "L 248 50 " +
  "C 258 50,262 60,254 68 " +
  "L 240 78 " +
  // Eau Rouge dip and Raidillon climb (left-right-left at full chat)
  "L 220 92 " +
  "L 210 84 " +
  "L 198 96 " +
  // Kemmel Straight (long descent)
  "L 120 130 " +
  // Les Combes (right-left-right chicane)
  "L 108 124 " +
  "L 96 132 " +
  "L 92 122 " +
  // Bruxelles + Speakers Corner
  "C 84 118,72 124,70 134 " +
  // Pouhon (very fast double-left)
  "L 64 152 " +
  "C 60 164,68 174,78 172 " +
  // Fagnes / Stavelot
  "L 116 166 " +
  "C 130 164,144 170,150 182 " +
  // Curve at Paul Frère
  "L 162 188 " +
  "C 174 192,188 188,194 178 " +
  // Blanchimont (very fast left)
  "L 210 158 " +
  "C 222 144,228 124,222 110 " +
  // Bus Stop chicane
  "L 218 96 " +
  "L 228 90 " +
  "L 222 80 " +
  "L 232 74 " +
  // Final left onto the start straight
  "C 238 68,238 56,220 50 Z";

// ────────────────────────────────────────────────────────────────────────────
// BARCELONA — Circuit de Barcelona-Catalunya
// Signature: long start-finish, T1 Elf right, T2 Renault, T3 Repsol sweep,
// long Wurth back straight, T10 hairpin, T13-14 chicane, Caixa final.
// ────────────────────────────────────────────────────────────────────────────
const BARCELONA_PATH =
  // Start-finish (long, heading east)
  "M 30 100 " +
  "L 180 100 " +
  // T1 (Elf, fast right)
  "C 196 100,206 110,202 124 " +
  // T2 (Renault, left)
  "L 196 134 " +
  // T3 (Repsol, long right sweep)
  "C 200 148,216 154,232 148 " +
  // T4 (Repsol exit)
  "L 250 138 " +
  "C 260 132,260 120,250 116 " +
  // Sector 1 / 2 split — short straight
  "L 230 110 " +
  "C 222 106,222 96,232 92 " +
  // T5 (Seat, right)
  "L 248 86 " +
  "C 258 82,258 70,248 66 " +
  // T6 (Wurth back straight start)
  "L 220 62 " +
  "C 208 60,200 50,200 40 " +
  // Wurth long back straight
  "L 200 30 " +
  // T7-T9 esses descending
  "C 200 22,190 18,180 22 " +
  "L 150 32 " +
  "C 138 36,132 46,138 56 " +
  // T10 (la Caixa hairpin)
  "L 152 70 " +
  "C 160 78,156 90,144 92 " +
  // T11 (Banc Sabadell)
  "L 110 92 " +
  "C 96 92,86 102,90 116 " +
  // T12 (Europcar) and T13 (New Holland chicane)
  "L 96 132 " +
  "C 102 142,96 152,84 152 " +
  "L 60 148 " +
  // T14-T15 (Caixa Bank) sweep back to start
  "C 44 146,32 132,32 116 " +
  "L 30 100 Z";

// ────────────────────────────────────────────────────────────────────────────
// HUNGARY — Hungaroring
// Twisty, no real straights. T1 (right downhill), T2 (left), T3 (left),
// T4 mid-sector loop, T6-7 chicane, T11 hairpin, T13-14 final esses.
// ────────────────────────────────────────────────────────────────────────────
const HUNGARY_PATH =
  // Start-finish (descending into T1)
  "M 50 60 " +
  "L 130 70 " +
  // T1 downhill right
  "C 148 74,158 64,156 50 " +
  // T2 left
  "L 154 38 " +
  "C 152 26,166 22,176 30 " +
  // T3 long left
  "C 188 40,196 56,186 70 " +
  // T4 right
  "L 174 84 " +
  "C 168 92,176 102,186 100 " +
  // T5 acceleration zone (back-half straight surrogate)
  "L 232 96 " +
  "C 250 94,260 110,250 124 " +
  // T6-7 right-left chicane
  "L 232 134 " +
  "L 240 144 " +
  "L 226 154 " +
  // T8 left and T9 right sweep
  "C 216 162,200 162,190 154 " +
  "L 170 142 " +
  "C 160 136,148 144,148 156 " +
  // T11 hairpin (180° left)
  "L 148 168 " +
  "C 148 180,134 184,124 178 " +
  // T12 right entry into final esses
  "L 100 168 " +
  "C 88 162,76 168,74 180 " +
  // T13-14 left-right
  "L 70 192 " +
  "L 60 184 " +
  "L 50 192 " +
  "L 42 180 " +
  // Back up to grid
  "C 36 168,40 152,52 148 " +
  "L 70 140 " +
  "C 82 136,86 124,78 116 " +
  "L 50 100 " +
  "C 40 92,40 76,50 60 Z";

// ────────────────────────────────────────────────────────────────────────────
// MEXICO CITY — Autódromo Hermanos Rodríguez
// Signature: long pit straight, T1 sequence right-left-right, the stadium
// section through Foro Sol, Peraltada-style exit back to the grid.
// ────────────────────────────────────────────────────────────────────────────
const MEXICO_PATH =
  // Pit straight (top)
  "M 40 50 " +
  "L 200 50 " +
  // T1 right
  "C 218 50,230 60,228 78 " +
  // T2-T3 left-right
  "L 220 90 " +
  "L 234 100 " +
  "L 222 112 " +
  "C 214 120,222 132,234 130 " +
  // Mid-sector right turn into back straight
  "L 250 124 " +
  "C 260 122,260 138,248 142 " +
  "L 220 152 " +
  // Stadium entry (slow corners through Foro Sol)
  "C 208 156,198 152,194 142 " +
  "L 186 130 " +
  "L 176 138 " +
  "L 164 128 " +
  "L 152 136 " +
  "L 140 128 " +
  // Peraltada (banked long right)
  "C 124 130,112 142,108 158 " +
  "L 100 172 " +
  "C 94 184,80 184,72 174 " +
  "L 60 158 " +
  "C 52 146,40 144,30 152 " +
  "L 22 138 " +
  "C 14 124,18 108,32 100 " +
  "L 50 92 " +
  "C 60 88,60 76,50 72 " +
  "L 36 64 " +
  "C 28 58,32 50,40 50 Z";

// ────────────────────────────────────────────────────────────────────────────
// AUSTRIA — Red Bull Ring
// Short lap, three big straights with hairpins between, scenic Spielberg.
// ────────────────────────────────────────────────────────────────────────────
const AUSTRIA_PATH =
  "M 60 160 " +
  "L 100 110 " +
  "C 110 96,128 96,138 110 " +
  "L 150 130 " +
  "C 160 144,180 144,190 130 " +
  "L 232 70 " +
  "C 244 56,260 64,256 82 " +
  "L 240 112 " +
  "C 232 124,240 138,254 138 " +
  "C 264 138,264 152,254 156 " +
  "L 220 168 " +
  "C 200 174,180 174,162 168 " +
  "L 130 158 " +
  "C 110 154,90 162,80 178 " +
  "L 60 192 " +
  "C 48 198,38 190,42 178 " +
  "L 60 160 Z";

// ────────────────────────────────────────────────────────────────────────────
// SINGAPORE — Marina Bay Street Circuit
// Long, twisty street circuit with the iconic Anderson Bridge crossing.
// ────────────────────────────────────────────────────────────────────────────
const SINGAPORE_PATH =
  "M 40 100 " +
  "L 80 100 " +
  "L 80 70 " +
  "L 140 70 " +
  "C 152 70,158 84,150 92 " +
  "L 140 100 " +
  "L 180 100 " +
  "L 180 60 " +
  "L 220 60 " +
  "C 240 60,250 80,240 96 " +
  "L 226 110 " +
  "L 240 122 " +
  "C 252 134,244 154,228 154 " +
  "L 200 154 " +
  "L 200 130 " +
  "L 170 130 " +
  "L 170 160 " +
  "L 130 160 " +
  "L 130 130 " +
  "L 100 130 " +
  "L 100 170 " +
  "L 60 170 " +
  "C 44 170,36 158,40 142 " +
  "L 40 100 Z";

// ────────────────────────────────────────────────────────────────────────────
// FALLBACK — Generic stylised oval for circuits without a dedicated layout
// ────────────────────────────────────────────────────────────────────────────
const GENERIC_OVAL_PATH =
  "M 40 100 " +
  "C 40 60,80 40,140 40 " +
  "C 200 40,240 60,240 100 " +
  "C 240 140,200 160,140 160 " +
  "C 80 160,40 140,40 100 Z";

// ────────────────────────────────────────────────────────────────────────────
// Layout table — keyed by the `circuit_id` field that /api/v1/sessions emits.
// Add a new circuit by dropping a new entry here. The viewBox is fixed at
// 280×200 so every layout fits the same SVG container without rescaling.
// ────────────────────────────────────────────────────────────────────────────
export const TRACK_LAYOUTS: Record<string, TrackLayout> = {
  monaco: {
    id: "monaco",
    displayName: "Circuit de Monaco",
    viewBox: "0 0 280 200",
    path: MONACO_PATH,
    startFinishAt: 0.0,
    direction: "cw",
  },
  bahrain: {
    id: "bahrain",
    displayName: "Bahrain International Circuit",
    viewBox: "0 0 280 200",
    path: BAHRAIN_PATH,
    startFinishAt: 0.0,
    direction: "cw",
  },
  silverstone: {
    id: "silverstone",
    displayName: "Silverstone Circuit",
    viewBox: "0 0 280 200",
    path: SILVERSTONE_PATH,
    aliases: ["british"],
    startFinishAt: 0.0,
    direction: "cw",
  },
  monza: {
    id: "monza",
    displayName: "Autodromo Nazionale Monza",
    viewBox: "0 0 280 200",
    path: MONZA_PATH,
    aliases: ["italian"],
    startFinishAt: 0.0,
    direction: "cw",
  },
  spa: {
    id: "spa",
    displayName: "Circuit de Spa-Francorchamps",
    viewBox: "0 0 280 200",
    path: SPA_PATH,
    aliases: ["belgian"],
    startFinishAt: 0.0,
    direction: "cw",
  },
  barcelona: {
    id: "barcelona",
    displayName: "Circuit de Barcelona-Catalunya",
    viewBox: "0 0 280 200",
    path: BARCELONA_PATH,
    aliases: ["spanish", "catalunya"],
    startFinishAt: 0.0,
    direction: "cw",
  },
  hungary: {
    id: "hungary",
    displayName: "Hungaroring",
    viewBox: "0 0 280 200",
    path: HUNGARY_PATH,
    aliases: ["hungarian", "hungaroring"],
    startFinishAt: 0.0,
    direction: "cw",
  },
  mexico_city: {
    id: "mexico_city",
    displayName: "Autódromo Hermanos Rodríguez",
    viewBox: "0 0 280 200",
    path: MEXICO_PATH,
    aliases: ["mexican", "mexico"],
    startFinishAt: 0.0,
    direction: "cw",
  },
  austrian: {
    id: "austrian",
    displayName: "Red Bull Ring",
    viewBox: "0 0 280 200",
    path: AUSTRIA_PATH,
    aliases: ["austria", "red_bull_ring"],
    startFinishAt: 0.0,
    direction: "cw",
  },
  singapore: {
    id: "singapore",
    displayName: "Marina Bay Street Circuit",
    viewBox: "0 0 280 200",
    path: SINGAPORE_PATH,
    aliases: ["marina_bay"],
    startFinishAt: 0.0,
    direction: "cw",
  },
};

export const FALLBACK_TRACK_LAYOUT: TrackLayout = {
  id: "generic",
  displayName: "Generic Circuit (no custom layout)",
  viewBox: "0 0 280 200",
  path: GENERIC_OVAL_PATH,
  startFinishAt: 0.0,
  direction: "cw",
};

// Build a flat alias → canonical-id map once at module load.
const ALIAS_TO_ID: Record<string, string> = (() => {
  const map: Record<string, string> = {};
  for (const layout of Object.values(TRACK_LAYOUTS)) {
    map[layout.id] = layout.id;
    for (const alias of layout.aliases ?? []) {
      map[alias] = layout.id;
    }
  }
  return map;
})();

/** Resolve a circuit_id (or alias / session_id prefix) to a TrackLayout.
 *  Returns the fallback generic oval when no match is found. */
export function getTrackLayout(circuitId: string | undefined | null): {
  layout: TrackLayout;
  isFallback: boolean;
} {
  if (!circuitId) {
    return { layout: FALLBACK_TRACK_LAYOUT, isFallback: true };
  }
  const key = circuitId.toLowerCase().trim();
  const resolvedId = ALIAS_TO_ID[key];
  if (resolvedId && TRACK_LAYOUTS[resolvedId]) {
    return { layout: TRACK_LAYOUTS[resolvedId], isFallback: false };
  }
  return { layout: FALLBACK_TRACK_LAYOUT, isFallback: true };
}

/** List of supported circuit ids (used by the UI to show coverage). */
export const SUPPORTED_CIRCUITS = Object.keys(TRACK_LAYOUTS);
