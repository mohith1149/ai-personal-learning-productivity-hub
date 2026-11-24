import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { addDays, todayIn } from "../lib/dates";
import { installFakeApi, USER } from "./fakeApi";
import { installFakePlanner, mkItem, type FakePlanner } from "./fakePlanner";
import { renderAt } from "./render";

const TODAY = () => todayIn(USER.timezone);

async function open(days: FakePlanner["days"] = {}) {
  const fake = installFakeApi();
  const store = installFakePlanner(fake, { days });
  renderAt("/planner");
  await screen.findByRole("heading", { name: "Daily planner", level: 1 });
  return { fake, store };
}

/** A typical day: one overdue task, one task, a lesson, a video, a habit, a project nudge and one completed task. */
function busyDay(): FakePlanner["days"] {
  return {
    [TODAY()]: [
      mkItem({ kind: "task", ref_id: 1, title: "File taxes", status: "overdue", due_date: addDays(TODAY(), -2) }),
      mkItem({ kind: "task", ref_id: 2, title: "Write report", status: "pending", minutes: 90 }),
      mkItem({ kind: "lesson", ref_id: 3, title: "What is an agent?", subtitle: "Agentic AI · Intro", url: "https://example.com/l" }),
      mkItem({ kind: "video", ref_id: 4, title: "How DNS works", subtitle: "ByteByteGo", url: "https://youtu.be/aaaaaaaaaaa", minutes: 10 }),
      mkItem({ kind: "habit", ref_id: 5, title: "Reading", subtitle: "Every day" }),
      mkItem({ kind: "project", ref_id: 6, title: "Work on RAG chatbot", can_complete: false, link: "/projects/6" }),
      mkItem({ kind: "task", ref_id: 7, title: "Pay bill", status: "completed" }),
    ],
  };
}

const section = (name: string) => screen.findByRole("region", { name });
const row = async (title: string) => (await screen.findByRole("link", { name: title })).closest("li")!;

