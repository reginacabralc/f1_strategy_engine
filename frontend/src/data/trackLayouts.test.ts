import { describe, it, expect } from "vitest";
import {
  FALLBACK_TRACK_LAYOUT,
  SUPPORTED_CIRCUITS,
  TRACK_LAYOUTS,
  getTrackLayout,
} from "./trackLayouts";

describe("trackLayouts", () => {
  it("exports at least the six priority circuits", () => {
    const required = [
      "monaco",
      "bahrain",
      "silverstone",
      "monza",
      "spa",
      "barcelona",
    ];
    for (const id of required) {
      expect(TRACK_LAYOUTS[id], `missing layout for ${id}`).toBeDefined();
    }
  });

  it("every layout has the same viewBox so paths swap cleanly", () => {
    const viewBoxes = new Set(
      Object.values(TRACK_LAYOUTS).map((l) => l.viewBox),
    );
    expect(viewBoxes.size).toBe(1);
    expect([...viewBoxes][0]).toBe("0 0 280 200");
  });

  it("every path is closed (ends with Z)", () => {
    for (const layout of Object.values(TRACK_LAYOUTS)) {
      expect(
        layout.path.trim().endsWith("Z"),
        `${layout.id} path is not closed`,
      ).toBe(true);
    }
    expect(FALLBACK_TRACK_LAYOUT.path.trim().endsWith("Z")).toBe(true);
  });

  it("every path starts with a Move (M) command", () => {
    for (const layout of Object.values(TRACK_LAYOUTS)) {
      expect(layout.path.trim().startsWith("M ")).toBe(true);
    }
  });

  it("getTrackLayout returns the canonical layout for known ids", () => {
    const { layout, isFallback } = getTrackLayout("monaco");
    expect(layout.id).toBe("monaco");
    expect(isFallback).toBe(false);
  });

  it("getTrackLayout resolves aliases (italian → monza, british → silverstone)", () => {
    expect(getTrackLayout("italian").layout.id).toBe("monza");
    expect(getTrackLayout("british").layout.id).toBe("silverstone");
    expect(getTrackLayout("spanish").layout.id).toBe("barcelona");
    expect(getTrackLayout("belgian").layout.id).toBe("spa");
  });

  it("getTrackLayout is case-insensitive and trims whitespace", () => {
    expect(getTrackLayout("  MONACO  ").layout.id).toBe("monaco");
    expect(getTrackLayout("Bahrain").layout.id).toBe("bahrain");
  });

  it("getTrackLayout returns the fallback for unknown ids", () => {
    const { layout, isFallback } = getTrackLayout("not_a_real_track");
    expect(isFallback).toBe(true);
    expect(layout.id).toBe("generic");
  });

  it("getTrackLayout returns the fallback for null / undefined / empty", () => {
    expect(getTrackLayout(null).isFallback).toBe(true);
    expect(getTrackLayout(undefined).isFallback).toBe(true);
    expect(getTrackLayout("").isFallback).toBe(true);
  });

  it("SUPPORTED_CIRCUITS matches the keys of TRACK_LAYOUTS", () => {
    expect([...SUPPORTED_CIRCUITS].sort()).toEqual(
      Object.keys(TRACK_LAYOUTS).sort(),
    );
  });
});
