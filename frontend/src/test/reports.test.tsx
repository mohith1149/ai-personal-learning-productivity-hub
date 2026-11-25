import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { addDays } from "../lib/dates";
import { niceTicks, formatMinutes, MINUTE_STEPS } from "../pages/reports/charts";
import { installFakeApi, TODAY } from "./fakeApi";
import { buildReport, installFakeReports, type FakeReports } from "./fakeReports";
import { renderAt } from "./render";

async function open(seed: Partial<FakeReports> = {}) {
  const fake = installFakeApi();
  const store = installFakeReports(fake, seed);
  renderAt("/reports");
  await screen.findByRole("heading", { name: "Reports", level: 1 });
  await screen.findByRole("list", { name: "Totals" });
  return { fake, store };
}

const card = (name: string) => screen.findByRole("region", { name });

describe("reports page", () => {
  it("shows this week by default and says what each total is", async () => {
    const { store } = await open();
    expect(store.requests).toEqual(["/api/reports/weekly?"]);
    const r = buildReport("week", null);
    const totals = screen.getByRole("list", { name: "Totals" });
    expect(within(totals).getByText("Items finished").nextSibling).toHaveTextContent(String(r.totals.items_done));
    expect(within(totals).getByText("Study time").nextSibling).toHaveTextContent(formatMinutes(r.totals.study_minutes));
    expect(within(totals).getByText("Plan completed").nextSibling).toHaveTextContent(`${r.plan.percent}%`);
    expect(within(totals).getByText("Challenge days").nextSibling).toHaveTextContent(String(r.totals.challenge_days));
  });

  it("compares with the same days before, in words and not only colour", async () => {
    await open();
    const r = buildReport("week", null);
    const totals = screen.getByRole("list", { name: "Totals" });
    // the fake makes last week's items 2 higher and study time 30 minutes lower (or zero); project time and habits are equal
    expect(within(totals).getByText("Down 2 vs the same days last week")).toBeInTheDocument();
    expect(within(totals).getByText(`Up ${formatMinutes(Math.min(30, r.totals.study_minutes))} vs the same days last week`)).toBeInTheDocument();
    expect(within(totals).getAllByText("No change vs the same days last week")).toHaveLength(2);
  });

  it("goes to the previous week and back, and cannot go past the current one", async () => {
    const user = userEvent.setup();
    const { store } = await open();
    const next = screen.getByRole("button", { name: "Next week" });
    expect(next).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous week" }));
    await waitFor(() => expect(store.requests).toHaveLength(2));
    expect(store.requests[1]).toMatch(/^\/api\/reports\/weekly\?week_start=\d{4}-\d{2}-\d{2}$/);
    const asked = store.requests[1].split("=")[1];
    expect(asked <= addDays(TODAY, -7)).toBe(true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Next week" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "This week" }));
    await waitFor(() => expect(store.requests).toHaveLength(3));
    expect(store.requests[2]).toBe("/api/reports/weekly?");
    await waitFor(() => expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled());
  });

  it("switches to months and steps back a month", async () => {
    const user = userEvent.setup();
    const { store } = await open();
    await user.click(screen.getByRole("button", { name: "Month" }));
    await waitFor(() => expect(store.requests).toContain("/api/reports/monthly?"));
    await screen.findByRole("button", { name: "Previous month" });
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => expect(store.requests.at(-1)).toMatch(/^\/api\/reports\/monthly\?month=\d{4}-\d{2}$/));
    const asked = store.requests.at(-1)!.split("=")[1];
    expect(asked < TODAY.slice(0, 7)).toBe(true);
    expect(screen.getByRole("button", { name: "Month" })).toHaveAttribute("aria-pressed", "true");
  });

  it("describes every day of every chart to a screen reader, and marks days that have not happened", async () => {
    await open();
    const finished = await card("Finished each day");
    const r = buildReport("week", null);
    const first = r.days[0];
    const expected = `Tasks ${first.tasks_done}, Lessons ${first.lessons_done}, Videos ${first.videos_done}, Roadmap topics ${first.topics_done}`;
    expect(within(finished).getAllByRole("img").map((i) => i.getAttribute("aria-label"))[0]).toContain(expected);
    expect(within(finished).getAllByRole("img")).toHaveLength(7);
    const plan = await card("Plan completed each day");
    const future = r.days.filter((d) => d.date > TODAY);
    if (future.length) expect(within(plan).getAllByRole("img").filter((i) => /Not happened yet/.test(i.getAttribute("aria-label") ?? ""))).toHaveLength(future.length);
  });

  it("has a legend for a chart with several series and none for a single series", async () => {
    await open();
    expect(within(await card("Finished each day")).getByRole("list", { name: "Legend" })).toHaveTextContent("TasksLessonsVideosRoadmap topics");
    expect(within(await card("Time spent each day")).getByRole("list", { name: "Legend" })).toHaveTextContent("StudyProjects");
    expect(within(await card("Plan completed each day")).queryByRole("list", { name: "Legend" })).not.toBeInTheDocument();
  });

  it("offers every number as a table instead of a chart", async () => {
    const user = userEvent.setup();
    await open();
    await user.click(screen.getByRole("button", { name: "Tables" }));
    const table = within(await card("Finished each day")).getByRole("table", { name: "Finished each day" });
    expect(within(table).getAllByRole("row")).toHaveLength(8);                                       // header + 7 days
    expect(within(table).getByRole("columnheader", { name: "Roadmap topics" })).toBeInTheDocument();
    expect(within(await card("Plan completed each day")).getByRole("table")).toBeInTheDocument();
    expect(within(await card("Finished each day")).queryAllByRole("img")).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Charts" }));
    expect(within(await card("Finished each day")).queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the challenge with a name for every status, never colour alone", async () => {
    await open();
    const ch = await card("Daily challenge");
    const days = within(ch).getByRole("list", { name: "Daily challenge by day" });
    const labels = within(days).getAllByRole("listitem").map((li) => li.getAttribute("aria-label") ?? "");
    expect(labels).toHaveLength(7);
    expect(labels.some((l) => /: Completed$/.test(l))).toBe(true);
    for (const name of ["Completed", "Missed", "Excused", "Planned", "Nothing planned"]) expect(within(within(ch).getByRole("list", { name: "Challenge key" })).getByText(name)).toBeInTheDocument();
  });

  it("lists time by project and habit check-ins", async () => {
    await open();
    const p = await card("Time by project");
    expect(within(p).getByText("RAG chatbot")).toBeInTheDocument();
    expect(within(p).getByText("3h")).toBeInTheDocument();
    expect(within(await card("Habits")).getByText("1 day")).toBeInTheDocument();
  });

  it("says plainly when nothing was recorded, and still shows the empty charts", async () => {
    await open({ empty: true });
    expect(await screen.findByRole("status")).toHaveTextContent("Nothing was recorded in this week");
    expect(within(await card("Time by project")).getByText(/No project time was logged/)).toBeInTheDocument();
    expect(within(await card("Habits")).getByText(/No habit was checked off/)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Totals" })).getByText("Nothing was planned")).toBeInTheDocument();
  });

  it("shows a server error with a retry", async () => {
    const fake = installFakeApi();
    const store = installFakeReports(fake, { error: "The report could not be built" });
    renderAt("/reports");
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be built/);
    store.error = null;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("list", { name: "Totals" })).toBeInTheDocument();
  });

  it("is in the sidebar", async () => {
    await open();
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: /Reports/ })).toHaveAttribute("aria-current", "page");
  });
});

