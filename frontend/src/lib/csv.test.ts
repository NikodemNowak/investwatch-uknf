import { describe, expect, it } from "vitest";
import { csvField, csvFilename } from "@/lib/csv";

describe("csvFilename", () => {
  it("uses the local wall-clock time, not UTC", () => {
    // Built from local fields: the name matches the clock the analyst sees in any time zone.
    expect(csvFilename("do-przejrzenia", new Date(2026, 10, 21, 23, 30))).toBe(
      "investwatch-do-przejrzenia-20261121-2330.csv",
    );
  });
});

describe("csvField", () => {
  it("quotes separators and quotes", () => {
    expect(csvField('a;"b"')).toBe('"a;""b"""');
  });
});
