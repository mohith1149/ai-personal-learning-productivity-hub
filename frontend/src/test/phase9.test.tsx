import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { setModelChoice } from "../api/assistant";
import { addDays, todayIn } from "../lib/dates";
import { installFakeApi, USER, type Fake } from "./fakeApi";
import { installFakeAssistant } from "./fakeAssistant";
import { installFakeChallenges } from "./fakeChallenges";
import { installFakePlanner, mkItem, type FakePlanner } from "./fakePlanner";
import { renderAt } from "./render";

const TODAY = () => todayIn(USER.timezone);

beforeEach(() => {
  setModelChoice(null);
});

/** `setup` runs before the page loads, e.g. to set the weekly hours. */
async function open(days: FakePlanner["days"] = {}, setup?: (fake: Fake) => void) {
  const fake = installFakeApi();
  const store = installFakePlanner(fake, { days });
  setup?.(fake);
  renderAt("/planner");
  await screen.findByRole("heading", { name: "Daily planner", level: 1 });
  return { fake, store };
}

const twoTasks = (): FakePlanner["days"] => ({
  [TODAY()]: [
    mkItem({ kind: "task", ref_id: 1, title: "Write report", status: "pending", minutes: 90 }),
    mkItem({ kind: "task", ref_id: 2, title: "File taxes", status: "overdue", minutes: 45 }),
  ],
});

const monthName = () => new Date().toLocaleDateString("en-GB", { month: "long" });

