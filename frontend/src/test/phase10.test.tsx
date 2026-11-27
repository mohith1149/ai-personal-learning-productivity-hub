import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { setModelChoice } from "../api/assistant";
import type { Goal } from "../api/goals";
import { clock } from "../components/Timer";
import { addDays, todayIn } from "../lib/dates";
import { installFakeApi, USER, type Fake } from "./fakeApi";
import { installFakePlanner, mkItem, type FakePlanner } from "./fakePlanner";
import { renderAt } from "./render";

const TODAY = () => todayIn(USER.timezone);

beforeEach(() => {
  setModelChoice(null);
});

async function open(days: FakePlanner["days"] = {}, setup?: (fake: Fake) => void) {
  const fake = installFakeApi();
  installFakePlanner(fake, { days });
  setup?.(fake);
  renderAt("/planner");
  await screen.findByRole("heading", { name: "Daily planner", level: 1 });
  return { fake };
}

const items = (): FakePlanner["days"] => ({
  [TODAY()]: [
    mkItem({ kind: "task", ref_id: 1, title: "Write report", status: "pending" }),
    mkItem({ kind: "project", ref_id: 7, title: "RAG bot", status: "pending" }),
    mkItem({ kind: "habit", ref_id: 3, title: "Stretch", status: "pending" }),
  ],
});

const goal = (o: Partial<Goal> = {}): Goal => ({
  kind: "course", id: 1, title: "RAG course", target_date: addDays(TODAY(), 20), status: "on_track", warning: false,
  message: "On track: at your pace of 1 lessons a day you'd finish around 5 Dec (target 10 Dec).", unit: "lessons", total: 24, done: 14, remaining: 10,
  days_left: 21, needed_per_day: 0.48, recent_per_day: 1, projected_date: addDays(TODAY(), 10), ...o,
});

describe("clock", () => {
  it("formats seconds as M:SS and H:MM:SS", () => {
    expect(clock(0)).toBe("0:00");
    expect(clock(65)).toBe("1:05");
    expect(clock(3600 + 61)).toBe("1:01:01");
    expect(clock(-5)).toBe("0:00");
  });
});

