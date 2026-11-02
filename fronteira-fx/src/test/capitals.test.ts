import { describe, expect, it } from "vitest";
import { capitalOptions } from "@/lib/api/capitals";
import { DEMO_CAPITALS } from "@/lib/api/demo-data";

describe("capitalOptions", () => {
  it("uses the demo capitals only in demo mode", () => {
    expect(capitalOptions("demo", 5000)).toEqual(DEMO_CAPITALS);
  });
  it("real and simulation modes offer the standard amounts plus the user's default capital, sorted and unique", () => {
    expect(capitalOptions("real", 5000)).toEqual([5000, 10000, 25000, 50000]);
    expect(capitalOptions("simulation", 7500)).toEqual([5000, 7500, 10000, 25000, 50000]);
    expect(capitalOptions("real", 0)).toEqual([5000, 10000, 25000, 50000]);
  });
});
