import { describe, expect, it } from "vitest";
import { DEMO_HOURS } from "@/lib/pregao/demo";
import { HouseHoursSchema } from "@/lib/pregao/schemas";
import { PRE_OPEN_MIN, houseStatus, isAlwaysOpen, localParts, windowsByDay, zonedToUtc } from "@/lib/pregao/hours";
import type { HouseHours } from "@/lib/pregao/types";

const utc = (y: number, mo: number, d: number, h = 0, mi = 0) => new Date(Date.UTC(y, mo - 1, d, h, mi));
const iso = (y: number, mo: number, d: number, h = 0, mi = 0) => utc(y, mo, d, h, mi).toISOString();

describe("localParts", () => {
  it("converts a UTC instant into wall-clock parts of the zone", () => {
    // 2026-11-02 12:00Z is Monday 09:00 in Asunción (UTC−3).
    expect(localParts(utc(2026, 11, 2, 12, 0), "America/Asuncion")).toEqual({ year: 2026, month: 11, day: 2, isoWeekday: 1, minutes: 9 * 60 });
  });
  it("crosses the date line correctly and uses ISO weekdays (7 = Sunday)", () => {
    // 2026-11-02 02:30Z is still Sunday 23:30 of 2026-11-01 in Asunción.
    expect(localParts(utc(2026, 11, 2, 2, 30), "America/Asuncion")).toEqual({ year: 2026, month: 11, day: 1, isoWeekday: 7, minutes: 23 * 60 + 30 });
  });
  it("returns null for a zone Intl rejects", () => {
    expect(localParts(utc(2026, 11, 2), "Nope/Zone")).toBeNull();
  });
});

describe("zonedToUtc", () => {
  it("maps a wall-clock time of the zone to the UTC instant", () => {
    expect(zonedToUtc(2026, 11, 2, 7, 30, "America/Asuncion").toISOString()).toBe(iso(2026, 11, 2, 10, 30));
    expect(zonedToUtc(2026, 11, 2, 0, 0, "UTC").toISOString()).toBe(iso(2026, 11, 2));
  });
  it("treats 24:00 as midnight of the next day", () => {
    expect(zonedToUtc(2026, 11, 2, 24, 0, "America/Asuncion").toISOString()).toBe(iso(2026, 11, 3, 3, 0));
  });
  it("handles a daylight-saving transition day without drifting", () => {
    // Santiago: 2026-09-06 02:00 local jumps to 03:00 (UTC−4 → UTC−3).
    expect(zonedToUtc(2026, 9, 6, 12, 0, "America/Santiago").toISOString()).toBe(iso(2026, 9, 6, 15, 0));
    expect(zonedToUtc(2026, 9, 5, 12, 0, "America/Santiago").toISOString()).toBe(iso(2026, 9, 5, 16, 0));
  });
});

describe("isAlwaysOpen", () => {
  it("is true only for 7 days from 00:00 to 24:00", () => {
    expect(isAlwaysOpen(DEMO_HOURS.ueno)).toBe(true);
    expect(isAlwaysOpen(DEMO_HOURS.chaco)).toBe(false);
    expect(isAlwaysOpen({ ...DEMO_HOURS.ueno, days: [1, 2, 3, 4, 5, 6] })).toBe(false);
  });
});

describe("windowsByDay", () => {
  it("merges the main window with the schedule windows, one per ISO day", () => {
    const m = windowsByDay(DEMO_HOURS.chaco);
    expect([...m.keys()].sort()).toEqual([1, 2, 3, 4, 5, 6]);
    expect(m.get(1)).toEqual([7 * 60 + 15, 16 * 60]);
    expect(m.get(6)).toEqual([7 * 60 + 15, 13 * 60]);
    expect(m.has(7)).toBe(false);
  });
});

