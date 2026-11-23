import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { addDays } from "../lib/dates";
import { installFakeApi, TODAY, type Fake } from "./fakeApi";
import { AGENTIC_TEMPLATE, installFakeCourses, mkCourse, mkLesson, mkModule, recompute, type FakeCourses } from "./fakeCourses";
import { renderAt } from "./render";

type Setup = { fake: Fake; store: FakeCourses };

/** A course with two modules: M1 has 3 lessons (10 / 20 / no minutes), M2 has 1. Nothing completed. */
function agentsCourse(overrides: Parameters<typeof mkCourse>[0] = {}) {
  const cid = 1;
  return mkCourse({
    id: cid, title: "Agents 101", provider: "DeepLearning.AI", url: "https://example.com/agents",
    modules: [
      mkModule({ id: 10, title: "Module 1", lessons: [
        mkLesson({ id: 101, module_id: 10, course_id: cid, title: "Intro", duration_minutes: 10, url: "https://example.com/intro" }),
        mkLesson({ id: 102, module_id: 10, course_id: cid, title: "Reflection", duration_minutes: 20 }),
        mkLesson({ id: 103, module_id: 10, course_id: cid, title: "Tools" }),
      ] }),
      mkModule({ id: 11, title: "Module 2", lessons: [mkLesson({ id: 104, module_id: 11, course_id: cid, title: "Planning" })] }),
    ],
    ...overrides,
  });
}

/** Mark lessons completed the way the server would (status + timestamp), then refresh derived values. */
function markDone(course: ReturnType<typeof mkCourse>, ...lessonIds: number[]) {
  for (const l of course.modules.flatMap((m) => m.lessons)) {
    if (lessonIds.includes(l.id)) {
      l.status = "completed";
      l.completed_at = "2026-11-20T10:00:00Z";
    }
  }
  recompute(course);
  return course;
}

async function open(path: string, seed: Partial<FakeCourses> = {}): Promise<Setup> {
  const fake = installFakeApi();
  const store = installFakeCourses(fake, seed);
  renderAt(path);
  return { fake, store };
}

async function openDetail(course = agentsCourse(), extra: Partial<FakeCourses> = {}): Promise<Setup> {
  const s = await open(`/courses/${course.id}`, { courses: [course], ...extra });
  await screen.findByRole("heading", { name: course.title });
  return s;
}

// ================================ list page ================================

