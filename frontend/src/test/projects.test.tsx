import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { addDays, todayIn } from "../lib/dates";
import { installFakeApi, mkTask, USER } from "./fakeApi";
import { installFakeAssistant } from "./fakeAssistant";
import { installFakeProjects, mkProject, type FakeProjects } from "./fakeProjects";
import { renderAt } from "./render";

const TODAY = () => todayIn(USER.timezone);

async function open(path: string, seed: Partial<FakeProjects> = {}, tasks: ReturnType<typeof mkTask>[] = []) {
  const fake = installFakeApi({ tasks });
  const store = installFakeProjects(fake, seed);
  renderAt(path);
  return { fake, store };
}

/** One project with 2 milestones (1 done) and 2 tasks (1 completed): 2 of 4 = 50%. */
function rag(): { seed: Partial<FakeProjects>; tasks: ReturnType<typeof mkTask>[] } {
  const done = mkTask({ id: 901, title: "Write loader", status: "completed", completed_at: "2026-11-20T10:00:00Z" });
  const open_ = mkTask({ id: 902, title: "Add reranker" });
  return {
    tasks: [done, open_],
    seed: {
      projects: [mkProject({ id: 1, title: "RAG chatbot", tech_stack: ["Python", "FastAPI"], repo_url: "https://github.com/me/rag", objective: "learn retrieval", start_date: "2026-11-01", target_date: addDays(TODAY(), 30) })],
      milestones: [
        { id: 11, project_id: 1, title: "Ingest docs", description: null, status: "done", position: 1, due_date: null, completed_at: "2026-11-10T10:00:00Z", evidence: "commit abc123", overdue: false },
        { id: 12, project_id: 1, title: "Build API", description: null, status: "pending", position: 2, due_date: null, completed_at: null, evidence: null, overdue: false },
      ],
      taskIds: { 1: [901, 902] },
      sessions: [{ id: 21, project_id: 1, date: "2026-11-20", minutes: 90, summary: "built the loader", milestone_id: 11, task_id: null, notes: null, created_at: "2026-11-20T10:00:00Z" }],
    },
  };
}

// ================================ list ================================

describe("projects list", () => {
  it("shows an honest empty state and invents nothing", async () => {
    const { store } = await open("/projects");
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(store.projects).toHaveLength(0);
  });

  it("shows each project's progress, counts, technologies, time and a safe GitHub link", async () => {
    const { seed, tasks } = rag();
    await open("/projects", seed, tasks);
    const card = (await screen.findByRole("heading", { name: "RAG chatbot", level: 3 })).closest("li")!;
    expect(within(card).getByRole("progressbar", { name: "RAG chatbot progress" })).toHaveAttribute("aria-valuenow", "50");
    expect(within(card).getByText(/1\/2 milestones · 1\/2 tasks/)).toBeInTheDocument();
    expect(within(card).getAllByRole("listitem").map((x) => x.textContent)).toEqual(["Python", "FastAPI"]);
    expect(within(card).getByText(/1h 30m over 1 day/)).toBeInTheDocument();
    const link = within(card).getByRole("link", { name: "GitHub repository of RAG chatbot" });
    expect(link).toHaveAttribute("href", "https://github.com/me/rag");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
    expect(within(card).getByText("Active")).toBeInTheDocument();
  });

  it("flags existing projects and projects past their target date", async () => {
    await open("/projects", { projects: [mkProject({ id: 1, title: "Old API", origin: "existing", target_date: addDays(TODAY(), -3) })] });
    const card = (await screen.findByRole("heading", { name: "Old API", level: 3 })).closest("li")!;
    expect(within(card).getByText("Existing")).toBeInTheDocument();
    expect(within(card).getByText("Past target date")).toBeInTheDocument();
  });

  it("filters by status on the server", async () => {
    const { fake } = await open("/projects", { projects: [mkProject({ id: 1, title: "A" }), mkProject({ id: 2, title: "B", status: "paused" })] });
    await screen.findByRole("heading", { name: "A", level: 3 });
    await userEvent.click(screen.getByRole("tab", { name: "Paused" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "A", level: 3 })).not.toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "B", level: 3 })).toBeInTheDocument();
    expect(fake.callsTo("GET", /\/api\/projects$/).some((c) => c.query.status === "paused")).toBe(true);
    await userEvent.click(screen.getByRole("tab", { name: "Archived" }));
    expect(await screen.findByText("No projects with this status")).toBeInTheDocument();
  });

  it("shows the server error and retries", async () => {
    const fake = installFakeApi();
    installFakeProjects(fake, { projects: [mkProject({ id: 1, title: "A" })] });
    fake.failNext(/^GET \/api\/projects$/, 500, "Database is down");
    renderAt("/projects");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "A", level: 3 })).toBeInTheDocument();
  });
});