describe("rest days on the planner", () => {
  it("takes a rest day: open items become excused, the streak note shows, and the month usage updates", async () => {
    const { fake } = await open(twoTasks());
    expect(await screen.findByText(`4 of 4 rest days left in ${monthName()}`)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Take a rest day" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Reason (optional)"), "Fever");
    await userEvent.click(within(dialog).getByRole("button", { name: "Take the rest day" }));
    const card = await screen.findByRole("region", { name: "Rest day" });
    expect(card).toHaveTextContent("Fever");
    expect(card).toHaveTextContent("Your streak is safe");
    expect(fake.planning.restDays).toEqual([{ date: TODAY(), reason: "Fever" }]);
    const excused = await screen.findByRole("region", { name: "Excused" });
    expect(within(excused).getByText("Write report")).toBeInTheDocument();
    expect(within(excused).queryByRole("button", { name: /Remove excuse/ })).not.toBeInTheDocument(); // the rest day owns that excuse
    expect(screen.queryByRole("region", { name: "Overdue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Move unfinished to tomorrow/ })).not.toBeInTheDocument();
  });

  it("cancels a rest day", async () => {
    const { fake } = await open(twoTasks(), (f) => f.planning.restDays.push({ date: TODAY(), reason: null }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel rest day" }));
    await waitFor(() => expect(fake.planning.restDays).toEqual([]));
    expect(await screen.findByRole("region", { name: "Overdue" })).toBeInTheDocument();
  });

  it("disables the button when the month has no rest days left", async () => {
    await open(twoTasks(), (f) => (f.planning.prefs.rest_days_per_month = 0));
    expect(await screen.findByText(new RegExp(`No rest days left in ${monthName()}`))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take a rest day" })).toBeDisabled();
  });

  it("shows the server's message if the limit was reached meanwhile", async () => {
    const { fake } = await open(twoTasks());
    await userEvent.click(await screen.findByRole("button", { name: "Take a rest day" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Take the rest day" })).toBeEnabled());
    fake.planning.prefs.rest_days_per_month = 0; // changed elsewhere after the dialog opened
    await userEvent.click(within(dialog).getByRole("button", { name: "Take the rest day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("used all 0 rest days");
  });

  it("offers no rest day for days further back than 3 days", async () => {
    await open(twoTasks());
    await screen.findByRole("button", { name: "Take a rest day" });
    for (let i = 0; i < 3; i++) await userEvent.click(screen.getByRole("button", { name: "Previous day" }));
    expect(await screen.findByRole("button", { name: "Take a rest day" })).toBeInTheDocument(); // 3 days back is still allowed
    await userEvent.click(screen.getByRole("button", { name: "Previous day" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Take a rest day" })).not.toBeInTheDocument());
  });
});

describe("daily hours", () => {
  it("warns when the day asks for more than the hours available", async () => {
    await open(twoTasks(), (f) => (f.planning.prefs.weekday_minutes = [120, 120, 120, 120, 120, 120, 120]));
    const notice = await screen.findByRole("region", { name: "Time planned" });
    expect(within(notice).getByRole("status")).toHaveTextContent("Overloaded: 15m more than you have"); // 135 planned, 120 available
    expect(notice).toHaveTextContent("2h 15m planned, 2h available");
  });

  it("is calm when the day fits, and says how to turn the warnings on when no hours are set", async () => {
    const { fake } = await open(twoTasks());
    const notice = await screen.findByRole("region", { name: "Time planned" });
    expect(notice).toHaveTextContent("Planned about 2h 15m");
    expect(within(notice).getByRole("link", { name: "Set the hours you have each day" })).toHaveAttribute("href", "/settings");
    expect(within(notice).queryByRole("status")).not.toBeInTheDocument();
    expect(fake.planning.prefs.weekday_minutes).toBeNull();
  });

  it("says how many items could not be counted instead of guessing", async () => {
    await open({ [TODAY()]: [mkItem({ kind: "task", ref_id: 1, title: "A", minutes: 30 }), mkItem({ kind: "habit", ref_id: 2, title: "Reading" })] });
    expect(await screen.findByText("1 open item has no time estimate, so it isn't counted.")).toBeInTheDocument();
  });
});

describe("rolling unfinished tasks to tomorrow", () => {
  it("previews, then moves the tasks and shows how loaded tomorrow becomes", async () => {
    const { store } = await open(twoTasks(), (f) => (f.planning.prefs.weekday_minutes = [120, 120, 120, 120, 120, 120, 120]));
    await userEvent.click(await screen.findByRole("button", { name: "Move unfinished to tomorrow (2)" }));
    const dialog = await screen.findByRole("dialog");
    const list = await within(dialog).findByRole("list", { name: "Tasks to move" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(dialog).toHaveTextContent("will move to");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Tomorrow would have about 2h 15m planned of 2h available");
    expect(store.days[TODAY()]).toHaveLength(2); // the preview changed nothing
    await userEvent.click(within(dialog).getByRole("button", { name: "Move all 2" }));
    await waitFor(() => expect(dialog).toHaveTextContent("Moved 2 tasks"));
    expect(store.days[TODAY()]).toHaveLength(0);
    expect(store.days[addDays(TODAY(), 1)]).toHaveLength(2);
    await userEvent.click(within(dialog).getAllByRole("button", { name: "Close" }).at(-1)!);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Move unfinished to tomorrow/ })).not.toBeInTheDocument();
  });

  it("is not offered when nothing is open", async () => {
    await open({ [TODAY()]: [mkItem({ kind: "task", ref_id: 1, title: "Done", status: "completed" })] });
    await screen.findByRole("region", { name: "Day summary" });
    expect(screen.queryByRole("button", { name: /Move unfinished/ })).not.toBeInTheDocument();
  });

  it("flags a task that would now have been moved three times", async () => {
    await open({ [TODAY()]: [mkItem({ kind: "task", ref_id: 1, title: "Stubborn", carry_count: 2 })] });
    await userEvent.click(await screen.findByRole("button", { name: /Move unfinished to tomorrow/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Slipping: moved 3×")).toBeInTheDocument();
  });
});

describe("slipping tasks", () => {
  it("marks a task moved 3+ times and links to the assistant with the question filled in", async () => {
    await open({ [TODAY()]: [mkItem({ kind: "task", ref_id: 1, title: "Write the report", carry_count: 4 })] });
    expect(await screen.findByText("Slipping: moved 4×")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Ask the assistant why/ });
    expect(decodeURIComponent(link.getAttribute("href")!)).toBe(`/assistant?ask=Why does "Write the report" keep slipping? I've moved it 4 times.`);
  });

  it("does not mark a task moved only twice", async () => {
    await open({ [TODAY()]: [mkItem({ kind: "task", ref_id: 1, title: "Fine", carry_count: 2 })] });
    await screen.findByText("Fine");
    expect(screen.queryByText(/Slipping/)).not.toBeInTheDocument();
  });

  it("the assistant page opens with the question typed in, ready to send", async () => {
    const fake = installFakeApi();
    installFakeAssistant(fake, { status: { provider: "groq", connected: true, model: "m", live_verified: true, message: "ok" } });
    renderAt(`/assistant?ask=${encodeURIComponent('Why does "Report" keep slipping?')}`);
    expect(await screen.findByDisplayValue('Why does "Report" keep slipping?')).toBeInTheDocument();
  });
});

describe("planning settings", () => {
  it("saves the weekly hours and the rest-day limit", async () => {
    const fake = installFakeApi();
    renderAt("/settings");
    const card = await screen.findByRole("region", { name: "Planning settings" });
    const box = await within(card).findByRole("checkbox", { name: /Warn me when a day has more planned/ });
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    const sat = within(card).getByLabelText("Saturday (hours)");
    await userEvent.clear(sat);
    await userEvent.type(sat, "1.5");
    const rest = within(card).getByLabelText(/^Rest days per month/);
    await userEvent.clear(rest);
    await userEvent.type(rest, "6");
    await userEvent.click(within(card).getByRole("button", { name: "Save planning settings" }));
    expect(await within(card).findByText("Saved")).toBeInTheDocument();
    expect(fake.planning.prefs).toEqual({ weekday_minutes: [240, 240, 240, 240, 240, 90, 240], rest_days_per_month: 6 });
  });

  it("turning the warning off saves no hours", async () => {
    const fake = installFakeApi();
    fake.planning.prefs.weekday_minutes = [60, 60, 60, 60, 60, 60, 60];
    renderAt("/settings");
    const card = await screen.findByRole("region", { name: "Planning settings" });
    const box = await within(card).findByRole("checkbox", { name: /Warn me when a day has more planned/ });
    expect(box).toBeChecked();
    expect(within(card).getByLabelText("Monday (hours)")).toHaveValue(1);
    await userEvent.click(box);
    expect(within(card).getByLabelText("Monday (hours)")).toBeDisabled();
    await userEvent.click(within(card).getByRole("button", { name: "Save planning settings" }));
    await within(card).findByText("Saved");
    expect(fake.planning.prefs.weekday_minutes).toBeNull();
  });

  it("rejects bad numbers without calling the server", async () => {
    const fake = installFakeApi();
    renderAt("/settings");
    const card = await screen.findByRole("region", { name: "Planning settings" });
    const rest = await within(card).findByLabelText(/^Rest days per month/);
    await userEvent.clear(rest);
    await userEvent.type(rest, "40");
    await userEvent.click(within(card).getByRole("button", { name: "Save planning settings" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("whole number from 0 to 31");
    expect(fake.callsTo("PATCH", /preferences/)).toHaveLength(0);
  });
});

describe("rest days on the challenge page", () => {
  it("tells you today is a rest day and marks rest days on the calendar and legend", async () => {
    const fake = installFakeApi();
    installFakeChallenges(fake);
    fake.planning.restDays.push({ date: TODAY(), reason: null }, { date: addDays(TODAY(), -2), reason: "Trip" });
    renderAt("/challenge");
    expect(await screen.findByText(/Today is a planned rest day/)).toBeInTheDocument();
    const legend = await screen.findByRole("list", { name: "Legend" });
    expect(within(legend).getByText("Rest day")).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Rest day/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Rest days")).toBeInTheDocument(); // the stat tile
  });
});
