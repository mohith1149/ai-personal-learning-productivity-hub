import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Dashboard } from "../api/dashboard";
import { installFakeApi } from "./fakeApi";
import { mkChallenge } from "./fakeChallenges";
import { emptyDashboard, installFakeDashboard } from "./fakeDashboard";
import { mkItem } from "./fakePlanner";
import { renderAt } from "./render";

async function open(data: Partial<Dashboard> | null) {
  const fake = installFakeApi();
  if (data) installFakeDashboard(fake, { is_empty: false, ...data });
  renderAt("/");
  await screen.findByRole("heading", { level: 1, name: /Good (morning|afternoon|evening), Ada Lovelace/ });
  return fake;
}

const panel = (name: string) => screen.findByRole("region", { name });
const SOME = { tasks: { overdue: 0, today: 1, completed_today: 0 } };

function busy(): Partial<Dashboard> {
  const base = emptyDashboard();
  return {
    plan: {
      summary: { total: 5, completed: 2, pending: 2, overdue: 1, excused: 0, percent: 40, study_minutes: 30, dev_minutes: 90, by_kind: [] },
      next_items: [mkItem({ kind: "task", ref_id: 1, title: "File taxes", status: "overdue", link: "/tasks" }), mkItem({ kind: "video", ref_id: 2, title: "How DNS works", link: "/videos" })],
      open_count: 3,
    },
    videos: [{ playlist_id: 1, name: "BYTEBYTEGO", daily_target: 5, watched_today: 2, remaining_today: 3, target_met: false, up_next: ["Big-O notation", "SQL vs NoSQL", "REST vs GraphQL"] }],
    challenge: { today: mkChallenge({ status: "completed", planned_task: "Add retrieval" }), stats: { ...base.challenge.stats, current_streak: 4, longest_streak: 9, missed: 2 } },
    habits: { active: 2, due_today: 1, best_streak: 6, best_streak_name: "Reading", best_streak_unit: "days" },
    tasks: { overdue: 1, today: 3, completed_today: 2 },
    projects: [{ id: 7, title: "RAG chatbot", percent: 66, minutes_spent: 150, last_activity_at: null }],
    courses: [{ id: 3, title: "Agentic AI", percent: 25, next_lesson: "What is an agent?" }],
    roadmap: { total: 51, completed: 4, in_progress: 1, percent: 7, next_topic: "Python" },
    week: base.week.map((w, i) => (i === 6 ? { ...w, study_minutes: 30, dev_minutes: 90 } : w)),
  };
}