describe("houseStatus: chaco verificado (Adrián Jara, America/Asuncion)", () => {
  it("exports PRE_OPEN_MIN = 30", () => {
    expect(PRE_OPEN_MIN).toBe(30);
  });
  it("is open on Monday 09:00 local, 07:15–16:00", () => {
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 2, 12, 0))).toEqual({
      status: "open",
      opens_at: iso(2026, 11, 2, 10, 15),
      closes_at: iso(2026, 11, 2, 19, 0),
      next_change_at: iso(2026, 11, 2, 19, 0),
    });
  });
  it("is pre-open on Monday 07:00 local (15 min before 07:15)", () => {
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 2, 10, 0))).toEqual({
      status: "pre",
      opens_at: iso(2026, 11, 2, 10, 15),
      closes_at: iso(2026, 11, 2, 19, 0),
      next_change_at: iso(2026, 11, 2, 10, 15),
    });
  });
  it("is closed on Sunday noon (no Sunday window) and points to Monday's opening", () => {
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 1, 15, 0))).toEqual({
      status: "closed",
      opens_at: iso(2026, 11, 2, 10, 15),
      closes_at: iso(2026, 11, 2, 19, 0),
      next_change_at: iso(2026, 11, 2, 9, 45),
    });
  });
  it("is closed after closing time and points to the next day", () => {
    // Monday 18:00 local → Tuesday.
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 2, 21, 0))).toMatchObject({ status: "closed", opens_at: iso(2026, 11, 3, 10, 15) });
  });
  it("is closed before pre-open on a working day and points to the same day", () => {
    // Monday 06:00 local.
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 2, 9, 0))).toMatchObject({ status: "closed", opens_at: iso(2026, 11, 2, 10, 15), next_change_at: iso(2026, 11, 2, 9, 45) });
  });
  it("ueno is always open with null times", () => {
    expect(houseStatus(DEMO_HOURS.ueno, utc(2026, 11, 1, 3, 0))).toEqual({ status: "open", opens_at: null, closes_at: null, next_change_at: null });
  });
  it("a source without hours is unknown", () => {
    const none = { status: "unknown", opens_at: null, closes_at: null, next_change_at: null };
    expect(houseStatus(undefined, utc(2026, 11, 2, 12))).toEqual(none);
    expect(houseStatus(null, utc(2026, 11, 2, 12))).toEqual(none);
  });
  it("an invalid tz is unknown", () => {
    expect(houseStatus({ ...DEMO_HOURS.chaco, tz: "Nope/Zone" }, utc(2026, 11, 2, 12)).status).toBe("unknown");
  });
  it("empty days and no schedule is closed with null times", () => {
    expect(houseStatus({ ...DEMO_HOURS.chaco, days: [], schedule: undefined }, utc(2026, 11, 2, 12))).toEqual({
      status: "closed",
      opens_at: null,
      closes_at: null,
      next_change_at: null,
    });
  });
});

describe("houseStatus: sábado à tarde (janela de schedule)", () => {
  it("is open on Saturday until 13:00 local (exclusive): 12:59 open", () => {
    // Saturday 2026-11-07 15:59Z = 12:59 local.
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 7, 15, 59))).toEqual({
      status: "open",
      opens_at: iso(2026, 11, 7, 10, 15),
      closes_at: iso(2026, 11, 7, 16, 0),
      next_change_at: iso(2026, 11, 7, 16, 0),
    });
  });
  it("is closed at 13:00 local on Saturday and points to Monday", () => {
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 7, 16, 0))).toEqual({
      status: "closed",
      opens_at: iso(2026, 11, 9, 10, 15),
      closes_at: iso(2026, 11, 9, 19, 0),
      next_change_at: iso(2026, 11, 9, 9, 45),
    });
  });
  it("is pre-open on Saturday at 06:45 local and closed at 06:44", () => {
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 7, 9, 45)).status).toBe("pre");
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 7, 9, 44)).status).toBe("closed");
  });
  it("does not reopen on Saturday afternoon after the 13:00 close", () => {
    // Saturday 14:00 local.
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 7, 17, 0)).opens_at).toBe(iso(2026, 11, 9, 10, 15));
  });
  it("uses the schedule window only on its own days (Sunday closed for chaco)", () => {
    // Sunday 11:00 local.
    expect(houseStatus(DEMO_HOURS.chaco, utc(2026, 11, 8, 14, 0)).status).toBe("closed");
  });
});

describe("houseStatus: outras casas verificadas", () => {
  it("bcp is an apuração window on weekdays 08:30–13:00: Saturday points to Monday", () => {
    // Saturday 2026-11-07 12:00Z = 09:00 local.
    expect(houseStatus(DEMO_HOURS.bcp, utc(2026, 11, 7, 12, 0))).toMatchObject({ status: "closed", opens_at: iso(2026, 11, 9, 11, 30), next_change_at: iso(2026, 11, 9, 11, 0) });
  });
  it("bcp is open on a weekday at 10:00 local and closed at 13:00 local", () => {
    expect(houseStatus(DEMO_HOURS.bcp, utc(2026, 11, 2, 13, 0)).status).toBe("open");
    expect(houseStatus(DEMO_HOURS.bcp, utc(2026, 11, 2, 16, 0)).status).toBe("closed");
  });
});

describe("HouseHoursSchema", () => {
  it("accepts the verified shape with schedule and procedure fields", () => {
    expect(HouseHoursSchema.safeParse(DEMO_HOURS.chaco).success).toBe(true);
  });
  it("rejects a schedule window with empty days or malformed hours", () => {
    const base: HouseHours = { tz: "UTC", days: [1], opens: "08:00", closes: "09:00" };
    expect(HouseHoursSchema.safeParse({ ...base, schedule: [{ days: [], opens: "08:00", closes: "09:00" }] }).success).toBe(false);
    expect(HouseHoursSchema.safeParse({ ...base, schedule: [{ days: [6], opens: "8:00", closes: "09:00" }] }).success).toBe(false);
    expect(HouseHoursSchema.safeParse({ ...base, schedule: [{ days: [6], opens: "08:00", closes: "09:00" }] }).success).toBe(true);
  });
});
