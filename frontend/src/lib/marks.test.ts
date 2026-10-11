import { describe, expect, it } from "vitest";
import { addMark, overlaps, removeMarks, segments, shiftMarks, wordCount } from "./marks";

describe("shiftMarks", () => {
  const text = "One two three four five";
  const marks = [{ start: 8, end: 13 }]; // "three"

  it("keeps a mark on the same words when text is inserted before it", () => {
    const next = "Zero. " + text;
    const out = shiftMarks(text, next, marks);
    expect(next.slice(out[0].start, out[0].end)).toBe("three");
  });
  it("leaves a mark alone when text is appended after it", () => {
    const next = text + " six";
    expect(shiftMarks(text, next, marks)).toEqual(marks);
  });
  it("drops a mark whose words were deleted", () => {
    const next = "One two  four five";
    expect(shiftMarks(text, next, marks)).toEqual([]);
  });
  it("is a no-op when nothing changed", () => {
    expect(shiftMarks(text, text, marks)).toBe(marks);
  });
});

describe("mark editing", () => {
  it("merges overlapping marks so they never overlap", () => {
    expect(addMark([{ start: 0, end: 5 }], { start: 3, end: 9 })).toEqual([{ start: 0, end: 9 }]);
  });
  it("keeps separate marks apart", () => {
    expect(addMark([{ start: 0, end: 3 }], { start: 6, end: 9 })).toEqual([{ start: 0, end: 3 }, { start: 6, end: 9 }]);
  });
  it("removes only marks touched by the selection", () => {
    const m = [{ start: 0, end: 3 }, { start: 6, end: 9 }];
    expect(removeMarks(m, { start: 7, end: 8 })).toEqual([{ start: 0, end: 3 }]);
    expect(overlaps(m, { start: 3, end: 6 })).toBe(false);
  });
  it("splits text into plain and marked runs", () => {
    expect(segments("abcdef", [{ start: 2, end: 4 }])).toEqual([
      { text: "ab", marked: false }, { text: "cd", marked: true }, { text: "ef", marked: false },
    ]);
  });
  it("counts words", () => {
    expect(wordCount("  a  b c ")).toBe(3);
    expect(wordCount("")).toBe(0);
  });
});
