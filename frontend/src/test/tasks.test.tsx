import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { addDays } from "../lib/dates";
import { installFakeApi, mkRecurring, mkTask, TODAY, type Fake } from "./fakeApi";
import { renderAt } from "./render";

type Seed = Parameters<typeof installFakeApi>[0];

async function openTasks(seed: Seed = {}, path = "/tasks"): Promise<Fake> {
  const fake = installFakeApi(seed);
  renderAt(path);
  await screen.findByRole("heading", { name: "Tasks" });
  return fake;
}

const STUDY = { id: 5, name: "Study", color: "#123456", is_system: false };
const seedTasks = () => [
  mkTask({ id: 1, title: "Write report", due_date: addDays(TODAY, -2), is_overdue: true, priority: 1 }),
  mkTask({ id: 2, title: "Read paper", category_id: 5, category: { id: 5, name: "Study", color: "#123456" }, due_date: addDays(TODAY, 3) }),
  mkTask({ id: 3, title: "Old thing", status: "completed", completed_at: "2026-11-20T10:00:00Z" }),
];

describe("task list", () => {
  it("shows tasks with their status, due text, priority and category, plus per-tab counts", async () => {
    await openTasks({ tasks: seedTasks(), categories: [STUDY] });
    const list = await screen.findByRole("list", { name: "Tasks" });
    expect(within(list).getByText("Write report")).toBeInTheDocument();
    expect(within(list).getByText("Read paper")).toBeInTheDocument();
    expect(within(list).queryByText("Old thing")).not.toBeInTheDocument(); // completed work is not in "Open"

    expect(within(list).getByText("Overdue")).toBeInTheDocument(); // status badge
    expect(within(list).getByText("2 days overdue")).toBeInTheDocument();
    expect(within(list).getByText("Urgent priority")).toBeInTheDocument();
    expect(within(list).getByText("Study")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole("tab", { name: /^Open\s*2 tasks/ })).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: /^Overdue\s*1 tasks/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Completed\s*1 tasks/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^All\s*3 tasks/ })).toBeInTheDocument();
  });

  it.each([
    ["open", "No open tasks"],
    ["overdue", "Nothing overdue"],
    ["completed", "No completed tasks yet"],
  ])("shows an honest empty state on the %s tab", async (view, title) => {
    await openTasks({}, `/tasks?view=${view}`);
    expect(await screen.findByText(title)).toBeInTheDocument();
  });

  it("opens on the tab named in the URL and switching tabs asks the server for that view", async () => {
    const fake = await openTasks({ tasks: seedTasks() }, "/tasks?view=overdue");
    expect(screen.getByRole("tab", { name: /^Overdue/ })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Write report")).toBeInTheDocument();
    expect(screen.queryByText("Read paper")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /^Completed/ }));
    expect(await screen.findByText("Old thing")).toBeInTheDocument();
    expect(fake.callsTo("GET", /\/api\/tasks$/).map((c) => c.query.view)).toContain("completed");
  });

  it("falls back to Open for an unknown ?view=", async () => {
    await openTasks({ tasks: seedTasks() }, "/tasks?view=nonsense");
    expect(screen.getByRole("tab", { name: /^Open/ })).toHaveAttribute("aria-selected", "true");
  });

  it("searches (debounced) and filters by category and priority via the server", async () => {
    const fake = await openTasks({ tasks: seedTasks(), categories: [STUDY] });
    await screen.findByText("Read paper");

    await userEvent.type(screen.getByRole("searchbox", { name: "Search tasks" }), "paper");
    await waitFor(() => expect(fake.callsTo("GET", /\/api\/tasks$/).some((c) => c.query.q === "paper")).toBe(true));
    await waitFor(() => expect(screen.queryByText("Write report")).not.toBeInTheDocument());
    expect(screen.getByText("Read paper")).toBeInTheDocument();

    await userEvent.clear(screen.getByRole("searchbox", { name: "Search tasks" }));
    await userEvent.selectOptions(screen.getByLabelText("Filter by priority"), "1");
    await waitFor(() => expect(fake.callsTo("GET", /\/api\/tasks$/).some((c) => c.query.priority === "1")).toBe(true));
    await waitFor(() => expect(screen.queryByText("Read paper")).not.toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText("Filter by priority"), "");
    await userEvent.selectOptions(screen.getByLabelText("Filter by category"), "5");
    await waitFor(() => expect(fake.callsTo("GET", /\/api\/tasks$/).some((c) => c.query.category_id === "5")).toBe(true));
  });

  it("explains when filters hide everything", async () => {
    await openTasks({ tasks: seedTasks() });
    await screen.findByText("Read paper");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search tasks" }), "zzzz");
    expect(await screen.findByText("No tasks match these filters")).toBeInTheDocument();
  });

  it("shows the server's error with a working Retry", async () => {
    const fake = installFakeApi({ tasks: seedTasks() });
    fake.failNext(/^GET \/api\/tasks$/, 500, "Database exploded");
    renderAt("/tasks");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database exploded");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Read paper")).toBeInTheDocument();
  });
});

