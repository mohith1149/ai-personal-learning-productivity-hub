import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { setModelChoice } from "../api/assistant";
import { parseBlocks } from "../components/Markdown";
import { installFakeApi } from "./fakeApi";
import { installFakeAssistant, type FakeAssistant } from "./fakeAssistant";
import { renderAt } from "./render";

const CONNECTED = { provider: "groq", connected: true, model: "llama-3.3-70b-versatile", live_verified: false, message: "A provider is configured, but the live connection has not been tested yet." };

async function open(seed: Partial<FakeAssistant> = {}) {
  const fake = installFakeApi();
  const store = installFakeAssistant(fake, { status: CONNECTED, ...seed });
  renderAt("/assistant");
  await screen.findByRole("heading", { name: "AI assistant", level: 1 });
  return { fake, store };
}

const card = (name: string) => screen.findByRole("region", { name });
const chatCard = () => card("Chat");

beforeEach(() => {
  setModelChoice(null);
});

describe("chat window", () => {
  it("sends with Enter, keeps a new line with Shift+Enter, and clears the box when the answer arrives", async () => {
    const { fake } = await open();
    const chat = await chatCard();
    const box = await within(chat).findByRole("textbox", { name: "Message" });
    await userEvent.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(box).toHaveValue("line one\nline two");
    expect(fake.callsTo("POST", /ai\/chat$/)).toHaveLength(0);
    await userEvent.type(box, "{Enter}");
    await waitFor(() => expect(fake.callsTo("POST", /ai\/chat$/)).toHaveLength(1));
    expect(fake.callsTo("POST", /ai\/chat$/)[0].body).toMatchObject({ message: "line one\nline two", conversation_id: null });
    expect(await within(chat).findByText("You have 2 open tasks today.")).toBeInTheDocument();
    expect(box).toHaveValue("");
  });

  it("offers suggestions on an empty chat, sends one when clicked, then hides them", async () => {
    const { fake } = await open();
    const chat = await chatCard();
    await userEvent.click(await within(chat).findByRole("button", { name: "What is overdue?" }));
    await waitFor(() => expect(fake.callsTo("POST", /ai\/chat$/)[0].body).toMatchObject({ message: "What is overdue?" }));
    await within(chat).findByText("You have 2 open tasks today.");
    expect(within(chat).queryByRole("button", { name: "What is overdue?" })).not.toBeInTheDocument();
  });

  it("renders the reply's formatting instead of raw symbols, and never as HTML", async () => {
    await open({ chatReply: "**Today:**\n- Read paper\n- Write `notes`\n\n1. First\n2. Second\n<script>alert(1)</script>" });
    const chat = await chatCard();
    await userEvent.type(await within(chat).findByRole("textbox", { name: "Message" }), "plan{Enter}");
    const log = await within(chat).findByRole("log", { name: "Conversation" });
    expect((await within(log).findByText("Today:")).tagName).toBe("STRONG");
    expect(within(log).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Read paper", "Write notes", "First", "Second"]);
    expect(within(log).getByText("notes").tagName).toBe("CODE");
    expect(log.textContent).not.toContain("**");
    expect(log.querySelector("script")).toBeNull();
    expect(log.textContent).toContain("<script>alert(1)</script>");
  });

  it("shows a provider error and keeps what was typed so it can be retried", async () => {
    const { fake } = await open();
    fake.failNext(/POST \/api\/ai\/chat$/, 502, "Groq's rate limit was reached. Wait a minute and try again, or pick another model");
    const chat = await chatCard();
    await userEvent.type(await within(chat).findByRole("textbox", { name: "Message" }), "hello{Enter}");
    expect(await within(chat).findByRole("alert")).toHaveTextContent("rate limit");
    expect(within(chat).getByRole("textbox", { name: "Message" })).toHaveValue("hello");
  });

  it("starts a fresh conversation with New chat", async () => {
    const { fake } = await open();
    const chat = await chatCard();
    await userEvent.type(await within(chat).findByRole("textbox", { name: "Message" }), "one{Enter}");
    await within(chat).findByText("You have 2 open tasks today.");
    await userEvent.click(within(chat).getByRole("button", { name: "New chat" }));
    expect(within(chat).queryByRole("button", { name: "New chat" })).not.toBeInTheDocument();
    await userEvent.type(within(chat).getByRole("textbox", { name: "Message" }), "two{Enter}");
    await waitFor(() => expect(fake.callsTo("POST", /ai\/chat$/)).toHaveLength(2));
    expect(fake.callsTo("POST", /ai\/chat$/)[1].body).toMatchObject({ message: "two", conversation_id: null });
  });
});

describe("model menu", () => {
  it("lists every provider that has a key with its models, marking each default", async () => {
    await open();
    const menu = await within(await chatCard()).findByRole("combobox", { name: "Model" });
    expect(menu).toHaveValue("groq|llama-3.3-70b-versatile");
    expect(within(menu).getByRole("group", { name: "Groq (free)" })).toBeInTheDocument();
    expect(within(menu).getByRole("group", { name: "Google Gemini (free tier)" })).toBeInTheDocument();
    expect(within(menu).getAllByRole("option").map((o) => o.textContent)).toEqual(["llama-3.3-70b-versatile (default)", "openai/gpt-oss-20b", "gemini-3.5-flash (default)"]);
  });

  it("sends the picked provider and model with the chat and the connection test, and remembers the pick", async () => {
    const { fake } = await open();
    const chat = await chatCard();
    await userEvent.selectOptions(await within(chat).findByRole("combobox", { name: "Model" }), "gemini|gemini-3.5-flash");
    expect(localStorage.getItem("hub.ai-model")).toContain("gemini-3.5-flash");
    await userEvent.type(within(chat).getByRole("textbox", { name: "Message" }), "hi{Enter}");
    await waitFor(() => expect(fake.callsTo("POST", /ai\/chat$/)[0].body).toMatchObject({ message: "hi", provider: "gemini", model: "gemini-3.5-flash" }));
    const s = await card("Assistant status");
    expect(within(s).getByText("Model: gemini-3.5-flash")).toBeInTheDocument();
    await userEvent.click(within(s).getByRole("button", { name: "Test the connection" }));
    await waitFor(() => expect(fake.callsTo("POST", /ai\/check$/)[0].body).toEqual({ provider: "gemini", model: "gemini-3.5-flash" }));
  });

  it("sends no provider or model until one is picked, so the server default applies", async () => {
    const { fake } = await open();
    await userEvent.type(await within(await chatCard()).findByRole("textbox", { name: "Message" }), "hi{Enter}");
    await waitFor(() => expect(fake.callsTo("POST", /ai\/chat$/)).toHaveLength(1));
    const body = fake.callsTo("POST", /ai\/chat$/)[0].body!;
    expect("provider" in body || "model" in body).toBe(false);
  });

  it("drops a remembered pick whose provider no longer has a key", async () => {
    setModelChoice({ provider: "anthropic", model: "claude-opus-5-5" });
    await open();
    const menu = await within(await chatCard()).findByRole("combobox", { name: "Model" });
    await waitFor(() => expect(localStorage.getItem("hub.ai-model")).toBeNull());
    expect(menu).toHaveValue("groq|llama-3.3-70b-versatile");
  });

  it("is not shown when no provider has a key", async () => {
    await open({ models: { default_provider: null, providers: [] } });
    await within(await chatCard()).findByRole("textbox", { name: "Message" });
    expect(screen.queryByRole("combobox", { name: "Model" })).not.toBeInTheDocument();
  });
});

describe("markdown parsing", () => {
  it("groups lists and keeps paragraphs, headings and code apart", () => {
    expect(parseBlocks("# Title\nIntro line\n\n- a\n- b\n\n1) one\n2) two\n```\ncode here\n```\nend")).toEqual([
      { kind: "h", text: "Title" },
      { kind: "p", text: "Intro line" },
      { kind: "ul", items: ["a", "b"] },
      { kind: "ol", items: ["one", "two"] },
      { kind: "code", text: "code here" },
      { kind: "p", text: "end" },
    ]);
  });

  it("does not choke on an unclosed code fence or unmatched bold markers", () => {
    expect(parseBlocks("```\nnever closed")).toEqual([{ kind: "code", text: "never closed" }]);
    expect(parseBlocks("a ** b")).toEqual([{ kind: "p", text: "a ** b" }]);
  });
});