describe("courses list", () => {
  it("shows each course with its real progress, next lesson and status", async () => {
    const done = markDone(agentsCourse(), 101);
    const c2 = mkCourse({ id: 2, title: "Empty course", provider: null });
    await open("/courses", { courses: [done, c2] });

    const list = await screen.findByRole("list", { name: "Courses" });
    const card = within(list).getByText("Agents 101").closest("a")!;
    expect(within(card).getByRole("progressbar", { name: "Agents 101 progress" })).toHaveAttribute("aria-valuenow", "25");
    expect(within(card).getByText("1 of 4 lessons")).toBeInTheDocument();
    expect(within(card).getByText("Reflection")).toBeInTheDocument(); // the next lesson, after the completed one
    expect(within(card).getByText("In progress")).toBeInTheDocument();
    expect(within(card).getByText(/~\s*20 min left/)).toBeInTheDocument(); // 30 total minus the completed 10
    expect(card).toHaveAttribute("href", "/courses/1");

    const empty = within(list).getByText("Empty course").closest("a")!;
    expect(within(empty).getByText("No lessons added yet")).toBeInTheDocument();
    expect(within(empty).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });

  it("filters by status tab via the server and keeps the tab in the URL", async () => {
    const { fake } = await open("/courses?status=paused", {
      courses: [agentsCourse({ status: "paused" }), mkCourse({ id: 2, title: "Active one" })],
    });
    expect(await screen.findByRole("tab", { name: "Paused" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Agents 101")).toBeInTheDocument();
    expect(screen.queryByText("Active one")).not.toBeInTheDocument();
    expect(fake.callsTo("GET", /\/api\/courses$/).some((c) => c.query.status === "paused")).toBe(true);
    await userEvent.click(screen.getByRole("tab", { name: "Active" }));
    expect(await screen.findByText("Active one")).toBeInTheDocument();
  });

  it("says 'No active courses' (not 'No courses yet') when only a completed course exists, and lists it under Completed", async () => {
    const finished = markDone(agentsCourse(), 101, 102, 103, 104);
    expect(finished.status).toBe("completed");
    await open("/courses", { courses: [finished] });
    expect(await screen.findByText("No active courses")).toBeInTheDocument();
    expect(screen.queryByText("No courses yet")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Completed" }));
    expect(await screen.findByText("Agents 101")).toBeInTheDocument();
  });

  it("falls back to Active for an unknown ?status=", async () => {
    await open("/courses?status=bogus");
    expect(await screen.findByRole("tab", { name: "Active" })).toHaveAttribute("aria-selected", "true");
  });

  it("explains the empty state and offers the template", async () => {
    await open("/courses", { templates: [{ ...AGENTIC_TEMPLATE }] });
    expect(await screen.findByText("No active courses")).toBeInTheDocument();
    const quick = await screen.findByRole("region", { name: "Course templates" });
    expect(within(quick).getByText(/DeepLearning.AI: Agentic AI/)).toBeInTheDocument();
    for (const m of AGENTIC_TEMPLATE.modules) expect(within(quick).getByText(m)).toBeInTheDocument();
    expect(within(quick).getByRole("link", { name: /Course page/ })).toHaveAttribute("href", "https://www.deeplearning.ai/courses/agentic-ai");
  });

  it("adding the template creates the course with its modules but no lessons and nothing completed", async () => {
    const { fake, store } = await open("/courses", { templates: [{ ...AGENTIC_TEMPLATE }] });
    await userEvent.click(await screen.findByRole("button", { name: "Add this course" }));
    await screen.findByRole("link", { name: /Back to courses/ }); // landed on the detail page
    expect(screen.getByRole("heading", { name: "Agentic AI" })).toBeInTheDocument();
    expect(fake.callsTo("POST", /course-templates\/deeplearning-agentic-ai$/)).toHaveLength(1);
    const mods = await screen.findByRole("list", { name: "Modules" });
    expect(within(mods).getAllByRole("heading", { level: 3 })).toHaveLength(5);
    expect(screen.getByText(/No lessons added yet/)).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
    expect(store.courses[0].modules.every((m) => m.lessons.length === 0)).toBe(true);
    expect(screen.queryByText("Every lesson is completed.")).not.toBeInTheDocument();
  });

  it("does not offer a template that was already added", async () => {
    await open("/courses", { templates: [{ ...AGENTIC_TEMPLATE, already_added: true }], courses: [agentsCourse()] });
    await screen.findByText("Agents 101");
    expect(screen.queryByRole("region", { name: "Course templates" })).not.toBeInTheDocument();
  });

  it("shows the server's message if adding a template fails", async () => {
    const { fake } = await open("/courses", { templates: [{ ...AGENTIC_TEMPLATE }] });
    fake.failNext(/^POST \/api\/course-templates/, 409, "You have already added this course");
    await userEvent.click(await screen.findByRole("button", { name: "Add this course" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already added");
  });
});

describe("creating a course", () => {
  it("validates, sends the fields, and opens the new course", async () => {
    const { fake } = await open("/courses");
    await userEvent.click((await screen.findAllByRole("button", { name: "New course" }))[0]);
    const dlg = screen.getByRole("dialog", { name: "New course" });

    await userEvent.click(within(dlg).getByRole("button", { name: "Create course" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("give the course a title");
    expect(fake.callsTo("POST", /\/api\/courses$/)).toHaveLength(0);

    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Deep Learning");
    await userEvent.type(within(dlg).getByLabelText(/^Provider/), "Coursera");
    await userEvent.type(within(dlg).getByLabelText(/^Link/), "https://example.com/dl");
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Priority/), "1");
    fireEvent.change(within(dlg).getByLabelText(/^Target finish date/), { target: { value: addDays(TODAY, 30) } });
    await userEvent.click(within(dlg).getByRole("button", { name: "Create course" }));

    await screen.findByRole("link", { name: /Back to courses/ }); // only the detail page has this: navigation finished
    expect(screen.getByRole("heading", { name: "Deep Learning" })).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/courses$/)[0].body).toMatchObject({
      title: "Deep Learning", provider: "Coursera", url: "https://example.com/dl", priority: 1, kind: "course", target_date: addDays(TODAY, 30), description: null,
    });
  });

  it("keeps the form and shows the server's reason when a link is rejected", async () => {
    const { fake } = await open("/courses");
    fake.failNext(/^POST \/api\/courses$/, 422, "url: Enter a full web address starting with http:// or https://");
    await userEvent.click((await screen.findAllByRole("button", { name: "New course" }))[0]);
    const dlg = screen.getByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Keep me");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create course" }));
    expect(await within(dlg).findByRole("alert")).toHaveTextContent("http:// or https://");
    expect(within(dlg).getByLabelText(/^Title/)).toHaveValue("Keep me");
  });
});

// ================================ detail page ================================

describe("course detail: progress", () => {
  it("shows progress, minutes left and the next lesson", async () => {
    await openDetail();
    expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("0 of 4 lessons completed")).toBeInTheDocument();
    expect(screen.getByText(/~30 min of lessons left/)).toBeInTheDocument();
    const next = screen.getByRole("region", { name: "Up next" });
    expect(within(next).getByText("Intro")).toBeInTheDocument();
    expect(within(next).getByText("Module 1")).toBeInTheDocument();
  });

  it("completing a lesson moves progress and the next lesson forward; un-completing reverses it", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("checkbox", { name: 'Mark "Intro" as done' }));
    await waitFor(() => expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "25"));
    expect(fake.callsTo("POST", /lessons\/101\/complete$/)).toHaveLength(1);
    const next = screen.getByRole("region", { name: "Up next" });
    expect(within(next).getByText("Reflection")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: 'Mark "Intro" as not done' })).toHaveAttribute("aria-checked", "true");

    await userEvent.click(screen.getByRole("checkbox", { name: 'Mark "Intro" as not done' }));
    await waitFor(() => expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "0"));
    expect(fake.callsTo("POST", /lessons\/101\/uncomplete$/)).toHaveLength(1);
  });

  it("the Up next card can complete the next lesson", async () => {
    const { fake } = await openDetail();
    await userEvent.click(within(screen.getByRole("region", { name: "Up next" })).getByRole("button", { name: "Mark complete" }));
    await waitFor(() => expect(fake.callsTo("POST", /lessons\/101\/complete$/)).toHaveLength(1));
  });

  it("finishing the last lesson completes the course and says so", async () => {
    const c = markDone(agentsCourse(), 101, 102, 103);
    await openDetail(c);
    expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "75");
    await userEvent.click(screen.getByRole("checkbox", { name: 'Mark "Planning" as done' }));
    expect(await screen.findByText("Every lesson is completed.")).toBeInTheDocument();
    expect(screen.getByText("Completed", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "100");
    expect(screen.queryByRole("button", { name: "Pause" })).not.toBeInTheDocument(); // a finished course can't be paused

    await userEvent.click(screen.getByRole("checkbox", { name: 'Mark "Planning" as not done' }));
    await waitFor(() => expect(screen.queryByText("Every lesson is completed.")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument(); // reopened
  });

  it("does not call a course complete while a module still has no lessons, and says why", async () => {
    // Module 2 is empty: every lesson that exists is done, but the course is not.
    const c = markDone(
      mkCourse({
        id: 3, title: "Half entered",
        modules: [
          mkModule({ id: 30, title: "Entered", lessons: [mkLesson({ id: 301, module_id: 30, course_id: 3, title: "Only lesson" })] }),
          mkModule({ id: 31, title: "Not entered yet" }),
        ],
      }),
      301,
    );
    expect(c.status).toBe("active");
    await openDetail(c);
    expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByRole("note")).toHaveTextContent("1 module has no lessons yet, so the course can't be marked complete");
    const next = screen.getByRole("region", { name: "Up next" });
    expect(within(next).getByText(/1 module still has no lessons/)).toBeInTheDocument();
    expect(screen.queryByText("Every lesson is completed.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument(); // still an active course
  });

  it("the list says the same on the course card", async () => {
    const c = markDone(
      mkCourse({ id: 3, title: "Half entered", modules: [
        mkModule({ id: 30, title: "Entered", lessons: [mkLesson({ id: 301, module_id: 30, course_id: 3, title: "Only lesson" })] }),
        mkModule({ id: 31, title: "A" }), mkModule({ id: 32, title: "B" }),
      ] }),
      301,
    );
    await open("/courses", { courses: [c] });
    expect(await screen.findByText("All added lessons done · 2 modules still empty")).toBeInTheDocument();
  });

  it("Start marks a lesson in progress", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: 'Start "Reflection"' }));
    await waitFor(() => expect(fake.callsTo("POST", /lessons\/102\/start$/)).toHaveLength(1));
    const row = screen.getByText("Reflection").closest("li")!;
    expect(await within(row).findByText("In progress")).toBeInTheDocument();
  });

  it("shows the server's message when a lesson action is refused", async () => {
    const { fake } = await openDetail();
    fake.failNext(/^POST \/api\/lessons\/101\/complete/, 500, "Could not save");
    await userEvent.click(screen.getByRole("checkbox", { name: 'Mark "Intro" as done' }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save");
    expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "0");
  });

  it("explains a course that has no modules or lessons", async () => {
    await openDetail(mkCourse({ id: 9, title: "Blank" }));
    expect(screen.getByText(/No modules yet/)).toBeInTheDocument();
    expect(screen.getByText("Add lessons to see what's next.")).toBeInTheDocument();
  });

  it("opens external links safely", async () => {
    await openDetail();
    for (const link of [screen.getByRole("link", { name: /Course page/ }), screen.getByRole("link", { name: "Intro" })]) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
      expect(link.getAttribute("href")).toMatch(/^https:\/\//);
    }
  });

  it("says plainly when a course does not exist", async () => {
    await open("/courses/777");
    expect(await screen.findByText("Course not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to courses/ })).toHaveAttribute("href", "/courses");
  });
});

describe("course detail: editing structure", () => {
  it("pastes a list of lessons, cleaning markers, previewing the count, and adds them not-started", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getAllByRole("button", { name: "Paste lessons" })[1]); // Module 2
    const dlg = screen.getByRole("dialog", { name: /Paste lessons into "Module 2"/ });
    expect(within(dlg).getByText("Nothing to add yet.")).toBeInTheDocument();
    expect(within(dlg).getByRole("button", { name: "Add lessons" })).toBeDisabled();

    await userEvent.type(within(dlg).getByLabelText(/^Lesson titles/), "1. Multi-agent workflows{enter}{enter}- Communication patterns{enter}Final quiz");
    expect(within(dlg).getByText("3 lessons will be added.")).toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("button", { name: "Add lessons" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    expect(fake.callsTo("POST", /courses\/1\/bulk-lessons$/)[0].body).toEqual({
      module_id: 11, titles: ["Multi-agent workflows", "Communication patterns", "Final quiz"],
    });
    const m2 = screen.getByRole("list", { name: "Lessons in Module 2" });
    expect(within(m2).getAllByRole("checkbox").map((b) => b.getAttribute("aria-checked"))).toEqual(["false", "false", "false", "false"]); // none completed
    expect(screen.getByText("0 of 7 lessons completed")).toBeInTheDocument();
  });

  it("adds a lesson with a link, type and duration", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getAllByRole("button", { name: "Add lesson" })[0]);
    const dlg = screen.getByRole("dialog", { name: "Add lesson" });
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Evals deep dive");
    await userEvent.type(within(dlg).getByLabelText(/^Link/), "https://example.com/evals");
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Type/), "video");
    await userEvent.type(within(dlg).getByLabelText(/^Duration/), "15");
    await userEvent.click(within(dlg).getByRole("button", { name: "Add lesson" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(fake.callsTo("POST", /modules\/10\/lessons$/)[0].body).toMatchObject({
      title: "Evals deep dive", url: "https://example.com/evals", lesson_type: "video", duration_minutes: 15, notes: null,
    });
    const row = (await screen.findByText("Evals deep dive")).closest("li")!;
    expect(within(row).getByText("Video")).toBeInTheDocument();
    expect(within(row).getByText("15 min")).toBeInTheDocument();
  });

  it("edits a lesson and can move it to another module", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: 'Edit lesson "Tools"' }));
    const dlg = screen.getByRole("dialog", { name: "Edit lesson" });
    expect(within(dlg).getByLabelText(/^Title/)).toHaveValue("Tools");
    await userEvent.clear(within(dlg).getByLabelText(/^Title/));
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Tool use");
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Module/), "11");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(fake.callsTo("PATCH", /lessons\/103$/)[0].body).toMatchObject({ title: "Tool use", module_id: 11 });
    expect(within(screen.getByRole("list", { name: "Lessons in Module 2" })).getByText("Tool use")).toBeInTheDocument();
  });

  it("deletes a lesson only after confirmation", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: 'Delete lesson "Tools"' }));
    let dlg = screen.getByRole("dialog", { name: "Delete lesson?" });
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /lessons\//)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: 'Delete lesson "Tools"' }));
    dlg = screen.getByRole("dialog", { name: "Delete lesson?" });
    await userEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("Tools")).not.toBeInTheDocument());
    expect(fake.callsTo("DELETE", /lessons\/103$/)).toHaveLength(1);
    expect(screen.getByText("0 of 3 lessons completed")).toBeInTheDocument();
  });

  it("adds, renames, reorders and deletes modules", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: "Add module" }));
    let dlg = screen.getByRole("dialog", { name: "Add module" });
    await userEvent.click(within(dlg).getByRole("button", { name: "Add module" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("give the module a title");
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Module 3");
    await userEvent.click(within(dlg).getByRole("button", { name: "Add module" }));
    expect(await screen.findByRole("heading", { name: "Module 3" })).toBeInTheDocument();
    expect(fake.callsTo("POST", /courses\/1\/modules$/)[0].body).toEqual({ title: "Module 3" });

    await userEvent.click(screen.getByRole("button", { name: 'Rename module "Module 3"' }));
    dlg = screen.getByRole("dialog", { name: "Rename module" });
    await userEvent.clear(within(dlg).getByLabelText(/^Title/));
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Capstone");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("heading", { name: "Capstone" })).toBeInTheDocument();

    expect(screen.getByRole("button", { name: 'Move module "Module 1" up' })).toBeDisabled(); // first
    expect(screen.getByRole("button", { name: 'Move module "Capstone" down' })).toBeDisabled(); // last
    await userEvent.click(screen.getByRole("button", { name: 'Move module "Capstone" up' }));
    await waitFor(() => expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Module 1", "Capstone", "Module 2"]));

    await userEvent.click(screen.getByRole("button", { name: 'Delete module "Module 2"' }));
    dlg = screen.getByRole("dialog", { name: "Delete module?" });
    expect(dlg).toHaveTextContent("1 lesson");
    await userEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Module 2" })).not.toBeInTheDocument());
  });

  it("reorders lessons within a module", async () => {
    const { fake } = await openDetail();
    expect(screen.getByRole("button", { name: 'Move lesson "Intro" up' })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: 'Move lesson "Intro" down' }));
    await waitFor(() => expect(fake.callsTo("POST", /lessons\/101\/move$/)[0].body).toEqual({ direction: "down" }));
    const m1 = screen.getByRole("list", { name: "Lessons in Module 1" });
    await waitFor(() => expect(within(m1).getAllByRole("checkbox")[0]).toHaveAccessibleName('Mark "Reflection" as done'));
  });
});