describe("creating tasks", () => {
  it("creates a task with the chosen fields and shows it in the list", async () => {
    const fake = await openTasks({ tasks: seedTasks(), categories: [STUDY] });
    await userEvent.click(screen.getByRole("button", { name: "New task" }));
    const dlg = screen.getByRole("dialog", { name: "New task" });

    const due = within(dlg).getByLabelText(/^Due date/);
    const time = within(dlg).getByLabelText(/^Due time/);
    expect(time).toBeDisabled(); // a time without a date is meaningless

    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Ship milestone 3");
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Priority/), "1");
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Category/), "5");
    fireEvent.change(due, { target: { value: addDays(TODAY, 5) } });
    expect(time).toBeEnabled();
    fireEvent.change(time, { target: { value: "09:30" } });
    await userEvent.click(within(dlg).getByRole("button", { name: "Create task" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const post = fake.callsTo("POST", /\/api\/tasks$/);
    expect(post).toHaveLength(1);
    expect(post[0].body).toMatchObject({
      title: "Ship milestone 3",
      priority: 1,
      category_id: 5,
      due_date: addDays(TODAY, 5),
      due_time: "09:30",
      description: null,
    });
    expect(await screen.findByText("Ship milestone 3")).toBeInTheDocument();
  });

  it("refuses a blank title without calling the server", async () => {
    const fake = await openTasks({ tasks: seedTasks() });
    await userEvent.click(screen.getByRole("button", { name: "New task" }));
    const dlg = screen.getByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "    ");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create task" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("give the task a title");
    expect(fake.callsTo("POST", /\/api\/tasks$/)).toHaveLength(0);
  });

  it("catches a due date before the scheduled date locally", async () => {
    const fake = await openTasks({ tasks: seedTasks() });
    await userEvent.click(screen.getByRole("button", { name: "New task" }));
    const dlg = screen.getByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "x");
    fireEvent.change(within(dlg).getByLabelText(/^Scheduled for/), { target: { value: addDays(TODAY, 3) } });
    fireEvent.change(within(dlg).getByLabelText(/^Due date/), { target: { value: addDays(TODAY, 1) } });
    await userEvent.click(within(dlg).getByRole("button", { name: "Create task" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("before the scheduled date");
    expect(fake.callsTo("POST", /\/api\/tasks$/)).toHaveLength(0);
  });

  it("keeps the form open and shows the server's message when the server rejects it", async () => {
    const fake = await openTasks({ tasks: seedTasks() });
    fake.failNext(/^POST \/api\/tasks$/, 422, "That category doesn't exist");
    await userEvent.click(screen.getByRole("button", { name: "New task" }));
    const dlg = screen.getByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Keep my typing");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create task" }));
    expect(await within(dlg).findByRole("alert")).toHaveTextContent("That category doesn't exist");
    expect(within(dlg).getByLabelText(/^Title/)).toHaveValue("Keep my typing"); // nothing lost

    await userEvent.click(within(dlg).getByRole("button", { name: "Create task" })); // retry works
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("pre-fills today's date when creating from the Today tab", async () => {
    await openTasks({}, "/tasks?view=today");
    await userEvent.click(screen.getAllByRole("button", { name: "New task" })[0]);
    expect(within(screen.getByRole("dialog")).getByLabelText(/^Due date/)).toHaveValue(TODAY);
  });
});

