import { describe, expect, it } from "vitest";
import { screenshotProblem } from "@/lib/submission";

describe("screenshotProblem", () => {
  it("accepts no file and PNG screenshots up to 10 MB", () => {
    expect(screenshotProblem(null)).toBeNull();
    expect(screenshotProblem({ name: "post.png", type: "image/png", size: 1000 })).toBeNull();
  });

  it("refuses other formats and oversized files, in plain Polish", () => {
    expect(screenshotProblem({ name: "post.jpg", type: "image/jpeg", size: 10 })).toBe(
      "Zrzut ekranu musi być plikiem PNG.",
    );
    expect(screenshotProblem({ name: "a.png", type: "image/png", size: 11 * 2 ** 20 })).toBe(
      "Zrzut ekranu jest większy niż 10 MB.",
    );
  });
});
