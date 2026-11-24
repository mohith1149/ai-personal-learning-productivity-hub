import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { todayIn } from "../lib/dates";
import { installFakeApi } from "./fakeApi";
import { defaultRoadmap, installFakeRoadmap, type FakeRoadmap } from "./fakeRoadmap";
import { renderAt } from "./render";
import { USER } from "./fakeApi";

async function open(seed: FakeRoadmap = defaultRoadmap()) {
  const fake = installFakeApi();
  const store = installFakeRoadmap(fake, seed);
  renderAt("/roadmap");
  await screen.findByRole("heading", { name: "AI roadmap", level: 1 });
  return { fake, store };
}

const stage = (n: number) => screen.findByRole("region", { name: new RegExp(`^Stage ${n}`) });
const rowOf = async (title: string) => (await screen.findByRole("combobox", { name: `Status of ${title}` })).closest("li")!;

describe("roadmap page", () => {
  it("shows every stage with its topics, all not started, with 0% progress and no invented data", async () => {
    await open();
    const s1 = await stage(1);
    expect(within(s1).getAllByRole("listitem").map((li) => li.querySelector("p")?.textContent)).toEqual(["Python", "Java fundamentals", "Git and GitHub"]);
    expect(within(s1).getByRole("progressbar", { name: /Stage 1 .* progress/ })).toHaveAttribute("aria-valuenow", "0");
    expect(within(s1).getByText(/0 of 3 completed · 0 in progress · 0m studied/)).toBeInTheDocument();
    for (const sel of screen.getAllByRole("combobox", { name: /^Status of / })) expect(sel).toHaveValue("not_started");
    const overall = screen.getByRole("region", { name: "Overall roadmap progress" });
    expect(within(overall).getByText("Topics").nextSibling).toHaveTextContent("5");
    expect(within(overall).getByText("Not started").nextSibling).toHaveTextContent("5");
    expect(within(overall).getByText("Study time").nextSibling).toHaveTextContent("0m");
    expect(within(overall).getByText("Python")).toBeInTheDocument(); // next up
  });

  it("changes a topic's status from the menu and recomputes stage and overall progress", async () => {
    const { fake } = await open();
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Status of Python" }), "completed");
    await waitFor(() => expect(within(screen.getByRole("region", { name: /^Stage 1/ })).getByText(/1 of 3 completed/)).toBeInTheDocument());
    expect(fake.callsTo("POST", /roadmap\/topics\/101\/status$/)[0].body).toEqual({ status: "completed" });
    expect(within(await stage(1)).getByRole("progressbar", { name: /Stage 1/ })).toHaveAttribute("aria-valuenow", "33");
    const overall = screen.getByRole("region", { name: "Overall roadmap progress" });
    expect(within(overall).getByText("Completed").nextSibling).toHaveTextContent("1");
    expect(within(overall).getByText(/Next up:/)).toHaveTextContent("Java fundamentals");
    expect(within(overall).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20");
    expect(within(await rowOf("Python")).getByText(/completed Today/)).toBeInTheDocument();
  });

  it("supports every status transition, including reopening a completed topic", async () => {
    const { fake } = await open();
    const select = await screen.findByRole("combobox", { name: "Status of Java fundamentals" });
    await userEvent.selectOptions(select, "in_progress");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Status of Java fundamentals" })).toHaveValue("in_progress"));
    expect(within(await stage(1)).getByText(/0 of 3 completed · 1 in progress/)).toBeInTheDocument();
    await userEvent.selectOptions(select, "completed");
    await waitFor(() => expect(within(screen.getByRole("region", { name: /^Stage 1/ })).getByText(/1 of 3 completed · 0 in progress/)).toBeInTheDocument());
    await userEvent.selectOptions(select, "not_started");
    await waitFor(() => expect(within(screen.getByRole("region", { name: /^Stage 1/ })).getByText(/0 of 3 completed · 0 in progress/)).toBeInTheDocument());
    expect(fake.callsTo("POST", /topics\/102\/status$/).map((c) => (c.body as { status: string }).status)).toEqual(["in_progress", "completed", "not_started"]);
    expect(within(await rowOf("Java fundamentals")).queryByText(/completed /)).not.toBeInTheDocument();
  });

  it("completing every topic says so", async () => {
    const seed = defaultRoadmap();
    seed.stages.forEach((s) => s.topics.forEach((t) => Object.assign(t, { status: "completed", completed_at: "2026-11-01T10:00:00Z" })));
    await open(seed);
    expect(await screen.findByText("Every topic is completed.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Overall roadmap progress" })).toHaveAttribute("aria-valuenow", "100");
  });

  it("logging study time adds minutes and days, starts the topic, but never completes it", async () => {
    const { fake } = await open();
    await userEvent.click(await screen.findByRole("button", { name: "Log study time for PyTorch" }));
    const dialog = await screen.findByRole("dialog", { name: "Study time: PyTorch" });
    expect(within(dialog).getByText("No study time logged yet.")).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText("Minutes studied"));
    await userEvent.type(within(dialog).getByLabelText("Minutes studied"), "95");
    await userEvent.type(within(dialog).getByLabelText(/What did you cover/), "tensors");
    await userEvent.click(within(dialog).getByRole("button", { name: "Log study time" }));

    const history = await within(dialog).findByRole("list", { name: "Study history" });
    expect(within(history).getByText(/1h 35m/)).toBeInTheDocument();
    expect(within(history).getByText(/tensors/)).toBeInTheDocument();
    expect(fake.callsTo("POST", /topics\/201\/study$/)[0].body).toEqual({ minutes: 95, date: todayIn(USER.timezone), notes: "tensors" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    const row = await rowOf("PyTorch");
    await waitFor(() => expect(within(row).getByText(/1h 35m over 1 day/)).toBeInTheDocument());
    expect(within(row).getByRole("combobox")).toHaveValue("in_progress");
    expect(screen.getByRole("region", { name: "Overall roadmap progress" })).toHaveTextContent("1h 35m");
  });

  it("validates study minutes locally and deleting a session fixes the totals", async () => {
    const { fake, store } = await open();
    store.sessions.push({ id: 1, topic_id: 201, date: "2026-11-20", minutes: 40, notes: null, created_at: "2026-11-20T10:00:00Z" });
    await userEvent.click(await screen.findByRole("button", { name: "Log study time for PyTorch" }));
    const dialog = await screen.findByRole("dialog", { name: "Study time: PyTorch" });
    await userEvent.clear(within(dialog).getByLabelText("Minutes studied"));
    await userEvent.type(within(dialog).getByLabelText("Minutes studied"), "0");
    await userEvent.click(within(dialog).getByRole("button", { name: "Log study time" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("whole number from 1 to 1440");
    expect(fake.callsTo("POST", /study$/)).toHaveLength(0);

    await userEvent.click(await within(dialog).findByRole("button", { name: "Delete 40m session on 2026-11-20" }));
    expect(await within(dialog).findByText("No study time logged yet.")).toBeInTheDocument();
    expect(fake.callsTo("DELETE", /learning-sessions\/1$/)).toHaveLength(1);
  });

  it("adds a topic to a stage, rejects blanks and duplicates", async () => {
    const { fake } = await open();
    await userEvent.click(await screen.findByRole("button", { name: /^Add topic to Stage 2/ }));
    const dialog = await screen.findByRole("dialog", { name: /Add a topic to Stage 2/ });
    await userEvent.click(within(dialog).getByRole("button", { name: "Add topic" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Please give the topic a name.");
    await userEvent.type(within(dialog).getByLabelText("Topic"), "pytorch");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add topic" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already has a topic with that name");
    await userEvent.clear(within(dialog).getByLabelText("Topic"));
    await userEvent.type(within(dialog).getByLabelText("Topic"), "JAX");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add topic" }));
    expect(await within(await stage(2)).findByText("JAX")).toBeInTheDocument();
    expect(fake.callsTo("POST", /roadmap\/topics$/).at(-1)!.body).toEqual({ stage_id: 2, title: "JAX" });
    expect(within(await stage(2)).getByText(/0 of 3 completed/)).toBeInTheDocument();       // total grew
    expect(within(await rowOf("JAX")).getByRole("combobox")).toHaveValue("not_started");    // new topics start not started
  });

  it("saves notes and shows them on the topic", async () => {
    const { fake } = await open();
    await userEvent.click(await screen.findByRole("button", { name: "Notes for Python" }));
    const dialog = await screen.findByRole("dialog", { name: "Notes: Python" });
    await userEvent.type(within(dialog).getByLabelText("Notes"), "finish the decorators chapter");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save notes" }));
    expect(await within(await rowOf("Python")).findByText(/Note: finish the decorators chapter/)).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /topics\/101$/)[0].body).toEqual({ notes: "finish the decorators chapter" });
  });

  it("deletes a topic only after confirmation", async () => {
    const { fake } = await open();
    await userEvent.click(await screen.findByRole("button", { name: "Delete TensorFlow" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete topic?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /roadmap\/topics/)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Delete TensorFlow" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("TensorFlow")).not.toBeInTheDocument());
    expect(fake.callsTo("DELETE", /roadmap\/topics\/202$/)).toHaveLength(1);
  });

  it("shows the server's error and retries when the roadmap can't load", async () => {
    const fake = installFakeApi();
    installFakeRoadmap(fake);
    fake.failNext(/^GET \/api\/roadmap$/, 500, "Database is down");
    renderAt("/roadmap");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await stage(1)).toBeInTheDocument();
  });

  it("shows the server's message if a status change fails", async () => {
    const { fake } = await open();
    fake.failNext(/^POST \/api\/roadmap\/topics\/\d+\/status/, 500, "Disk full");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Status of Python" }), "completed");
    expect(await within(await rowOf("Python")).findByRole("alert")).toHaveTextContent("Disk full");
  });

  it("the sidebar link is live (no Soon badge)", async () => {
    await open();
    const link = within(screen.getAllByRole("navigation")[0]).getByRole("link", { name: /AI roadmap/ });
    expect(within(link).queryByText("Soon")).not.toBeInTheDocument();
  });
});