describe("changing tasks", () => {
  it("ticking a task completes it, and unticking from Completed reopens it", async () => {
    const fake = await openTasks({ tasks: seedTasks() });
    await userEvent.click(await screen.findByRole("checkbox", { name: 'Mark "Read paper" as done' }));
    await waitFor(() => expect(fake.callsTo("PATCH", /\/api\/tasks\/2$/)[0]?.body).toEqual({ status: "completed" }));
    await waitFor(() => expect(screen.queryByText("Read paper")).not.toBeInTheDocument()); // left the Open view

    await userEvent.click(screen.getByRole("tab", { name: /^Completed/ }));
    const box = await screen.findByRole("checkbox", { name: 'Mark "Read paper" as not done' });
    expect(box).toHaveAttribute("aria-checked", "true");
    await userEvent.click(box);
    await waitFor(() => expect(fake.callsTo("PATCH", /\/api\/tasks\/2$/)[1]?.body).toEqual({ status: "pending" }));
  });

  it("completing an overdue task removes its overdue marking", async () => {
    await openTasks({ tasks: seedTasks() }, "/tasks?view=all");
    await userEvent.click(await screen.findByRole("checkbox", { name: 'Mark "Write report" as done' }));
    const row = (await screen.findByText("Write report")).closest("li")!;
    await waitFor(() => expect(within(row).queryByText("Overdue")).not.toBeInTheDocument());
    expect(within(row).getByText("Completed")).toBeInTheDocument();
  });

  it("edits a task: form is pre-filled and the saved changes are sent", async () => {
    const fake = await openTasks({ tasks: seedTasks(), categories: [STUDY] });
    await userEvent.click(await screen.findByRole("button", { name: "Read paper" }));
    const dlg = screen.getByRole("dialog", { name: "Edit task" });
    expect(within(dlg).getByLabelText(/^Title/)).toHaveValue("Read paper");
    expect(within(dlg).getByLabelText(/^Category/)).toHaveValue("5");
    expect(within(dlg).getByLabelText(/^Status/)).toHaveValue("pending");
    expect(within(dlg).getByLabelText(/^Due date/)).toHaveValue(addDays(TODAY, 3));

    await userEvent.clear(within(dlg).getByLabelText(/^Title/));
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Read two papers");
    fireEvent.change(within(dlg).getByLabelText(/^Due date/), { target: { value: "" } }); // clear the due date
    await userEvent.click(within(dlg).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const patch = fake.callsTo("PATCH", /\/api\/tasks\/2$/)[0];
    expect(patch.body).toMatchObject({ title: "Read two papers", due_date: null, due_time: null, status: "pending", category_id: 5 });
    expect(await screen.findByText("Read two papers")).toBeInTheDocument();
  });

  it("clearing the due date also clears a previously set due time", async () => {
    const fake = await openTasks({ tasks: [mkTask({ id: 9, title: "Timed", due_date: addDays(TODAY, 2), due_time: "09:30" })] });
    await userEvent.click(await screen.findByRole("button", { name: "Timed" }));
    const dlg = screen.getByRole("dialog", { name: "Edit task" });
    expect(within(dlg).getByLabelText(/^Due time/)).toHaveValue("09:30");
    fireEvent.change(within(dlg).getByLabelText(/^Due date/), { target: { value: "" } });
    expect(within(dlg).getByLabelText(/^Due time/)).toBeDisabled();
    await userEvent.click(within(dlg).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fake.callsTo("PATCH", /\/api\/tasks\/9$/)[0]?.body).toMatchObject({ due_date: null, due_time: null }));
  });

  it("deletes only after confirmation", async () => {
    const fake = await openTasks({ tasks: seedTasks() });
    await userEvent.click(await screen.findByRole("button", { name: 'Delete "Read paper"' }));
    let dlg = screen.getByRole("dialog", { name: "Delete task?" });
    expect(dlg).toHaveTextContent("Read paper");
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /./)).toHaveLength(0);
    expect(screen.getByText("Read paper")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: 'Delete "Read paper"' }));
    dlg = screen.getByRole("dialog", { name: "Delete task?" });
    await userEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("Read paper")).not.toBeInTheDocument());
    expect(fake.callsTo("DELETE", /\/api\/tasks\/2$/)).toHaveLength(1);
  });

  it("shows an error instead of failing silently when a status change is rejected", async () => {
    const fake = await openTasks({ tasks: seedTasks() });
    fake.failNext(/^PATCH /, 500, "Could not save");
    await userEvent.click(await screen.findByRole("checkbox", { name: 'Mark "Read paper" as done' }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save");
    expect(screen.getByText("Read paper")).toBeInTheDocument();
  });
});

