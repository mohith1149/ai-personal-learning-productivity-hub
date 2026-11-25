import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi } from "./fakeApi";
import { installFakeAssistant, mkMemory, mkPending, type FakeAssistant } from "./fakeAssistant";
import { renderAt } from "./render";

async function open(seed: Partial<FakeAssistant> = {}) {
  const fake = installFakeApi();
  const store = installFakeAssistant(fake, seed);
  renderAt("/assistant");
  await screen.findByRole("heading", { name: "AI assistant", level: 1 });
  return { fake, store };
}

const card = (name: string) => screen.findByRole("region", { name });

describe("AI assistant", () => {
  it("says honestly that the assistant is not connected and has not been tested live", async () => {
    await open();
    const s = await card("Assistant status");
    expect(await within(s).findByText("Not connected")).toBeInTheDocument();
    expect(within(s).getByText("Not tested live")).toBeInTheDocument();
    expect(within(s).getByText(/AI is off/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message/i })).not.toBeInTheDocument();       // no pretend chat box when nothing is connected
    expect(within(s).queryByRole("button", { name: "Test the connection" })).not.toBeInTheDocument();
  });

  it("shows a configured provider as configured but still untested", async () => {
    await open({ status: { provider: "anthropic", connected: true, model: "claude-opus-5-5", live_verified: false, message: "A provider is configured, but the live connection has not been tested yet." } });
    const s = await card("Assistant status");
    expect(await within(s).findByText("Provider configured")).toBeInTheDocument();
    expect(within(s).getByText("Model: claude-opus-5-5")).toBeInTheDocument();
    expect(within(s).getByText("Not tested live")).toBeInTheDocument();
  });

  it("lists what the assistant can do, split into look-ups and proposals", async () => {
    await open();
    const t = await card("What the assistant can do");
    const reads = await within(t).findByRole("list", { name: "Read tools" });
    expect(within(reads).getAllByRole("listitem").map((li) => li.querySelector("code")?.textContent)).toEqual(["get_today_tasks", "get_roadmap_progress"]);
    const writes = within(t).getByRole("list", { name: "Write tools" });
    expect(within(writes).getByText("create_task")).toBeInTheDocument();
    expect(within(t).getByText(/Propose changes \(needs your approval\)/)).toBeInTheDocument();
  });

  it("shows an empty approval queue plainly", async () => {
    await open();
    expect(await within(await card("Waiting for approval")).findByText("No proposals are waiting.")).toBeInTheDocument();
  });

  it("approves a proposal, which then leaves the queue", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ pending: [mkPending({ id: 1, summary: 'Create the task "Read paper"' }), mkPending({ id: 2, summary: "Move task #5 to 2026-11-30" })] });
    const q = await card("Waiting for approval");
    const list = await within(q).findByRole("list", { name: "Proposals" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    await user.click(within(list).getByRole("button", { name: 'Approve: Create the task "Read paper"' }));
    await waitFor(() => expect(fake.callsTo("POST", /ai\/pending\/1\/approve$/)).toHaveLength(1));
    await waitFor(() => expect(within(q).getAllByRole("listitem")).toHaveLength(1));
    expect(within(q).queryByText('Create the task "Read paper"')).not.toBeInTheDocument();
    expect(fake.callsTo("POST", /reject/)).toHaveLength(0);
  });

  it("rejects a proposal without approving it", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ pending: [mkPending({ id: 3, summary: "Mark task #9 as completed" })] });
    await user.click(await screen.findByRole("button", { name: "Reject: Mark task #9 as completed" }));
    await waitFor(() => expect(fake.callsTo("POST", /ai\/pending\/3\/reject$/)).toHaveLength(1));
    expect(fake.callsTo("POST", /approve/)).toHaveLength(0);
    expect(await within(await card("Waiting for approval")).findByText("No proposals are waiting.")).toBeInTheDocument();
  });

  it("shows the server's message when a proposal can't be approved", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ pending: [mkPending({ id: 4, summary: "Mark task #9 as completed" })] });
    fake.failNext(/POST \/api\/ai\/pending\/4\/approve$/, 409, "This proposal was already executed");
    await user.click(await screen.findByRole("button", { name: "Approve: Mark task #9 as completed" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already executed");
  });

  it("adds a memory, and checks it first", async () => {
    const user = userEvent.setup();
    const { fake } = await open();
    const m = await card("Memory");
    expect(await within(m).findByText("Nothing saved yet.")).toBeInTheDocument();
    await user.type(within(m).getByLabelText("Add a note"), "hi");
    await user.click(within(m).getByRole("button", { name: "Save note" }));
    expect(await within(m).findByRole("alert")).toHaveTextContent("at least 3 characters");
    expect(fake.callsTo("POST", /memories$/)).toHaveLength(0);
    await user.clear(within(m).getByLabelText("Add a note"));
    await user.type(within(m).getByLabelText("Add a note"), "Prefers short answers");
    await user.selectOptions(within(m).getByLabelText("Type"), "goal");
    await user.click(within(m).getByRole("button", { name: "Save note" }));
    await waitFor(() => expect(fake.callsTo("POST", /memories$/)[0].body).toEqual({ content: "Prefers short answers", kind: "goal" }));
    const list = await within(m).findByRole("list", { name: "Saved notes" });
    expect(within(list).getByText("Prefers short answers")).toBeInTheDocument();
    expect(within(list).getByText("goal")).toBeInTheDocument();
    expect(within(m).getByLabelText("Add a note")).toHaveValue("");
  });

  it("shows a duplicate-note error from the server", async () => {
    const user = userEvent.setup();
    await open({ memories: [mkMemory({ content: "Prefers short answers" })] });
    const m = await card("Memory");
    await user.type(await within(m).findByLabelText("Add a note"), "prefers short answers");
    await user.click(within(m).getByRole("button", { name: "Save note" }));
    expect(await within(m).findByRole("alert")).toHaveTextContent("already remembered");
  });

  it("labels who added each note and deletes one", async () => {
    const user = userEvent.setup();
    const { fake, store } = await open({ memories: [mkMemory({ id: 1, content: "Studies at night", source: "assistant", kind: "fact" }), mkMemory({ id: 2, content: "Likes brief replies" })] });
    const list = await within(await card("Memory")).findByRole("list", { name: "Saved notes" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("added by assistant");
    expect(rows[1]).toHaveTextContent("added by you");
    await user.click(within(list).getByRole("button", { name: "Delete memory: Studies at night" }));
    await waitFor(() => expect(fake.callsTo("DELETE", /memories\/1$/)).toHaveLength(1));
    await waitFor(() => expect(within(list).queryByText("Studies at night")).not.toBeInTheDocument());
    expect(store.memories.map((x) => x.id)).toEqual([2]);
  });

  it("is in the sidebar as a real page, not a placeholder", async () => {
    await open();
    expect(screen.queryByText("Not built yet")).not.toBeInTheDocument();
    expect(within(await screen.findByRole("navigation", { name: "Main" })).getByRole("link", { name: /AI assistant/ })).toHaveAttribute("aria-current", "page");
  });

  const CONNECTED = { provider: "anthropic", connected: true, model: "claude-opus-5-5", live_verified: false, message: "A provider is configured, but the live connection has not been tested yet." };

  it("tests the connection on request and shows the real result", async () => {
    await open({ status: CONNECTED });
    const s = await card("Assistant status");
    await userEvent.click(await within(s).findByRole("button", { name: "Test the connection" }));
    expect(await within(s).findByText(/The connection works/)).toBeInTheDocument();
  });

  it("chats: shows your message, the reply and what was looked up", async () => {
    await open({ status: CONNECTED });
    const chat = await card("Chat");
    await userEvent.type(await within(chat).findByRole("textbox", { name: "Message" }), "What is on today?");
    await userEvent.click(within(chat).getByRole("button", { name: "Send" }));
    const log = await within(chat).findByRole("log", { name: "Conversation" });
    expect(await within(log).findByText("What is on today?")).toBeInTheDocument();
    expect(await within(log).findByText("You have 2 open tasks today.")).toBeInTheDocument();
    expect(within(log).getByText(/Looked up: get_today_tasks/)).toBeInTheDocument();
  });

  it("says nothing has changed when the assistant proposes something, and lists it for approval", async () => {
    await open({ status: CONNECTED, chatProposals: 1 });
    const chat = await card("Chat");
    await userEvent.type(await within(chat).findByRole("textbox", { name: "Message" }), "Add a task");
    await userEvent.click(within(chat).getByRole("button", { name: "Send" }));
    expect(await within(chat).findByText(/Nothing has changed yet/)).toBeInTheDocument();
    expect(await within(await card("Waiting for approval")).findByRole("list", { name: "Proposals" })).toBeInTheDocument();
  });
});
