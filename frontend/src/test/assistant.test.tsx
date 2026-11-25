import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { installFakeApi } from "./fakeApi";
import { setModelChoice } from "../api/assistant";
import { installFakeAssistant, mkPending, type FakeAssistant } from "./fakeAssistant";
import { renderAt } from "./render";

async function open(seed: Partial<FakeAssistant> = {}) {
  const fake = installFakeApi();
  const store = installFakeAssistant(fake, seed);
  renderAt("/assistant");
  await screen.findByRole("heading", { name: "AI assistant", level: 1 });
  return { fake, store };
}

beforeEach(() => {
  setModelChoice(null);
});

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
    await open({ status: { provider: "groq", connected: true, model: "llama-3.3-70b-versatile", live_verified: false, message: "A provider is configured, but the live connection has not been tested yet." } });
    const s = await card("Assistant status");
    expect(await within(s).findByText("Provider configured")).toBeInTheDocument();
    expect(within(s).getByText("Model: llama-3.3-70b-versatile")).toBeInTheDocument();
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

  it("has no memory section any more", async () => {
    await open();
    await card("Assistant status");
    expect(screen.queryByRole("region", { name: "Memory" })).not.toBeInTheDocument();
    expect(screen.queryByText(/memory/i)).not.toBeInTheDocument();
  });

  it("is in the sidebar as a real page, not a placeholder", async () => {
    await open();
    expect(screen.queryByText("Not built yet")).not.toBeInTheDocument();
    expect(within(await screen.findByRole("navigation", { name: "Main" })).getByRole("link", { name: /AI assistant/ })).toHaveAttribute("aria-current", "page");
  });

  const CONNECTED = { provider: "groq", connected: true, model: "llama-3.3-70b-versatile", live_verified: false, message: "A provider is configured, but the live connection has not been tested yet." };

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
    expect(within(log).getByText("today tasks")).toBeInTheDocument();         // a friendly name, not get_today_tasks
    expect(within(log).queryByText("get_today_tasks")).not.toBeInTheDocument();
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