describe("modal behaviour", () => {
  it("closes on Escape and returns focus to the button that opened it", async () => {
    await openTasks({ tasks: seedTasks() });
    const opener = screen.getByRole("button", { name: "New task" });
    await userEvent.click(opener);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Title/)).toHaveFocus(); // typing can start immediately
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("closes when the backdrop is clicked but not when the panel is", async () => {
    await openTasks({ tasks: seedTasks() });
    await userEvent.click(screen.getByRole("button", { name: "New task" }));
    const dlg = screen.getByRole("dialog");
    await userEvent.click(within(dlg).getByLabelText(/^Description/));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.pointer({ keys: "[MouseLeft]", target: dlg.parentElement! });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps Tab focus inside the dialog", async () => {
    await openTasks({ tasks: seedTasks() });
    await userEvent.click(screen.getByRole("button", { name: "New task" }));
    const dlg = screen.getByRole("dialog");
    within(dlg).getByRole("button", { name: "Create task" }).focus();
    await userEvent.tab(); // from the last control, wraps to the first one
    expect(dlg.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(within(dlg).getByRole("button", { name: "Close" }));
  });
});

describe("categories", () => {
  it("adds, renames and deletes a category", async () => {
    const fake = await openTasks({ tasks: seedTasks(), categories: [STUDY] });
    await userEvent.click(screen.getByRole("button", { name: "Categories" }));
    const dlg = screen.getByRole("dialog", { name: "Task categories" });
    expect(within(dlg).getByText("Study")).toBeInTheDocument();

    await userEvent.type(within(dlg).getByLabelText("New category name"), "Health");
    await userEvent.click(within(dlg).getByRole("button", { name: "Add" }));
    expect(await within(dlg).findByText("Health")).toBeInTheDocument();
    expect(fake.callsTo("POST", /task-categories$/)[0].body).toEqual({ name: "Health", color: "#6366f1" });

    await userEvent.click(within(dlg).getByRole("button", { name: "Rename Health" }));
    const input = within(dlg).getByLabelText("New name for Health");
    await userEvent.clear(input);
    await userEvent.type(input, "Fitness");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save name" }));
    expect(await within(dlg).findByText("Fitness")).toBeInTheDocument();

    await userEvent.click(within(dlg).getByRole("button", { name: "Delete category Fitness" }));
    await userEvent.click(within(dlg).getByRole("button", { name: "Yes" }));
    await waitFor(() => expect(within(dlg).queryByText("Fitness")).not.toBeInTheDocument());
    expect(fake.callsTo("DELETE", /task-categories\/\d+$/)).toHaveLength(1);
  });

  it("shows the server's reason when a category can't be added", async () => {
    const fake = await openTasks({ categories: [STUDY] });
    fake.failNext(/^POST \/api\/task-categories$/, 422, "A category named 'study' already exists");
    await userEvent.click(screen.getByRole("button", { name: "Categories" }));
    const dlg = screen.getByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText("New category name"), "study");
    await userEvent.click(within(dlg).getByRole("button", { name: "Add" }));
    expect(await within(dlg).findByRole("alert")).toHaveTextContent("already exists");
  });
});