// ================================ create / edit ================================

describe("creating a project", () => {
  async function openForm() {
    const s = await open("/projects");
    await userEvent.click((await screen.findAllByRole("button", { name: "New project" }))[0]);
    return { ...s, dialog: await screen.findByRole("dialog", { name: "New project" }) };
  }

  it("fills only the empty fields from a GitHub repo, keeps what you typed, and saves nothing yet", async () => {
    const { fake, dialog } = await openForm();
    await userEvent.type(within(dialog).getByLabelText("Description"), "My own words");
    await userEvent.type(within(dialog).getByLabelText("GitHub repository"), "https://github.com/me/rag-bot");
    await userEvent.click(within(dialog).getByRole("button", { name: "Fill from GitHub" }));
    await waitFor(() => expect(within(dialog).getByLabelText("Project name")).toHaveValue("rag-bot"));
    expect(within(dialog).getByLabelText("Description")).toHaveValue("My own words");
    expect(within(dialog).getByLabelText(/Technology stack/)).toHaveValue("Python, TypeScript");
    expect(fake.callsTo("POST", /\/projects$/)).toHaveLength(0);
  });

  it("shows GitHub's problem and asks for a link first when none is entered", async () => {
    const { dialog } = await openForm();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fill from GitHub" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Enter a GitHub link");
    await userEvent.type(within(dialog).getByLabelText("GitHub repository"), "https://github.com/me/missing");
    await userEvent.click(within(dialog).getByRole("button", { name: "Fill from GitHub" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("GitHub has no repository");
  });

  const CONNECTED = { provider: "anthropic", connected: true, model: "claude-opus-5-5", live_verified: false, message: "configured" };

  it("hides Suggest with AI when AI is off", async () => {
    const { dialog } = await openForm();
    expect(within(dialog).queryByRole("button", { name: "Suggest with AI" })).not.toBeInTheDocument();
  });

  it("suggests details with AI, fills only empty fields, and creates the kept milestones with the project", async () => {
    const fake = installFakeApi();
    installFakeAssistant(fake, { status: CONNECTED });
    installFakeProjects(fake, { projects: [] });
    renderAt("/projects");
    await userEvent.click((await screen.findAllByRole("button", { name: "New project" }))[0]);
    const dialog = await screen.findByRole("dialog", { name: "New project" });
    await userEvent.type(within(dialog).getByLabelText("Description"), "My own words");
    await userEvent.type(within(dialog).getByLabelText("GitHub repository"), "https://github.com/me/rag-bot");
    await userEvent.click(await within(dialog).findByRole("button", { name: "Suggest with AI" }));
    await waitFor(() => expect(within(dialog).getByLabelText("Project name")).toHaveValue("RAG Bot"));
    expect(within(dialog).getByLabelText("Description")).toHaveValue("My own words");          // typed text is never overwritten
    expect(within(dialog).getByLabelText("Objective", { exact: false })).toHaveValue("Learn retrieval.");
    expect(within(dialog).getByText(/It can be wrong/)).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/projects$/)).toHaveLength(0);                                // nothing saved yet
    await userEvent.click(within(dialog).getByLabelText("Keep milestone: Build the index"));      // drop one idea
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(fake.callsTo("POST", /\/projects$/)).toHaveLength(1));
    await waitFor(() => expect(fake.callsTo("POST", /milestones$/).map((c) => c.body)).toEqual([{ title: "Load documents" }]));
  });

  it("shows the AI's problem and asks for a source first", async () => {
    const fake = installFakeApi();
    installFakeAssistant(fake, { status: CONNECTED, autofillError: "The AI didn't return a usable suggestion. Try again" });
    installFakeProjects(fake, { projects: [] });
    renderAt("/projects");
    await userEvent.click((await screen.findAllByRole("button", { name: "New project" }))[0]);
    const dialog = await screen.findByRole("dialog", { name: "New project" });
    await userEvent.click(await within(dialog).findByRole("button", { name: "Suggest with AI" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Enter a GitHub link or a short description first");
    await userEvent.type(within(dialog).getByLabelText("Description"), "A chatbot");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suggest with AI" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("usable suggestion");
  });

  it("validates name, repository link and dates before sending anything", async () => {
    const { fake, dialog } = await openForm();
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Please give the project a name.");
    await userEvent.type(within(dialog).getByLabelText("Project name"), "X");
    await userEvent.type(within(dialog).getByLabelText("GitHub repository"), "https://gitlab.com/o/r");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("GitHub link like https://github.com/owner/repository");
    await userEvent.clear(within(dialog).getByLabelText("GitHub repository"));
    await userEvent.type(within(dialog).getByLabelText(/^Start date/), "2026-05-02");
    await userEvent.type(within(dialog).getByLabelText("Target completion date"), "2026-05-01");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("target date can't be before the start date");
    expect(fake.callsTo("POST", /\/api\/projects$/)).toHaveLength(0);
  });

  it("creates a new project and opens it", async () => {
    const { fake, dialog } = await openForm();
    await userEvent.type(within(dialog).getByLabelText("Project name"), "Agent playground");
    await userEvent.type(within(dialog).getByLabelText(/^Technology stack/), "Python, LangGraph, ,python");
    await userEvent.type(within(dialog).getByLabelText("GitHub repository"), "https://github.com/me/agents");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("heading", { name: "Agent playground", level: 1 })).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/projects$/)[0].body).toMatchObject({
      title: "Agent playground", origin: "new", tech_stack: ["Python", "LangGraph", "python"], repo_url: "https://github.com/me/agents", status: "active", priority: 2,
    });
    expect(screen.getByLabelText("Technologies")).toBeInTheDocument();
  });

  it("brings in an existing project without inventing a start date", async () => {
    const { fake, dialog } = await openForm();
    await userEvent.type(within(dialog).getByLabelText("Project name"), "Legacy tool");
    await userEvent.selectOptions(within(dialog).getByLabelText("Is it new?"), "existing");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("heading", { name: "Legacy tool", level: 1 })).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/projects$/)[0].body).toMatchObject({ origin: "existing", start_date: null });
    expect(screen.getByText("Existing")).toBeInTheDocument();
    expect(screen.queryByText(/^Started/)).not.toBeInTheDocument();
  });

  it("shows the server's message for a duplicate name", async () => {
    const fake = installFakeApi();
    installFakeProjects(fake, { projects: [mkProject({ id: 1, title: "RAG chatbot" })] });
    renderAt("/projects");
    await userEvent.click((await screen.findAllByRole("button", { name: "New project" }))[0]);
    const dialog = await screen.findByRole("dialog", { name: "New project" });
    await userEvent.type(within(dialog).getByLabelText("Project name"), "rag chatbot");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already have a project with that name");
  });
});