describe("course detail: status and course actions", () => {
  it("pauses, resumes, archives and restores through the server", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(await screen.findByText("Paused")).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /courses\/1$/)[0].body).toEqual({ status: "paused" });
    await userEvent.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    expect(await screen.findByText("Archived")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(fake.callsTo("PATCH", /courses\/1$/).map((c) => c.body?.status)).toEqual(["paused", "active", "archived", "active"]));
  });

  it("edits the course details", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dlg = screen.getByRole("dialog", { name: "Edit course" });
    expect(within(dlg).getByLabelText(/^Provider/)).toHaveValue("DeepLearning.AI");
    await userEvent.clear(within(dlg).getByLabelText(/^Title/));
    await userEvent.type(within(dlg).getByLabelText(/^Title/), "Agents 201");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "Agents 201" })).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /courses\/1$/)[0].body).toMatchObject({ title: "Agents 201", provider: "DeepLearning.AI" });
  });

  it("deletes a course only after confirmation, then returns to the list", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: "Delete course" }));
    let dlg = screen.getByRole("dialog", { name: "Delete course?" });
    expect(dlg).toHaveTextContent("Study time you logged is kept");
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /\/api\/courses\//)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Delete course" }));
    dlg = screen.getByRole("dialog", { name: "Delete course?" });
    await userEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("heading", { name: "Courses" })).toBeInTheDocument();
    expect(fake.callsTo("DELETE", /courses\/1$/)).toHaveLength(1);
  });
});