describe("chart helpers", () => {
  it("picks clean axis steps", () => {
    expect(niceTicks(0)).toEqual([0, 1]);
    expect(niceTicks(1)).toEqual([0, 1]);
    expect(niceTicks(3)).toEqual([0, 1, 2, 3]);
    expect(niceTicks(87)).toEqual([0, 50, 100]);
    expect(niceTicks(240)).toEqual([0, 100, 200, 300]);
    for (const m of [1, 2, 7, 13, 99, 180, 1234]) {
      const t = niceTicks(m);
      expect(t[0]).toBe(0);
      expect(t.at(-1)! >= m).toBe(true);
      expect(t.length).toBeLessThanOrEqual(6);
      expect(t.every(Number.isInteger)).toBe(true);                    // never "0.5 tasks"
    }
  });

  it("steps minute axes in 15, 30, 60 or 120 minutes, not 50", () => {
    expect(niceTicks(150, MINUTE_STEPS)).toEqual([0, 60, 120, 180]);
    expect(niceTicks(45, MINUTE_STEPS)).toEqual([0, 15, 30, 45]);
    expect(niceTicks(95, MINUTE_STEPS)).toEqual([0, 30, 60, 90, 120]);
    expect(niceTicks(600, MINUTE_STEPS).every((t) => t % 15 === 0)).toBe(true);
  });

  it("formats minutes as people say them", () => {
    expect([0, 5, 59, 60, 90, 125, 180].map(formatMinutes)).toEqual(["0m", "5m", "59m", "1h", "1h 30m", "2h 5m", "3h"]);
  });
});