// ================================ detail ================================

describe("project detail", () => {
  async function detail() {
    const { seed, tasks } = rag();
    const s = await open("/projects/1", seed, tasks);
    await screen.findByRole("heading", { name: "RAG chatbot", level: 1 });
    return s;
  }

  it("shows the overview with numbers computed from the records", async () => {
    await detail();
    const overview = screen.getByRole("region", { name: "Project overview" });
    expect(within(overview).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    expect(within(overview).getByText(/50% · 2 of 4 milestones and tasks done/)).toBeInTheDocument();
    expect(within(overview).getByText("Milestones").nextSibling).toHaveTextContent("1/2");
    expect(within(overview).getByText("Tasks").nextSibling).toHaveTextContent("1/2");
    expect(within(overview).getByText("Time spent").nextSibling).toHaveTextContent("1h 30m");
    expect(within(overview).getByText("Days worked").nextSibling).toHaveTextContent("1");
    expect(within(overview).getByText(/Objective: learn retrieval/)).toBeInTheDocument();
    expect(within(overview).getByRole("link", { name: "GitHub repository" })).toHaveAttribute("href", "https://github.com/me/rag");
  });

  it("says so for a project that doesn't exist", async () => {
    await open("/projects/999");
    expect(await screen.findByText("Project not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to projects/ })).toHaveAttribute("href", "/projects");
  });

  it("marking a milestone done (with evidence) updates progress but does not complete the project", async () => {
    const { fake } = await detail();
    await userEvent.click(screen.getByRole("button", { name: "Mark milestone Build API done" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark done: Build API" });
    await userEvent.type(within(dialog).getByLabelText(/Evidence/), "commit def456");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark done" }));
    await waitFor(() => expect(screen.getByText(/75% · 3 of 4/)).toBeInTheDocument());
    expect(fake.callsTo("POST", /project-milestones\/12\/status$/)[0].body).toEqual({ status: "done", evidence: "commit def456" });
    expect(screen.getByRole("button", { name: "Reopen milestone Build API" })).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();                       // still active: completing is the owner's call
    expect(screen.getByRole("button", { name: "Mark project completed" })).toBeInTheDocument();
  });

  it("reopens a milestone and lowers progress", async () => {
    await detail();
    await userEvent.click(screen.getByRole("button", { name: "Reopen milestone Ingest docs" }));
    await waitFor(() => expect(screen.getByText(/25% · 1 of 4/)).toBeInTheDocument());
  });

  it("adds a milestone (rejecting duplicates) and deletes one after confirmation", async () => {
    const { fake } = await detail();
    const card = screen.getByRole("region", { name: "Milestones" });
    await userEvent.type(within(card).getByLabelText("New milestone"), "build api");
    await userEvent.click(within(card).getByRole("button", { name: "Add milestone" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("already has a milestone with that name");
    await userEvent.clear(within(card).getByLabelText("New milestone"));
    await userEvent.type(within(card).getByLabelText("New milestone"), "Deploy");
    await userEvent.click(within(card).getByRole("button", { name: "Add milestone" }));
    expect(await within(card).findByText("Deploy")).toBeInTheDocument();
    expect(fake.callsTo("POST", /projects\/1\/milestones$/).at(-1)!.body).toEqual({ title: "Deploy", due_date: null });
    expect(screen.getByText(/40% · 2 of 5/)).toBeInTheDocument();                 // the new milestone is part of the total

    await userEvent.click(within(card).getByRole("button", { name: "Delete milestone Deploy" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Delete milestone?" })).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /project-milestones/)).toHaveLength(0);
    await userEvent.click(within(card).getByRole("button", { name: "Delete milestone Deploy" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(within(card).queryByText("Deploy")).not.toBeInTheDocument());
  });

  it("completing a project task changes progress through the normal task status", async () => {
    const { fake } = await detail();
    const card = screen.getByRole("region", { name: "Project tasks" });
    await userEvent.click(within(card).getByRole("checkbox", { name: "Complete task Add reranker" }));
    await waitFor(() => expect(screen.getByText(/75% · 3 of 4/)).toBeInTheDocument());
    expect(fake.callsTo("PATCH", /\/api\/tasks\/902$/)[0].body).toEqual({ status: "completed" });
    await userEvent.click(within(card).getByRole("checkbox", { name: "Reopen task Add reranker" }));
    await waitFor(() => expect(screen.getByText(/50% · 2 of 4/)).toBeInTheDocument());
  });

  it("adds a task to the project", async () => {
    const { fake } = await detail();
    const card = screen.getByRole("region", { name: "Project tasks" });
    await userEvent.type(within(card).getByLabelText("New task"), "Write tests");
    await userEvent.click(within(card).getByRole("button", { name: "Add task" }));
    expect(await within(card).findByText("Write tests")).toBeInTheDocument();
    expect(fake.callsTo("POST", /projects\/1\/tasks$/)[0].body).toEqual({ title: "Write tests" });
    expect(screen.getByText(/40% · 2 of 5/)).toBeInTheDocument();
  });

  it("cancelled tasks are shown but not counted", async () => {
    const { seed, tasks } = rag();
    tasks[1] = { ...tasks[1], status: "cancelled" };
    await open("/projects/1", seed, tasks);
    expect(await screen.findByText(/66% · 2 of 3/)).toBeInTheDocument();
    expect(screen.getByText(/cancelled \(not counted\)/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Complete task Add reranker" })).toBeDisabled();
  });

  it("logs a development session (validated), updates the totals, and deletes one", async () => {
    const { fake } = await detail();
    const card = screen.getByRole("region", { name: "Development sessions" });
    await userEvent.click(within(card).getByRole("button", { name: "Log session" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Say what you worked on");
    await userEvent.type(within(card).getByLabelText("What did you work on?"), "wired up the retriever");
    await userEvent.clear(within(card).getByLabelText("Minutes"));
    await userEvent.type(within(card).getByLabelText("Minutes"), "0");
    await userEvent.click(within(card).getByRole("button", { name: "Log session" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("1 to 1440");
    expect(fake.callsTo("POST", /sessions$/)).toHaveLength(0);

    await userEvent.clear(within(card).getByLabelText("Minutes"));
    await userEvent.type(within(card).getByLabelText("Minutes"), "45");
    await userEvent.selectOptions(within(card).getByLabelText("Milestone (optional)"), "Build API");
    await userEvent.click(within(card).getByRole("button", { name: "Log session" }));
    expect(await within(card).findByText(/wired up the retriever/)).toBeInTheDocument();
    expect(fake.callsTo("POST", /projects\/1\/sessions$/)[0].body).toEqual({ minutes: 45, summary: "wired up the retriever", date: TODAY(), milestone_id: 12 });
    const overview = screen.getByRole("region", { name: "Project overview" });
    await waitFor(() => expect(within(overview).getByText("Time spent").nextSibling).toHaveTextContent("2h 15m"));
    expect(within(overview).getByText("Days worked").nextSibling).toHaveTextContent("2");

    await userEvent.click(within(card).getByRole("button", { name: /Delete session of .*: wired up the retriever/ }));
    await waitFor(() => expect(within(overview).getByText("Time spent").nextSibling).toHaveTextContent("1h 30m"));
  });

  it("shows the server's rejection of a session", async () => {
    const { fake } = await detail();
    fake.failNext(/^POST \/api\/projects\/1\/sessions$/, 422, "That milestone doesn't belong to this project");
    const card = screen.getByRole("region", { name: "Development sessions" });
    await userEvent.type(within(card).getByLabelText("What did you work on?"), "something real");
    await userEvent.click(within(card).getByRole("button", { name: "Log session" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("doesn't belong to this project");
  });

  it("saves notes", async () => {
    const { fake } = await detail();
    const card = screen.getByRole("region", { name: "Project notes" });
    expect(within(card).getByRole("button", { name: "Save notes" })).toBeDisabled();
    await userEvent.type(within(card).getByLabelText("Notes"), "try hybrid search");
    await userEvent.click(within(card).getByRole("button", { name: "Save notes" }));
    await waitFor(() => expect(fake.callsTo("PATCH", /projects\/1$/)[0].body).toEqual({ notes: "try hybrid search" }));
  });

  it("edits the project and shows the change", async () => {
    const { fake } = await detail();
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit project" });
    expect(within(dialog).getByLabelText("Project name")).toHaveValue("RAG chatbot");
    expect(within(dialog).getByLabelText(/^Technology stack/)).toHaveValue("Python, FastAPI");
    await userEvent.clear(within(dialog).getByLabelText("Project name"));
    await userEvent.type(within(dialog).getByLabelText("Project name"), "RAG chatbot v2");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "RAG chatbot v2", level: 1 })).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /projects\/1$/)[0].body).toMatchObject({ title: "RAG chatbot v2", tech_stack: ["Python", "FastAPI"] });
  });

  it("completes and reopens the project only through the explicit button", async () => {
    const { fake } = await detail();
    await userEvent.click(screen.getByRole("button", { name: "Mark project completed" }));
    expect(await screen.findByRole("button", { name: "Reopen project" })).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /projects\/1$/)[0].body).toEqual({ status: "completed" });
    expect(screen.getByText("Completed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reopen project" }));
    expect(await screen.findByRole("button", { name: "Mark project completed" })).toBeInTheDocument();
  });

  it("deletes the project only after confirmation, saying what goes and what stays", async () => {
    const { fake } = await detail();
    await userEvent.click(screen.getByRole("button", { name: "Delete project RAG chatbot" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete project?" });
    expect(dialog).toHaveTextContent("2 milestones and 1 development session");
    expect(dialog).toHaveTextContent("Its tasks stay in your task list");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /projects\/1$/)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Delete project RAG chatbot" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(fake.callsTo("DELETE", /projects\/1$/)).toHaveLength(1);
  });
});

describe("navigation", () => {
  it("the sidebar link is live (no Soon badge)", async () => {
    await open("/projects");
    const link = within(await screen.findByRole("navigation", { name: "Main" })).getByRole("link", { name: /Projects/ });
    expect(within(link).queryByText("Soon")).not.toBeInTheDocument();
  });
});