describe("goals and pace on the planner", () => {
  it("shows goals worst first, with the server's wording and a link to the item", async () => {
    await open(items(), (f) =>
      (f.planning.goals = [
        goal({ id: 2, title: "Deep learning", status: "behind", warning: true, message: "At your pace of 3.5 lessons a week you'd finish on 2 Jan, 31 days after 2 Dec. You need about 2 lessons a day." }),
        goal(),
      ]),
    );
    const card = await screen.findByRole("region", { name: "Goals and pace" });
    expect(within(card).getByText("1 need attention")).toBeInTheDocument();
    const rows = within(card).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Deep learning");
    expect(rows[0]).toHaveTextContent("Behind pace");
    expect(rows[0]).toHaveTextContent("31 days after 2 Dec");
    expect(rows[1]).toHaveTextContent("On track");
    expect(within(card).getByRole("link", { name: "Deep learning" })).toHaveAttribute("href", "/courses/2");
  });

  it("is hidden when no goal has a target date, and leaves finished goals out", async () => {
    await open(items(), (f) => (f.planning.goals = [goal({ status: "done", message: "All lessons are done." })]));
    await screen.findByText("Write report");
    expect(screen.queryByRole("region", { name: "Goals and pace" })).not.toBeInTheDocument();
  });

  it("is only shown on today's plan", async () => {
    await open(items(), (f) => (f.planning.goals = [goal()]));
    await screen.findByRole("region", { name: "Goals and pace" });
    await userEvent.click(screen.getByRole("button", { name: "Next day" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Goals and pace" })).not.toBeInTheDocument());
  });
});

describe("the timer", () => {
  it("starts on a task, shows a running bar everywhere, and disables the other timer buttons", async () => {
    const { fake } = await open(items());
    expect(screen.queryByRole("region", { name: "Running timer" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Start timer for Write report" }));
    const bar = await screen.findByRole("region", { name: "Running timer" });
    expect(bar).toHaveTextContent("Timed task 1");
    expect(fake.planning.timer?.task_id).toBe(1);
    await waitFor(() => expect(screen.getByRole("button", { name: "Start timer for RAG bot" })).toBeDisabled());
    expect(screen.getByRole("button", { name: "Start timer for RAG bot" })).toHaveAttribute("title", expect.stringContaining("already running"));
  });

  it("offers a timer on tasks and projects but not on habits", async () => {
    await open(items());
    await screen.findByRole("button", { name: "Start timer for RAG bot" });
    expect(screen.queryByRole("button", { name: "Start timer for Stretch" })).not.toBeInTheDocument();
  });

  it("is already running after a reload (it lives on the server) and counts up", async () => {
    await open(items(), (f) => {
      f.planning.timer = {
        kind: "task", label: "Write report", started_at: new Date().toISOString(), elapsed_seconds: 125, logs_to: null,
        task_id: 1, lesson_id: null, topic_id: null, course_id: null, project_id: null,
      };
    });
    const bar = await screen.findByRole("region", { name: "Running timer" });
    expect(within(bar).getByLabelText("Elapsed time")).toHaveTextContent(/^2:0[5-9]$/);
  });

  it("stops and logs, letting you correct the minutes", async () => {
    const { fake } = await open(items(), (f) => {
      f.planning.timer = {
        kind: "task", label: "Write report", started_at: new Date().toISOString(), elapsed_seconds: 47 * 60, logs_to: null,
        task_id: 1, lesson_id: null, topic_id: null, course_id: null, project_id: null,
      };
    });
    await userEvent.click(await screen.findByRole("button", { name: "Stop and log" }));
    const dialog = await screen.findByRole("dialog");
    const minutes = within(dialog).getByLabelText("Minutes to log");
    expect(minutes).toHaveValue(47);
    expect(within(dialog).queryByLabelText(/What did you do/)).not.toBeInTheDocument(); // only projects ask for a summary
    await userEvent.clear(minutes);
    await userEvent.type(minutes, "30");
    await userEvent.click(within(dialog).getByRole("button", { name: "Stop and log" }));
    expect(await within(dialog).findByRole("status")).toHaveTextContent("Logged 30 min on Write report");
    expect(fake.planning.stopped[0].minutes).toBe(30);
    await userEvent.click(within(dialog).getByText("Close", { selector: "button:not([aria-label])" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Running timer" })).not.toBeInTheDocument());
  });

  it("asks what you did when the time goes to a project, and sends it", async () => {
    const { fake } = await open(items(), (f) => {
      f.planning.timer = {
        kind: "project", label: "RAG bot", started_at: new Date().toISOString(), elapsed_seconds: 600, logs_to: "Project: RAG bot",
        task_id: null, lesson_id: null, topic_id: null, course_id: null, project_id: 7,
      };
    });
    await userEvent.click(await screen.findByRole("button", { name: "Stop and log" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/What did you do/), "Built the chunker");
    await userEvent.click(within(dialog).getByRole("button", { name: "Stop and log" }));
    expect(await within(dialog).findByRole("status")).toHaveTextContent("Logged 10 min on RAG bot (project)");
    expect(fake.callsTo("POST", /\/api\/timer\/stop/)[0].body).toEqual({ minutes: 10, summary: "Built the chunker" });
  });

  it("rejects a bad number of minutes before calling the server", async () => {
    const { fake } = await open(items(), (f) => {
      f.planning.timer = {
        kind: "task", label: "Write report", started_at: new Date().toISOString(), elapsed_seconds: 60, logs_to: null,
        task_id: 1, lesson_id: null, topic_id: null, course_id: null, project_id: null,
      };
    });
    await userEvent.click(await screen.findByRole("button", { name: "Stop and log" }));
    const dialog = await screen.findByRole("dialog");
    const minutes = within(dialog).getByLabelText("Minutes to log");
    await userEvent.clear(minutes);
    await userEvent.type(minutes, "2000");
    await userEvent.click(within(dialog).getByRole("button", { name: "Stop and log" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("from 1 to 1440");
    expect(fake.callsTo("POST", /\/api\/timer\/stop/)).toHaveLength(0);
  });

  it("asks for the minutes when a timer has run for over a day", async () => {
    await open(items(), (f) => {
      f.planning.timer = {
        kind: "task", label: "Write report", started_at: new Date().toISOString(), elapsed_seconds: 30 * 3600, logs_to: null,
        task_id: 1, lesson_id: null, topic_id: null, course_id: null, project_id: null,
      };
    });
    await userEvent.click(await screen.findByRole("button", { name: "Stop and log" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/more than 24 hours/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Minutes to log")).toHaveValue(null);
  });

  it("keeps running when you close the dialog, and discards without logging", async () => {
    const { fake } = await open(items(), (f) => {
      f.planning.timer = {
        kind: "task", label: "Write report", started_at: new Date().toISOString(), elapsed_seconds: 60, logs_to: null,
        task_id: 1, lesson_id: null, topic_id: null, course_id: null, project_id: null,
      };
    });
    await userEvent.click(await screen.findByRole("button", { name: "Stop and log" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Keep running" }));
    expect(fake.planning.timer).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Discard the timer without logging" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Running timer" })).not.toBeInTheDocument());
    expect(fake.planning.stopped).toEqual([]);
  });

  it("shows the server's message if a timer is already running elsewhere", async () => {
    const { fake } = await open(items());
    await screen.findByRole("button", { name: "Start timer for Write report" });
    fake.planning.timer = {
      kind: "task", label: "Other", started_at: new Date().toISOString(), elapsed_seconds: 0, logs_to: null,
      task_id: 9, lesson_id: null, topic_id: null, course_id: null, project_id: null,
    }; // started in another tab after this page loaded
    await userEvent.click(screen.getByRole("button", { name: "Start timer for Write report" }));
    expect(await screen.findByText(/already running/, { selector: '[role="alert"]' })).toBeInTheDocument();
  });
});
