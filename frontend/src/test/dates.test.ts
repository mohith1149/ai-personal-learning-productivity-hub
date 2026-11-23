import { describe, expect, it } from "vitest";
import { addDays, daysBetween, describeDue, formatDay, todayIn } from "../lib/dates";

describe("todayIn", () => {
  it("uses the given time zone, not the machine's", () => {
    const instant = new Date("2026-11-23T19:00:00Z"); // 00:30 on the 24th in Kolkata, still the 23rd in UTC
    expect(todayIn("Asia/Kolkata", instant)).toBe("2026-11-24");
    expect(todayIn("UTC", instant)).toBe("2026-11-23");
    expect(todayIn("America/Los_Angeles", instant)).toBe("2026-11-23");
  });

  it("falls back instead of crashing on a bad zone name", () => {
    expect(todayIn("Not/AZone", new Date("2026-11-23T12:00:00Z"))).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("date arithmetic", () => {
  it("adds days across month, year and leap boundaries", () => {
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it("counts whole days, including over a daylight-saving change", () => {
    expect(daysBetween("2026-11-23", "2026-11-26")).toBe(3);
    expect(daysBetween("2026-11-26", "2026-11-23")).toBe(-3);
    expect(daysBetween("2026-03-28", "2026-03-30")).toBe(2); // EU DST starts on the 29th
  });
});

describe("formatDay / describeDue", () => {
  const today = "2026-11-23";
  it("uses friendly words near today and a date further away", () => {
    expect(formatDay("2026-11-23", today)).toBe("Today");
    expect(formatDay("2026-11-24", today)).toBe("Tomorrow");
    expect(formatDay("2026-11-22", today)).toBe("Yesterday");
    expect(formatDay("2026-12-02", today)).toMatch(/Wed.*2 Dec/);
    expect(formatDay("2027-01-05", today)).toMatch(/2027/);
  });

  it("has no due text without a due date", () => {
    expect(describeDue({ due_date: null, due_time: null, is_overdue: false }, today)).toBeNull();
  });

  it("describes overdue and upcoming differently, trusting the server's overdue flag", () => {
    expect(describeDue({ due_date: "2026-11-20", due_time: null, is_overdue: true }, today)).toEqual({ text: "3 days overdue", overdue: true });
    expect(describeDue({ due_date: "2026-11-22", due_time: null, is_overdue: true }, today)?.text).toBe("1 day overdue");
    expect(describeDue({ due_date: today, due_time: "09:30", is_overdue: true }, today)?.text).toBe("Overdue (was due 09:30)");
    expect(describeDue({ due_date: today, due_time: "17:00", is_overdue: false }, today)).toEqual({ text: "Today 17:00", overdue: false });
    // A past date the server says is NOT overdue (e.g. completed) is shown plainly, never as overdue.
    expect(describeDue({ due_date: "2026-11-01", due_time: null, is_overdue: false }, today)?.overdue).toBe(false);
  });
});