describe("recurring tasks", () => {
  const seed = (): Seed => ({
    recurring: [
      mkRecurring({ id: 7, title: "Daily review" }),
      mkRecurring({ id: 8, title: "Weekly planning", frequency: "weekly", days_of_week: [0, 2], active: false }),
    ],
  });

  it("describes each schedule in plain words and marks paused ones", async () => {
    await openTasks(seed(), "/tasks?view=recurring");
    expect(await screen.findByText("Daily review")).toBeInTheDocument();
    expect(screen.getByText(/Every day/)).toBeInTheDocument();
    expect(screen.getByText(/Weekly on Mon, Wed/)).toBeInTheDocument();
    expect(screen.getByText("Paused")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New task" })).not.toBeInTheDocument(); // header button is for one-off tasks
  });

  it("pauses, resumes and deletes (after confirming)", async () => {
    const fake = await openTasks(seed(), "/tasks?view=recurring");
    await userEvent.click(await screen.findByRole("button", { name: 'Pause "Daily review"' }));
    await waitFor(() => expect(fake.callsTo("PATCH", /recurring-tasks\/7$/)[0].body).toEqual({ active: false }));
    await userEvent.click(await screen.findByRole("button", { name: 'Resume "Weekly planning"' }));
    await waitFor(() => expect(fake.callsTo("PATCH", /recurring-tasks\/8$/)[0].body).toEqual({ active: true }));

    await userEvent.click(screen.getByRole("button", { name: 'Delete recurring task "Daily review"' }));
    const dlg = screen.getByRole("dialog", { name: "Delete recurring task?" });
    expect(dlg).toHaveTextContent("Tasks it already created stay");
    await userEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("Daily review")).not.toBeInTheDocument());
    expect(fake.callsTo("DELETE", /recurring-tasks\/7$/)).toHaveLength(1);
  });

  it("requires at least one weekday for a weekly task, then sends the chosen days", async () => {
    const fake = await openTasks({}, "/tasks?view=recurring");
    await userEvent.click(await screen.findByRole("button", { name: "New recurring task" }));
    const dlg = screen.getByRole("dialog", { name: "New recurring task" });
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Gym");
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Repeats/), "weekly");

    await userEvent.click(within(dlg).getByRole("button", { name: "Create recurring task" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("at least one day");
    expect(fake.callsTo("POST", /recurring-tasks$/)).toHaveLength(0);

    await userEvent.click(within(dlg).getByRole("button", { name: "Wed" }));
    await userEvent.click(within(dlg).getByRole("button", { name: "Mon" }));
    expect(within(dlg).getByRole("button", { name: "Mon" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create recurring task" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(fake.callsTo("POST", /recurring-tasks$/)[0].body).toMatchObject({
      title: "Gym",
      frequency: "weekly",
      days_of_week: [0, 2],
      day_of_month: null,
      start_date: TODAY,
    });
    expect(await screen.findByText("Gym")).toBeInTheDocument();
  });

  it("asks for a day of the month only for monthly tasks", async () => {
    await openTasks({}, "/tasks?view=recurring");
    await userEvent.click(await screen.findByRole("button", { name: "New recurring task" }));
    const dlg = screen.getByRole("dialog");
    expect(within(dlg).queryByLabelText(/^Day of the month/)).not.toBeInTheDocument();
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Repeats/), "monthly");
    expect(within(dlg).getByLabelText(/^Day of the month/)).toBeInTheDocument();
    expect(within(dlg).getByText(/falls on the last day/)).toBeInTheDocument();
  });
});
