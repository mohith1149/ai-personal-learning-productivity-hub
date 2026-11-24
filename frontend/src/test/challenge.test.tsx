import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { addDays, todayIn } from "../lib/dates";
import { installFakeApi, USER } from "./fakeApi";
import { installFakeChallenges, mkChallenge, type FakeChallenges } from "./fakeChallenges";
import { installFakeProjects, mkProject } from "./fakeProjects";
import { renderAt } from "./render";

const TODAY = () => todayIn(USER.timezone);

async function open(seed: Partial<FakeChallenges> = {}) {
  const fake = installFakeApi();
  installFakeProjects(fake, { projects: [mkProject({ id: 1, title: "RAG chatbot", repo_url: "https://github.com/me/rag" }), mkProject({ id: 2, title: "Agent playground" })] });
  const store = installFakeChallenges(fake, seed);
  renderAt("/challenge");
  await screen.findByRole("heading", { name: "Daily challenge", level: 1 });
  return { fake, store };
}

const today = () => screen.findByRole("region", { name: "Today's challenge" });

describe("daily challenge", () => {
  it("is a real page now, not a placeholder, and says evidence is unverified", async () => {
    await open();
    expect(await screen.findByText(/shown as/i)).toHaveTextContent(/Unverified/);
    expect(screen.queryByText("Not built yet")).not.toBeInTheDocument();
  });

  it("with nothing planned shows the planning form and an empty history, with no invented data", async () => {
    await open();
    const card = await today();
    expect(within(card).getByRole("radio", { name: /Continue an existing project/ })).toBeChecked();
    expect(within(card).getByRole("button", { name: "Plan today's challenge" })).toBeInTheDocument();
    expect(await screen.findByText("No challenges yet")).toBeInTheDocument();
    const stats = screen.getByRole("region", { name: "Challenge statistics" });
    expect(within(stats).getByText("Current streak").nextSibling).toHaveTextContent("0 days");
    expect(screen.queryByRole("list", { name: "Suggestions" })).not.toBeInTheDocument();
  });

  it("plans an existing project, sending the project id and trimmed task", async () => {
    const user = userEvent.setup();
    const { fake } = await open();
    const card = await today();
    await user.selectOptions(await within(card).findByRole("combobox", { name: "Project" }), "RAG chatbot");
    await user.type(within(card).getByLabelText("What will you build or do today?"), "  Add the retrieval step  ");
    await user.type(within(card).getByLabelText(/Estimated minutes/), "60");
    await user.click(within(card).getByRole("button", { name: "Plan today's challenge" }));
    await waitFor(() => expect(fake.callsTo("POST", /challenges$/)[0].body).toEqual({ mode: "existing_project", planned_task: "Add the retrieval step", project_id: 1, estimated_minutes: 60 }));
    expect(await within(await today()).findByText("Add the retrieval step")).toBeInTheDocument();
    expect(within(await today()).getByText("Planned")).toBeInTheDocument();
  });

  it("plans a new project", async () => {
    const user = userEvent.setup();
    const { fake } = await open();
    const card = await today();
    await user.click(within(card).getByRole("radio", { name: /Start a new project/ }));
    await user.type(within(card).getByLabelText("New project name"), "Eval harness");
    await user.type(within(card).getByLabelText(/GitHub repository/), "https://github.com/me/evals");
    await user.type(within(card).getByLabelText("What will you build or do today?"), "Scaffold the runner");
    await user.click(within(card).getByRole("button", { name: "Plan today's challenge" }));
    await waitFor(() =>
      expect(fake.callsTo("POST", /challenges$/)[0].body).toEqual({ mode: "new_project", planned_task: "Scaffold the runner", new_project: { title: "Eval harness", repo_url: "https://github.com/me/evals" } }),
    );
    expect(await within(await today()).findByText(/New project:/)).toBeInTheDocument();
  });

  it("checks the plan form before calling the server", async () => {
    const user = userEvent.setup();
    const { fake } = await open();
    const card = await today();
    await user.click(within(card).getByRole("button", { name: "Plan today's challenge" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Choose the project you will continue");
    await user.selectOptions(within(card).getByRole("combobox", { name: "Project" }), "RAG chatbot");
    await user.click(within(card).getByRole("button", { name: "Plan today's challenge" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Say what you will build");
    await user.type(within(card).getByLabelText("What will you build or do today?"), "Something real");
    await user.type(within(card).getByLabelText(/Estimated minutes/), "0");
    await user.click(within(card).getByRole("button", { name: "Plan today's challenge" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("whole number from 1 to 1440");
    expect(fake.callsTo("POST", /challenges$/)).toHaveLength(0);
  });

  it("shows the server's message when the day already has a challenge", async () => {
    const user = userEvent.setup();
    const { fake } = await open();
    const card = await today();
    fake.failNext(/POST \/api\/challenges$/, 409, "That day already has a challenge");
    await user.selectOptions(await within(card).findByRole("combobox", { name: "Project" }), "RAG chatbot");
    await user.type(within(card).getByLabelText("What will you build or do today?"), "Something real");
    await user.click(within(card).getByRole("button", { name: "Plan today's challenge" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("That day already has a challenge");
  });

  it("offers suggestions built from the user's data and fills the form from one", async () => {
    const user = userEvent.setup();
    await open({
      suggestions: [
        { source: "project", mode: "existing_project", project_id: 2, title: "Agent playground", detail: "Next milestone · not worked on yet", planned_task: "Work towards the milestone 'Tools'" },
        { source: "roadmap", mode: "new_project", project_id: null, title: "Apply: Python", detail: "Foundations · roadmap topic", planned_task: "Build a small project that applies Python" },
      ],
    });
    const list = await screen.findByRole("list", { name: "Suggestions" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    await user.click(within(list).getByRole("button", { name: "Use idea: Agent playground" }));
    const card = await today();
    expect(within(card).getByLabelText("What will you build or do today?")).toHaveValue("Work towards the milestone 'Tools'");
    expect(await within(card).findByRole("combobox", { name: "Project" })).toHaveValue("2");
    await user.click(within(list).getByRole("button", { name: "Use idea: Apply: Python" }));
    expect(within(card).getByRole("radio", { name: /Start a new project/ })).toBeChecked();
  });

  it("starts a planned challenge", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ challenges: [mkChallenge({ id: 5 })] });
    const card = await today();
    await user.click(await within(card).findByRole("button", { name: "Start" }));
    await waitFor(() => expect(fake.callsTo("POST", /challenges\/5\/start$/)).toHaveLength(1));
    expect(await within(await today()).findByText("In progress")).toBeInTheDocument();
    expect(within(await today()).queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
  });

  it("will not send evidence that is incomplete", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ challenges: [mkChallenge({ id: 5 })] });
    await user.click(await screen.findByRole("button", { name: "Record evidence and complete" }));
    const dialog = await screen.findByRole("dialog", { name: "Record today's evidence" });
    expect(within(dialog).getByText(/Unverified/, { selector: "strong" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Complete the day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Describe what you implemented");
    await user.type(within(dialog).getByLabelText(/What did you implement/), "Built the retriever and tested top-k search on sample docs.");
    await user.click(within(dialog).getByRole("button", { name: "Complete the day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("GitHub repository");
    await user.type(within(dialog).getByLabelText("GitHub repository"), "https://github.com/me/rag");
    await user.click(within(dialog).getByRole("button", { name: "Complete the day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("commit hash");
    await user.type(within(dialog).getByLabelText(/^Commit hash/), "a1b2c3d");
    await user.click(within(dialog).getByRole("button", { name: "Complete the day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("commit message");
    await user.type(within(dialog).getByLabelText("Commit message"), "Add retrieval step");
    await user.click(within(dialog).getByRole("button", { name: "Complete the day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("whole number of minutes");
    expect(fake.callsTo("POST", /complete$/)).toHaveLength(0);
  });

  it("completes the day with evidence, then shows it as unverified and takes the actions away", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ challenges: [mkChallenge({ id: 5, estimated_minutes: 45, project: { id: 1, title: "RAG chatbot", repo_url: "https://github.com/me/rag" } })] });
    await user.click(await screen.findByRole("button", { name: "Record evidence and complete" }));
    const dialog = await screen.findByRole("dialog", { name: "Record today's evidence" });
    expect(within(dialog).getByLabelText("GitHub repository")).toHaveValue("https://github.com/me/rag");   // prefilled from the project
    expect(within(dialog).getByLabelText("Time spent (minutes)")).toHaveValue("45");                          // prefilled from the estimate
    await user.type(within(dialog).getByLabelText(/What did you implement/), "Built the retriever and tested top-k search on sample docs.");
    await user.type(within(dialog).getByLabelText(/^Commit hash/), "a1b2c3d4e5f6");
    await user.type(within(dialog).getByLabelText("Commit message"), "Add retrieval step to RAG pipeline");
    await user.click(within(dialog).getByRole("button", { name: "Complete the day" }));
    await waitFor(() =>
      expect(fake.callsTo("POST", /challenges\/5\/complete$/)[0].body).toEqual({
        summary: "Built the retriever and tested top-k search on sample docs.", repo_url: "https://github.com/me/rag", commit_sha: "a1b2c3d4e5f6",
        commit_message: "Add retrieval step to RAG pipeline", minutes: 45,
      }),
    );
    const card = await today();
    expect(await within(card).findByText("Completed")).toBeInTheDocument();
    expect(within(card).getByText("Unverified")).toBeInTheDocument();
    expect(within(card).getByText(/Built the retriever/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /View on GitHub/ })).toHaveAttribute("href", "https://github.com/me/rag/commit/a1b2c3d4e5f6");
    expect(within(card).queryByRole("button", { name: "Record evidence and complete" })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /Excuse today/ })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Remove plan" })).not.toBeInTheDocument();
    const stats = screen.getByRole("region", { name: "Challenge statistics" });
    await waitFor(() => expect(within(stats).getByText("Current streak").nextSibling).toHaveTextContent("1 day"));
    expect(await within(screen.getByRole("region", { name: "Evidence history" })).findByText("Unverified")).toBeInTheDocument();
  });

  it("shows the server's reason when evidence is rejected, and the day stays open", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ challenges: [mkChallenge({ id: 5 })] });
    await user.click(await screen.findByRole("button", { name: "Record evidence and complete" }));
    const dialog = await screen.findByRole("dialog");
    fake.failNext(/POST \/api\/challenges\/5\/complete$/, 422, "That commit message doesn't describe any work.");
    await user.type(within(dialog).getByLabelText(/What did you implement/), "Built the retriever and tested top-k search on sample docs.");
    await user.type(within(dialog).getByLabelText("GitHub repository"), "https://github.com/me/rag");
    await user.type(within(dialog).getByLabelText(/^Commit hash/), "a1b2c3d");
    await user.type(within(dialog).getByLabelText("Commit message"), "update");
    await user.type(within(dialog).getByLabelText("Time spent (minutes)"), "30");
    await user.click(within(dialog).getByRole("button", { name: "Complete the day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("doesn't describe any work");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(await today()).getByText("Planned")).toBeInTheDocument();
  });

  it("excuses today only with a reason", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ challenges: [mkChallenge({ id: 5 })] });
    await user.click(await screen.findByRole("button", { name: "Excuse today" }));
    const dialog = await screen.findByRole("dialog", { name: `Excuse ${TODAY()}` });
    await user.type(within(dialog).getByLabelText(/Why is this day being excused/), "no");
    await user.click(within(dialog).getByRole("button", { name: "Excuse this day" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("at least 5 characters");
    expect(fake.callsTo("POST", /excuse$/)).toHaveLength(0);
    await user.clear(within(dialog).getByLabelText(/Why is this day being excused/));
    await user.type(within(dialog).getByLabelText(/Why is this day being excused/), "Fever, stayed in bed");
    await user.click(within(dialog).getByRole("button", { name: "Excuse this day" }));
    await waitFor(() => expect(fake.callsTo("POST", /excuse$/)[0].body).toEqual({ date: TODAY(), reason: "Fever, stayed in bed" }));
    const card = await today();
    expect(await within(card).findByText("Excused: Fever, stayed in bed")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Record evidence and complete" })).not.toBeInTheDocument();
  });

  it("removes an excuse or a plan", async () => {
    const user = userEvent.setup();
    const { fake } = await open({ challenges: [mkChallenge({ id: 5, status: "excused", excuse_reason: "Fever", can_complete: false })] });
    await user.click(await screen.findByRole("button", { name: "Remove excuse" }));
    await waitFor(() => expect(fake.callsTo("DELETE", /challenges\/5$/)).toHaveLength(1));
    expect(await within(await today()).findByRole("button", { name: "Plan today's challenge" })).toBeInTheDocument();
  });

  it("shows the last 30 days with text labels, and lets a missed day be excused", async () => {
    const user = userEvent.setup();
    const done = mkChallenge({ id: 1, date: addDays(TODAY(), -3), status: "completed", can_complete: false, implemented_summary: "Wrote the loader and tested it.", commit_sha: "abcdef12345", commit_message: "Add loader", actual_minutes: 60 });
    const { fake } = await open({ challenges: [done, mkChallenge({ id: 2, date: addDays(TODAY(), -1), status: "missed", can_complete: false })] });
    const cal = await screen.findByRole("region", { name: "Last 30 days" });
    expect(within(cal).getByLabelText(`${addDays(TODAY(), -3)}: Completed (RAG chatbot)`)).toBeInTheDocument();
    const missed = within(cal).getByRole("button", { name: `${addDays(TODAY(), -1)}: Missed (RAG chatbot). Excuse this day` });
    expect(within(cal).getAllByRole("listitem").filter((li) => li.querySelector("button")).length).toBe(1);
    await user.click(missed);
    const dialog = await screen.findByRole("dialog", { name: `Excuse ${addDays(TODAY(), -1)}` });
    await user.type(within(dialog).getByLabelText(/Why is this day being excused/), "Travelling all day");
    await user.click(within(dialog).getByRole("button", { name: "Excuse this day" }));
    await waitFor(() => expect(fake.callsTo("POST", /excuse$/)[0].body).toEqual({ date: addDays(TODAY(), -1), reason: "Travelling all day" }));
    expect(await within(cal).findByLabelText(`${addDays(TODAY(), -1)}: Excused (RAG chatbot)`)).toBeInTheDocument();
  });

  it("lists completed days with their evidence in the history", async () => {
    await open({ challenges: [mkChallenge({ id: 1, date: addDays(TODAY(), -2), status: "completed", can_complete: false, implemented_summary: "Wrote the loader and tested it.", commit_sha: "abcdef12345", commit_message: "Add loader", actual_minutes: 75 })] });
    const history = await screen.findByRole("region", { name: "Evidence history" });
    expect(within(history).getByText("Wrote the loader and tested it.")).toBeInTheDocument();
    expect(within(history).getByText(/abcdef1234 · Add loader · 1h 15m/)).toBeInTheDocument();
    expect(within(history).getByText("Unverified")).toBeInTheDocument();
  });

  it("shows an error with a retry when the server fails", async () => {
    const fake = installFakeApi();
    installFakeProjects(fake);
    installFakeChallenges(fake);
    fake.failNext(/GET \/api\/challenges\/today$/, 500, "Database is unavailable");
    renderAt("/challenge");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is unavailable");
    await userEvent.setup().click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("button", { name: "Plan today's challenge" })).toBeInTheDocument();
  });
});
