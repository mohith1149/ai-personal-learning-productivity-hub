import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi, USER } from "./fakeApi";
import { installFakeHabits, isoDaysAgo, mkHabit, type FakeHabits } from "./fakeHabits";
import { todayIn } from "../lib/dates";
import { renderAt } from "./render";

const TODAY = () => todayIn(USER.timezone);

async function open(seed: Partial<FakeHabits> = {}) {
  const fake = installFakeApi();
  const store = installFakeHabits(fake, seed);
  renderAt("/habits");
  await screen.findByRole("heading", { name: "Habits", level: 1 });
  return { fake, store };
}

const log = (date: string, completed = true) => ({ date, completed, value: null, note: null });
const card = async (name: string) => (await screen.findByRole("heading", { name, level: 3 })).closest("li")!;

describe("habits page", () => {
  it("shows an honest empty state and creates a habit (validating first)", async () => {
    const { fake, store } = await open();
    expect(await screen.findByText("No habits yet")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "New habit" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "New habit" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Create habit" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Please give the habit a name.");
    expect(fake.callsTo("POST", /\/api\/habits$/)).toHaveLength(0);

    await userEvent.type(within(dialog).getByLabelText("Name"), "Exercise");
    await userEvent.selectOptions(within(dialog).getByLabelText("How often"), "weekly");
    await userEvent.clear(within(dialog).getByLabelText("Days per week"));
    await userEvent.type(within(dialog).getByLabelText("Days per week"), "9");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create habit" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("from 1 to 7");
    await userEvent.clear(within(dialog).getByLabelText("Days per week"));
    await userEvent.type(within(dialog).getByLabelText("Days per week"), "4");
    await userEvent.type(within(dialog).getByLabelText("Daily amount (optional)"), "30");
    await userEvent.type(within(dialog).getByLabelText("Unit (optional)"), "minutes");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create habit" }));

    const c = await card("Exercise");
    expect(within(c).getByText(/4 days a week · goal 30 minutes a day/)).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/habits$/)[0].body).toMatchObject({
      name: "Exercise", frequency: "weekly", target_per_period: 4, target_value: 30, unit: "minutes", active: true, start_date: TODAY(),
    });
    expect(store.habits).toHaveLength(1);
  });

  it("shows the server's message for a duplicate name", async () => {
    await open({ habits: [mkHabit({ id: 1, name: "Reading" })] });
    await userEvent.click(await screen.findByRole("button", { name: "New habit" }));
    const dialog = await screen.findByRole("dialog", { name: "New habit" });
    await userEvent.type(within(dialog).getByLabelText("Name"), "reading");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create habit" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already have a habit with that name");
  });

  it("marking done today records the day and the streak, progress and 'due' count update immediately", async () => {
    const { fake } = await open({
      habits: [mkHabit({ id: 1, name: "Reading" }), mkHabit({ id: 2, name: "Coding" })],
      logs: { 1: [log(isoDaysAgo(2)), log(isoDaysAgo(1))] },
    });
    const c = await card("Reading");
    expect(within(c).getByLabelText("Reading streak")).toHaveTextContent("2 days");
    expect(await screen.findByText("2 habits still to do today.")).toBeInTheDocument();

    await userEvent.click(within(c).getByRole("button", { name: "Mark Reading done today" }));
    await waitFor(() => expect(within(c).getByLabelText("Reading streak")).toHaveTextContent("3 days · best 3 days"));
    expect(fake.callsTo("PUT", new RegExp(`/api/habits/1/logs/${TODAY()}$`))[0].body).toEqual({ completed: true });
    expect(within(c).getByRole("button", { name: "Undo Reading for today" })).toBeInTheDocument();
    expect(await screen.findByText("1 habit still to do today.")).toBeInTheDocument();
  });

  it("undoing today lowers the streak again", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading" })], logs: { 1: [log(isoDaysAgo(1)), log(TODAY())] } });
    const c = await card("Reading");
    expect(within(c).getByLabelText("Reading streak")).toHaveTextContent("2 days");
    await userEvent.click(within(c).getByRole("button", { name: "Undo Reading for today" }));
    await waitFor(() => expect(within(c).getByLabelText("Reading streak")).toHaveTextContent(/^1 day/));
    expect(fake.callsTo("DELETE", new RegExp(`/logs/${TODAY()}$`))).toHaveLength(1);
  });

  it("a missed day shows a broken streak, not an invented one", async () => {
    await open({ habits: [mkHabit({ id: 1, name: "Reading" })], logs: { 1: [log(isoDaysAgo(5)), log(isoDaysAgo(4)), log(isoDaysAgo(3))] } });
    const c = await card("Reading");
    expect(within(c).getByLabelText("Reading streak")).toHaveTextContent("0 days · best 3 days");
  });

  it("the 28-day strip toggles any past day and cannot touch days before the start", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading", start_date: isoDaysAgo(10) })], logs: { 1: [] } });
    const c = await card("Reading");
    const d = isoDaysAgo(3);
    await userEvent.click(within(c).getByRole("button", { name: `Mark Reading done on ${d}` }));
    await waitFor(() => expect(within(c).getByRole("button", { name: `Undo Reading on ${d}` })).toBeInTheDocument());
    expect(fake.callsTo("PUT", new RegExp(`/logs/${d}$`))).toHaveLength(1);
    await userEvent.click(within(c).getByRole("button", { name: `Undo Reading on ${d}` }));
    await waitFor(() => expect(within(c).getByRole("button", { name: `Mark Reading done on ${d}` })).toBeInTheDocument());
    expect(within(c).getByRole("button", { name: `Mark Reading done on ${isoDaysAgo(20)}` })).toBeDisabled();
  });

  it("shows week and month progress from the records", async () => {
    const days = [0, 1, 2, 3, 4].map((n) => log(isoDaysAgo(n)));
    await open({ habits: [mkHabit({ id: 1, name: "Reading", start_date: isoDaysAgo(2) })], logs: { 1: days } });
    const c = await card("Reading");
    expect(within(c).getByText(/This month: 3 of 3 days \(100%\)/)).toBeInTheDocument();    // days before the start date don't count
  });

  it("a weekly habit measures the week against its days-per-week goal", async () => {
    await open({ habits: [mkHabit({ id: 1, name: "Gym", frequency: "weekly", target_per_period: 3 })], logs: { 1: [log(TODAY())] } });
    const c = await card("Gym");
    expect(within(c).getByText(/This week: 1 of 3 days/)).toBeInTheDocument();
    expect(within(c).getByRole("progressbar", { name: "Gym this week" })).toHaveAttribute("aria-valuenow", "33");
    expect(within(c).getByLabelText("Gym streak")).toHaveTextContent("0 weeks · best 0 weeks");
    expect(within(c).getByText(/This month: 1 days done/)).toBeInTheDocument();
  });

  it("records an amount and note for a chosen day and validates it", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading", unit: "pages" })] });
    await userEvent.click(await screen.findByRole("button", { name: "Add details for Reading" }));
    const dialog = await screen.findByRole("dialog", { name: "Record: Reading" });
    await userEvent.type(within(dialog).getByLabelText("Amount (pages)"), "-5");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save as done" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("0 or more");
    expect(fake.callsTo("PUT", /logs/)).toHaveLength(0);
    await userEvent.clear(within(dialog).getByLabelText("Amount (pages)"));
    await userEvent.type(within(dialog).getByLabelText("Amount (pages)"), "25");
    await userEvent.type(within(dialog).getByLabelText("Note"), "chapter 4");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save as done" }));
    expect(await within(await card("Reading")).findByText(/Today: 25 pages · chapter 4/)).toBeInTheDocument();
    expect(fake.callsTo("PUT", /logs/)[0].body).toEqual({ completed: true, value: 25, note: "chapter 4" });
  });

  it("shows the server's rejection inside the record dialog", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading" })] });
    fake.failNext(/^PUT \/api\/habits\/1\/logs/, 422, "You can't record a habit for a future day");
    await userEvent.click(await screen.findByRole("button", { name: "Add details for Reading" }));
    const dialog = await screen.findByRole("dialog", { name: "Record: Reading" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save as done" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("future day");
  });

  it("history lists records and deleting one fixes the streak", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading" })], logs: { 1: [{ date: isoDaysAgo(1), completed: true, value: 10, note: "ok" }, log(TODAY())] } });
    const c = await card("Reading");
    await userEvent.click(within(c).getByRole("button", { name: "History of Reading" }));
    const dialog = await screen.findByRole("dialog", { name: "History: Reading" });
    const list = await within(dialog).findByRole("list", { name: "Habit history" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getAllByRole("listitem")[1]).toHaveTextContent(/10 · ok/);
    await userEvent.click(within(list).getByRole("button", { name: `Delete record for ${isoDaysAgo(1)}` }));
    await waitFor(() => expect(within(dialog).getAllByRole("listitem")).toHaveLength(1));
    expect(fake.callsTo("DELETE", new RegExp(`/logs/${isoDaysAgo(1)}$`))).toHaveLength(1);
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(within(c).getByLabelText("Reading streak")).toHaveTextContent(/^1 day/));
  });

  it("edits a habit and can make it inactive (left out of 'due today')", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading" })] });
    expect(await screen.findByText("1 habit still to do today.")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Edit Reading" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit habit" });
    await userEvent.clear(within(dialog).getByLabelText("Name"));
    await userEvent.type(within(dialog).getByLabelText("Name"), "Deep reading");
    await userEvent.click(within(dialog).getByLabelText(/^Active/));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: /^Deep reading/, level: 3 })).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /habits\/1$/)[0].body).toMatchObject({ name: "Deep reading", active: false });
    expect(await screen.findByText("Inactive")).toBeInTheDocument();
    expect(await screen.findByText(/Nothing left to do today/)).toBeInTheDocument();
  });

  it("deletes a habit only after confirmation, saying how many records go with it", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading" })], logs: { 1: [log(isoDaysAgo(1)), log(TODAY())] } });
    await userEvent.click(await screen.findByRole("button", { name: "Delete Reading" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete habit?" });
    expect(dialog).toHaveTextContent("2 completed-day records");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /habits\/1$/)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Delete Reading" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No habits yet")).toBeInTheDocument();
    expect(fake.callsTo("DELETE", /habits\/1$/)).toHaveLength(1);
  });

  it("shows the server error when habits can't load, and retries", async () => {
    const fake = installFakeApi();
    installFakeHabits(fake, { habits: [mkHabit({ id: 1, name: "Reading" })] });
    fake.failNext(/^GET \/api\/habits$/, 500, "Database is down");
    renderAt("/habits");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await card("Reading")).toBeInTheDocument();
  });

  it("shows the server's message if marking done fails", async () => {
    const { fake } = await open({ habits: [mkHabit({ id: 1, name: "Reading" })] });
    fake.failNext(/^PUT \/api\/habits\/1\/logs/, 500, "Disk full");
    const c = await card("Reading");
    await userEvent.click(within(c).getByRole("button", { name: "Mark Reading done today" }));
    expect(await within(c).findByRole("alert")).toHaveTextContent("Disk full");
  });

  it("the sidebar link is live (no Soon badge)", async () => {
    await open();
    const link = within(screen.getAllByRole("navigation")[0]).getByRole("link", { name: /Habits/ });
    expect(within(link).queryByText("Soon")).not.toBeInTheDocument();
  });
});