describe("course detail: study time", () => {
  it("logs study time, shows it in the list, and can delete it", async () => {
    const { fake } = await openDetail();
    expect(await screen.findByText("No study time logged yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Log study time" }));
    const dlg = screen.getByRole("dialog", { name: "Log study time" });
    expect(within(dlg).getByLabelText(/^Date/)).toHaveValue(TODAY);
    await userEvent.type(within(dlg).getByLabelText(/^Minutes studied/), "45");
    await userEvent.selectOptions(within(dlg).getByLabelText(/^Lesson/), "101");
    await userEvent.type(within(dlg).getByLabelText(/^What did you study/), "Watched the intro");
    await userEvent.click(within(dlg).getByRole("button", { name: "Log time" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(fake.callsTo("POST", /learning-sessions$/)[0].body).toEqual({ course_id: 1, lesson_id: 101, minutes: 45, date: TODAY, notes: "Watched the intro" });

    const list = await screen.findByRole("list", { name: "Study sessions" });
    expect(within(list).getByText("45 min")).toBeInTheDocument();
    expect(within(list).getByText(/Today/)).toBeInTheDocument();
    expect(within(list).getByText(/Watched the intro/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete 45 minute session" }));
    await waitFor(() => expect(screen.getByText("No study time logged yet.")).toBeInTheDocument());
  });

  it("refuses missing minutes and future dates before calling the server", async () => {
    const { fake } = await openDetail();
    await userEvent.click(screen.getByRole("button", { name: "Log study time" }));
    const dlg = screen.getByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: "Log time" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("Enter the minutes studied");
    await userEvent.type(within(dlg).getByLabelText(/^Minutes studied/), "30");
    fireEvent.change(within(dlg).getByLabelText(/^Date/), { target: { value: addDays(TODAY, 2) } });
    await userEvent.click(within(dlg).getByRole("button", { name: "Log time" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("future");
    expect(fake.callsTo("POST", /learning-sessions$/)).toHaveLength(0);
  });
});