describe("dashboard", () => {
  it("for a new account shows an honest empty state with links to start, and no figures", async () => {
    await open(null);
    expect(await screen.findByText("Nothing to show yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "task" })).toHaveAttribute("href", "/tasks");
    expect(screen.getByRole("link", { name: "challenge" })).toHaveAttribute("href", "/challenge");
    expect(document.getElementById("main")!.textContent).not.toMatch(/\d/);
    expect(screen.queryByRole("region", { name: "Today's plan" })).not.toBeInTheDocument();
  });

  it("shows today's progress and the next open items, overdue marked", async () => {
    await open(busy());
    const p = await panel("Today's plan");
    expect(within(p).getByText("2/5")).toBeInTheDocument();
    expect(within(p).getByText(/1 overdue/)).toBeInTheDocument();
    expect(within(p).getByRole("progressbar", { name: "Today's progress" })).toHaveAttribute("aria-valuenow", "40");
    const list = within(p).getByRole("list", { name: "Up next" });
    expect(within(list).getAllByRole("listitem").map((li) => li.querySelector("a")?.textContent)).toEqual(["File taxes", "How DNS works"]);
    expect(within(list).getByRole("link", { name: "File taxes" })).toHaveAttribute("href", "/tasks");
    expect(within(p).getByText("and 1 more on the planner.")).toBeInTheDocument();
    expect(within(p).getByRole("link", { name: "Open planner" })).toHaveAttribute("href", "/planner");
  });

  it("says nothing is planned when the day is empty, rather than showing 0%", async () => {
    await open({ habits: { active: 1, due_today: 0, best_streak: 0, best_streak_name: null, best_streak_unit: null } });
    const p = await panel("Today's plan");
    expect(within(p).getByText("Nothing is planned for today.")).toBeInTheDocument();
    expect(within(p).queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("lists the videos to watch today with the daily target", async () => {
    await open(busy());
    const p = await panel("Videos to watch today");
    expect(within(p).getByText("BYTEBYTEGO: watched 2 of 5")).toBeInTheDocument();
    expect(within(p).getAllByRole("listitem").map((li) => li.textContent)).toEqual(expect.arrayContaining(["Big-O notation", "SQL vs NoSQL", "REST vs GraphQL"]));
    expect(within(p).queryByText("target met")).not.toBeInTheDocument();
  });

  it("marks a met video target", async () => {
    await open({ ...SOME, videos: [{ playlist_id: 1, name: "BYTEBYTEGO", daily_target: 5, watched_today: 5, remaining_today: 0, target_met: true, up_next: [] }] });
    expect(within(await panel("Videos to watch today")).getByText("target met")).toBeInTheDocument();
  });

  it("explains the missing video target instead of showing an empty box", async () => {
    await open(SOME);
    expect(within(await panel("Videos to watch today")).getByText(/No collection has a daily target/)).toBeInTheDocument();
  });

  it("shows the challenge status and streaks", async () => {
    await open(busy());
    const c = await panel("Daily challenge");
    expect(within(c).getByText("Completed")).toBeInTheDocument();
    expect(within(c).getByText("Current streak").nextSibling).toHaveTextContent("4 days");
    expect(within(c).getByText("Longest streak").nextSibling).toHaveTextContent("9 days");
    expect(within(c).getByText("Missed days").nextSibling).toHaveTextContent("2");
  });

  it("says the challenge isn't planned yet", async () => {
    await open(SOME);
    const c = await panel("Daily challenge");
    expect(within(c).getByText("Today's challenge isn't planned yet.")).toBeInTheDocument();
    expect(within(c).getByRole("link", { name: "Open challenge" })).toHaveAttribute("href", "/challenge");
  });

  it("shows habits, tasks, roadmap, projects and courses from the server's numbers", async () => {
    await open(busy());
    const h = await panel("Habits");
    expect(within(h).getByText("Due today").nextSibling).toHaveTextContent("1");
    expect(within(h).getByText("Best current streak").nextSibling).toHaveTextContent("6 days");
    expect(within(h).getByText("Reading")).toBeInTheDocument();
    const t = await panel("Tasks");
    expect([...t.querySelectorAll("dd")].map((d) => d.textContent)).toEqual(["1", "3", "2"]);
    const r = await panel("AI roadmap");
    expect(within(r).getByText("4 of 51 topics completed, 1 in progress")).toBeInTheDocument();
    expect(within(r).getByText("Next topic: Python")).toBeInTheDocument();
    expect(within(r).getByRole("progressbar", { name: "Roadmap progress" })).toHaveAttribute("aria-valuenow", "7");
    const pr = await panel("Active projects");
    expect(within(pr).getByRole("link", { name: "RAG chatbot" })).toHaveAttribute("href", "/projects/7");
    expect(within(pr).getByRole("progressbar", { name: "RAG chatbot progress" })).toHaveAttribute("aria-valuenow", "66");
    expect(within(pr).getByText("2h 30m spent")).toBeInTheDocument();
    const co = await panel("Active courses");
    expect(within(co).getByRole("link", { name: "Agentic AI" })).toHaveAttribute("href", "/courses/3");
    expect(within(co).getByText("Next: What is an agent?")).toBeInTheDocument();
  });

  it("shows plain empty messages for sections with nothing in them", async () => {
    await open(SOME);
    expect(within(await panel("Habits")).getByText("No active habits.")).toBeInTheDocument();
    expect(within(await panel("Active projects")).getByText("No active projects.")).toBeInTheDocument();
    expect(within(await panel("Active courses")).getByText("No active courses.")).toBeInTheDocument();
    expect(within(await panel("Last 7 days")).getByText(/No study or project time logged/)).toBeInTheDocument();
  });

  it("shows the last 7 days of study and project time", async () => {
    await open(busy());
    const w = await panel("Last 7 days");
    expect(within(w).getAllByRole("listitem")).toHaveLength(7);
    expect(within(w).getByText("Today")).toBeInTheDocument();
    expect(within(w).getByText("Yesterday")).toBeInTheDocument();
    expect(within(w).getByText("30m study · 1h 30m projects")).toBeInTheDocument();
  });

  it("links through to the feature pages", async () => {
    const user = userEvent.setup();
    await open(busy());
    await user.click(within(await panel("Tasks")).getByRole("link", { name: "Open tasks" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Tasks" })).toBeInTheDocument();
  });

  it("shows an error with retry when the server fails", async () => {
    const fake = installFakeApi();
    fake.failNext(/GET \/api\/dashboard$/, 500, "Database is unavailable");
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is unavailable");
    await userEvent.setup().click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Nothing to show yet")).toBeInTheDocument();
  });
});
