import { describe, expect, it } from "vitest";
import { delta, paperLabel, pct, relativeTime, viewerLink } from "./format";

describe("format helpers", () => {
  it("labels papers the way the backend does", () => {
    expect(paperLabel("Patrick Lewis, Ethan Perez", 2020)).toBe("Lewis et al. · 2020");
    expect(paperLabel("Ada Lovelace", null)).toBe("Lovelace · n.d.");
  });
  it("formats percentages and missing values", () => {
    expect(pct(0.923, 1)).toBe("92.3%");
    expect(pct(null)).toBe("n/a");
  });
  it("shows a signed difference, or nothing when a run is missing", () => {
    expect(delta(0.9, 0.86)).toBe("+0.04");
    expect(delta(0.8, 0.9, true)).toBe("−10.0%");
    expect(delta(0.9, undefined)).toBeNull();
  });
  it("builds viewer links with the page and quote", () => {
    expect(viewerLink(3, 8, "exact quote")).toBe("/papers/3?page=8&q=exact+quote");
    expect(viewerLink(3)).toBe("/papers/3");
  });
  it("describes elapsed time", () => {
    const now = Date.parse("2026-01-02T12:00:00Z");
    expect(relativeTime("2026-01-02T11:59:50Z", now)).toBe("just now");
    expect(relativeTime("2026-01-02T09:00:00Z", now)).toBe("3 h ago");
  });
});