describe("daily planner", () => {
  it("shows today's activities from every feature, grouped by status, overdue first", async () => {
    await open(busyDay());
    expect(await screen.findByRole("heading", { name: /^Today/, level: 2 })).toBeInTheDocument();
    const overdue = await section("Overdue");
    expect(within(overdue).getByText("File taxes")).toBeInTheDocument();
    expect(within(overdue).getByText(/due /)).toBeInTheDocument();
    const todo = await section("To do");
    expect(within(todo).getAllByRole("listitem").map((li) => li.querySelector("a")?.textContent).sort()).toEqual(
      ["How DNS works", "Reading", "What is an agent?", "Work on RAG chatbot", "Write report"],
    );
    expect(within(todo).getAllByText(/^(Task|Lesson|Video|Habit|Project)$/).map((b) => b.textContent).sort()).toEqual(["Habit", "Lesson", "Project", "Task", "Video"]);
    expect((await section("Completed")).textContent).toContain("Pay bill");
    const order = screen.getAllByRole("region").map((r) => r.getAttribute("aria-label")).filter((l) => ["Overdue", "To do", "Completed", "Excused"].includes(l!));
    expect(order).toEqual(["Overdue", "To do", "Completed"]);
  });

  it("shows the day's summary: counts, percent and per-type progress", async () => {
    await open(busyDay());
    const summary = await section("Day summary");
    expect(within(summary).getByRole("progressbar", { name: "Day progress" })).toHaveAttribute("aria-valuenow", "14");     // 1 of 7
    expect(within(summary).getByText("Completed").nextSibling).toHaveTextContent("1/7");
    expect(within(summary).getByText("Overdue").nextSibling).toHaveTextContent("1");
    expect(within(summary).getByText("To do").nextSibling).toHaveTextContent("5");
    expect(within(summary).getByText("Tasks 1/3")).toBeInTheDocument();
    expect(within(summary).getByText("Videos 0/1")).toBeInTheDocument();
  });

  it("completing an activity moves it to Completed and updates progress", async () => {
    const { fake } = await open(busyDay());
    await userEvent.click(await screen.findByRole("button", { name: "Complete Write report" }));
    await waitFor(() => expect(within(screen.getByRole("region", { name: "Completed" })).getByText("Write report")).toBeInTheDocument());
    expect(fake.callsTo("POST", /planner\/complete$/)[0].body).toEqual({ kind: "task", ref_id: 2, date: TODAY() });
    expect(within(screen.getByRole("region", { name: "Day summary" })).getByText("Completed").nextSibling).toHaveTextContent("2/7");
  });

  it("completes lessons, videos and habits the same way, and reopens a completed one", async () => {
    const { fake } = await open(busyDay());
    for (const t of ["What is an agent?", "How DNS works", "Reading"]) await userEvent.click(await screen.findByRole("button", { name: `Complete ${t}` }));
    await waitFor(() => expect(fake.callsTo("POST", /planner\/complete$/).map((c) => (c.body as { kind: string }).kind)).toEqual(["lesson", "video", "habit"]));
    await userEvent.click(await screen.findByRole("button", { name: "Reopen Pay bill" }));
    await waitFor(() => expect(within(screen.getByRole("region", { name: "To do" })).getByText("Pay bill")).toBeInTheDocument());
    expect(fake.callsTo("POST", /planner\/reopen$/)[0].body).toEqual({ kind: "task", ref_id: 7, date: TODAY() });
  });

  it("project work can't be completed from the planner and points at the project page", async () => {
    await open(busyDay());
    const r = await row("Work on RAG chatbot");
    expect(within(r).queryByRole("button", { name: /Complete/ })).not.toBeInTheDocument();
    expect(within(r).getByRole("link", { name: "Log a session" })).toHaveAttribute("href", "/projects/6");
  });

  it("shows external links safely and the estimated time", async () => {
    await open(busyDay());
    const link = within(await row("How DNS works")).getByRole("link", { name: "Open How DNS works" });
    expect(link).toHaveAttribute("href", "https://youtu.be/aaaaaaaaaaa");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
    expect(within(await row("Write report")).getByText(/~1h 30m/)).toBeInTheDocument();
  });

  it("reschedules only tasks, the task leaves the day, and nothing is marked completed", async () => {
    const { fake, store } = await open(busyDay());
    expect(within(await row("What is an agent?")).queryByRole("button", { name: /Reschedule/ })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Reschedule Write report" }));
    const dialog = await screen.findByRole("dialog", { name: "Reschedule: Write report" });
    expect(dialog).toHaveTextContent("Moving a task does not complete it.");
    const target = addDays(TODAY(), 3);
    fireDate(within(dialog).getByLabelText("New day"), target);
    await userEvent.click(within(dialog).getByRole("button", { name: "Reschedule" }));
    await waitFor(() => expect(screen.queryByText("Write report")).not.toBeInTheDocument());
    expect(fake.callsTo("POST", /planner\/tasks\/2\/reschedule$/)[0].body).toEqual({ date: target, from_date: TODAY(), move_due_date: false });
    expect(store.days[target].map((i) => [i.title, i.status])).toEqual([["Write report", "pending"]]);
    expect(within(screen.getByRole("region", { name: "Day summary" })).getByText("Completed").nextSibling).toHaveTextContent("1/6");   // unchanged: still 1 completed
  });

  it("offers to move the deadline too when the task has one, and refuses a past day", async () => {
    const { fake } = await open(busyDay());
    await userEvent.click(await screen.findByRole("button", { name: "Reschedule File taxes" }));
    const dialog = await screen.findByRole("dialog", { name: "Reschedule: File taxes" });
    await userEvent.click(within(dialog).getByLabelText(/Also move the deadline/));
    fireDate(within(dialog).getByLabelText("New day"), addDays(TODAY(), -1));
    await userEvent.click(within(dialog).getByRole("button", { name: "Reschedule" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("can't be moved into the past");
    expect(fake.callsTo("POST", /reschedule/)).toHaveLength(0);
    fireDate(within(dialog).getByLabelText("New day"), addDays(TODAY(), 1));
    await userEvent.click(within(dialog).getByRole("button", { name: "Reschedule" }));
    await waitFor(() => expect(fake.callsTo("POST", /reschedule/)[0].body).toMatchObject({ move_due_date: true }));
  });

  it("excusing needs a reason, moves the item to Excused and takes it out of the percentage", async () => {
    const { fake } = await open(busyDay());
    await userEvent.click(await screen.findByRole("button", { name: "Excuse File taxes" }));
    const dialog = await screen.findByRole("dialog", { name: "Excuse: File taxes" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Excuse for this day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Give a reason");
    expect(fake.callsTo("POST", /excuse$/)).toHaveLength(0);
    await userEvent.type(within(dialog).getByLabelText(/Why is it being skipped/), "Office was closed");
    await userEvent.click(within(dialog).getByRole("button", { name: "Excuse for this day" }));
    const excused = await section("Excused");
    expect(within(excused).getByText("File taxes")).toBeInTheDocument();
    expect(within(excused).getByText(/Excused: Office was closed/)).toBeInTheDocument();
    expect(fake.callsTo("POST", /excuse$/)[0].body).toEqual({ kind: "task", ref_id: 1, date: TODAY(), reason: "Office was closed" });
    const summary = screen.getByRole("region", { name: "Day summary" });
    expect(within(summary).getByText("Overdue").nextSibling).toHaveTextContent("0");
    expect(within(summary).getByText("Excused").nextSibling).toHaveTextContent("1");
    expect(within(summary).getByText("Completed").nextSibling).toHaveTextContent("1/6");
    expect(within(summary).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "16");       // 1 of 6 (excused left out)
  });

  it("removes an excuse", async () => {
    const days = busyDay();
    days[TODAY()][0] = { ...days[TODAY()][0], status: "excused", excuse_reason: "Away" };
    const { fake } = await open(days);
    await userEvent.click(await screen.findByRole("button", { name: "Remove excuse for File taxes" }));
    await waitFor(() => expect(within(screen.getByRole("region", { name: "To do" })).getByText("File taxes")).toBeInTheDocument());
    expect(fake.callsTo("POST", /unexcuse$/)).toHaveLength(1);
  });

  it("navigates to other days: nothing can be completed in the future or the past except habits", async () => {
    const days = busyDay();
    days[addDays(TODAY(), -1)] = [mkItem({ kind: "task", ref_id: 20, title: "Yesterday task", status: "overdue" }), mkItem({ kind: "habit", ref_id: 21, title: "Reading", status: "overdue" })];
    days[addDays(TODAY(), 1)] = [mkItem({ kind: "task", ref_id: 30, title: "Tomorrow task" })];
    const { fake } = await open(days);
    await userEvent.click(screen.getByRole("button", { name: "Previous day" }));
    expect(await screen.findByText("Yesterday task")).toBeInTheDocument();
    expect(fake.callsTo("GET", /\/api\/planner$/).at(-1)!.query.day).toBe(addDays(TODAY(), -1));
    expect(screen.queryByRole("button", { name: "Complete Yesterday task" })).not.toBeInTheDocument();          // tasks: today only
    expect(screen.getByRole("button", { name: "Complete Reading" })).toBeInTheDocument();                         // habits can be back-filled
    expect(screen.getByRole("button", { name: "Excuse Yesterday task" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(await screen.findByText("Write report")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next day" }));
    expect(await screen.findByText("Tomorrow task")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(Complete|Excuse|Reschedule) Tomorrow task/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Future days only show tasks scheduled for them/)).toBeInTheDocument();
  });

  it("the date picker jumps to a chosen day", async () => {
    const days = { [addDays(TODAY(), -5)]: [mkItem({ kind: "task", ref_id: 40, title: "Old task", status: "completed" })] };
    const { fake } = await open(days);
    fireDate(screen.getByLabelText("Go to day"), addDays(TODAY(), -5));
    expect(await screen.findByText("Old task")).toBeInTheDocument();
    expect(fake.callsTo("GET", /\/api\/planner$/).at(-1)!.query.day).toBe(addDays(TODAY(), -5));
  });

  it("an empty day says so honestly", async () => {
    await open({});
    expect(await screen.findByText("Nothing planned for this day")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Day progress" })).toHaveAttribute("aria-valuenow", "0");
  });

  it("shows the server's message when an action is rejected", async () => {
    const { fake } = await open(busyDay());
    fake.failNext(/^POST \/api\/planner\/complete$/, 404, "Task not found");
    await userEvent.click(await screen.findByRole("button", { name: "Complete Write report" }));
    expect(await within(await row("Write report")).findByRole("alert")).toHaveTextContent("Task not found");
  });

  it("shows the server error when the plan can't load, and retries", async () => {
    const fake = installFakeApi();
    installFakePlanner(fake, { days: busyDay() });
    fake.failNext(/^GET \/api\/planner$/, 500, "Database is down");
    renderAt("/planner");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Write report")).toBeInTheDocument();
  });

  it("the sidebar link is live (no Soon badge)", async () => {
    await open();
    const link = within(await screen.findByRole("navigation", { name: "Main" })).getByRole("link", { name: /Daily planner/ });
    expect(within(link).queryByText("Soon")).not.toBeInTheDocument();
  });
});

function fireDate(el: HTMLElement, value: string) {
  fireEvent.change(el, { target: { value } });
}
