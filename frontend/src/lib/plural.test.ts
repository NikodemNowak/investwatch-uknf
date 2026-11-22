import { describe, expect, it } from "vitest";
import { count, formatInt, plural } from "@/lib/plural";
import { nouns } from "@/i18n/pl";

describe("plural", () => {
  it("follows Polish plural rules", () => {
    expect(count(1, nouns.problem)).toBe("1 problem");
    expect(count(3, nouns.problem)).toBe("3 problemy");
    expect(count(5, nouns.problem)).toBe("5 problemów");
    expect(count(12, nouns.problem)).toBe("12 problemów");
    expect(count(22, nouns.problem)).toBe("22 problemy");
    expect(plural(0, nouns.source)).toBe("źródeł");
  });
  it("groups thousands with a non-breaking space, also for 4 digits", () => {
    expect(formatInt(1284)).toBe("1 284");
    expect(formatInt(757)).toBe("757");
  });
});
