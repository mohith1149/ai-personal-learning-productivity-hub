import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { todayIn } from "../lib/dates";
import { installFakeApi, USER } from "./fakeApi";
import { installFakePlanner, mkItem } from "./fakePlanner";
import { defaultRoadmap, installFakeRoadmap } from "./fakeRoadmap";
import { renderAt } from "./render";

const TODAY = () => todayIn(USER.timezone);

async function settings(setup?: (f: ReturnType<typeof installFakeApi>) => void) {
  const fake = installFakeApi();
  setup?.(fake);
  renderAt("/settings");
  const card = await screen.findByRole("region", { name: "Planning settings" });
  const box = await within(card).findByRole("checkbox", { name: /Plan hard topics for the hours I focus best/ });
  return { fake, card, box };
}

const save = (card: HTMLElement) => userEvent.click(within(card).getByRole("button", { name: "Save planning settings" }));

describe("difficulty on the roadmap", () => {
  it("shows each topic's difficulty and changes it from the menu", async () => {
    const fake = installFakeApi();
    installFakeRoadmap(fake, defaultRoadmap());
    renderAt("/roadmap");
    const menu = await screen.findByRole("combobox", { name: "Difficulty of Python" });
    for (const m of screen.getAllByRole("combobox", { name: /^Difficulty of / })) expect(m).toHaveValue("normal");
    await userEvent.selectOptions(menu, "hard");
    await waitFor(() => expect(fake.callsTo("PATCH", /roadmap\/topics\/101$/)[0].body).toEqual({ difficulty: "hard" }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Difficulty of Python" })).toHaveValue("hard"));
    expect(screen.getByRole("combobox", { name: "Difficulty of Java fundamentals" })).toHaveValue("normal");
  });

  it("offers exactly hard, normal and light", async () => {
    const fake = installFakeApi();
    installFakeRoadmap(fake, defaultRoadmap());
    renderAt("/roadmap");
    const menu = await screen.findByRole("combobox", { name: "Difficulty of Python" });
    expect(within(menu).getAllByRole("option").map((o) => o.textContent)).toEqual(["Hard", "Normal", "Light"]);
  });

  it("shows the server's message if the change fails, and keeps the old value", async () => {
    const fake = installFakeApi();
    installFakeRoadmap(fake, defaultRoadmap());
    renderAt("/roadmap");
    const menu = await screen.findByRole("combobox", { name: "Difficulty of Python" });
    fake.failNext(/PATCH \/api\/roadmap\/topics\/101/, 500, "Could not save the difficulty");
    await userEvent.selectOptions(menu, "light");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save the difficulty");
    expect(screen.getByRole("combobox", { name: "Difficulty of Python" })).toHaveValue("normal");
  });
});

describe("focus hours in settings", () => {
  it("is off by default and the time boxes are disabled", async () => {
    const { card, box } = await settings();
    expect(box).not.toBeChecked();
    expect(within(card).getByLabelText("Monday focus from")).toBeDisabled();
  });

  it("saves a window for each day, and an empty day as none", async () => {
    const { fake, card, box } = await settings();
    await userEvent.click(box);
    const from = within(card).getByLabelText("Sunday focus from");
    const to = within(card).getByLabelText("Sunday focus until");
    await userEvent.clear(from);
    await userEvent.clear(to);
    await save(card);
    expect(await within(card).findByText("Saved")).toBeInTheDocument();
    expect(fake.planning.prefs.focus_windows).toEqual(Array(6).fill("06:00-09:00").concat(""));
  });

  it("saves changed times", async () => {
    const { fake, card, box } = await settings();
    await userEvent.click(box);
    const from = within(card).getByLabelText("Saturday focus from");
    await userEvent.clear(from);
    await userEvent.type(from, "08:30");
    const to = within(card).getByLabelText("Saturday focus until");
    await userEvent.clear(to);
    await userEvent.type(to, "11:00");
    await save(card);
    await within(card).findByText("Saved");
    expect(fake.planning.prefs.focus_windows?.[5]).toBe("08:30-11:00");
  });

  it("loads saved windows into the form", async () => {
    const { card, box } = await settings((f) => (f.planning.prefs.focus_windows = ["05:00-07:00", "", "", "", "", "", ""]));
    expect(box).toBeChecked();
    expect(within(card).getByLabelText("Monday focus from")).toHaveValue("05:00");
    expect(within(card).getByLabelText("Monday focus until")).toHaveValue("07:00");
    expect(within(card).getByLabelText("Tuesday focus from")).toHaveValue("");
  });

  it("turning it off saves no windows", async () => {
    const { fake, card, box } = await settings((f) => (f.planning.prefs.focus_windows = Array(7).fill("06:00-09:00")));
    await userEvent.click(box);
    await save(card);
    await within(card).findByText("Saved");
    expect(fake.planning.prefs.focus_windows).toBeNull();
  });

  it("refuses an end that is not after the start, without calling the server", async () => {
    const { fake, card, box } = await settings();
    await userEvent.click(box);
    const to = within(card).getByLabelText("Monday focus until");
    await userEvent.clear(to);
    await userEvent.type(to, "05:00");
    await save(card);
    expect(await within(card).findByRole("alert")).toHaveTextContent("Monday: your focus hours must end after they start");
    expect(fake.callsTo("PATCH", /preferences/)).toHaveLength(0);
  });

  it("refuses a half-filled day", async () => {
    const { fake, card, box } = await settings();
    await userEvent.click(box);
    await userEvent.clear(within(card).getByLabelText("Friday focus until"));
    await save(card);
    expect(await within(card).findByRole("alert")).toHaveTextContent("Friday: fill in both");
    expect(fake.callsTo("PATCH", /preferences/)).toHaveLength(0);
  });

  it("leaving every day empty saves as not set", async () => {
    const { fake, card, box } = await settings();
    await userEvent.click(box);
    for (const d of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]) {
      await userEvent.clear(within(card).getByLabelText(`${d} focus from`));
      await userEvent.clear(within(card).getByLabelText(`${d} focus until`));
    }
    await save(card);
    await within(card).findByText("Saved");
    expect(fake.planning.prefs.focus_windows).toBeNull();
  });
});

describe("hints on the planner", () => {
  async function plan(items: ReturnType<typeof mkItem>[]) {
    const fake = installFakeApi();
    installFakePlanner(fake, { days: { [TODAY()]: items } });
    renderAt("/planner");
    await screen.findByRole("heading", { name: "Daily planner", level: 1 });
    return fake;
  }

  it("shows the hint under a hard topic", async () => {
    await plan([mkItem({ kind: "topic", ref_id: 5, title: "Transformers", difficulty: "hard", hint: "Hard topic: do it in your focus hours, 06:00–09:00" })]);
    expect(await screen.findByText("Hard topic: do it in your focus hours, 06:00–09:00")).toBeInTheDocument();
  });

  it("shows the light hint on a video", async () => {
    await plan([mkItem({ kind: "video", ref_id: 6, title: "How DNS works", hint: "Light: fine for a walk, the evening or spare time" })]);
    expect(await screen.findByText(/fine for a walk/)).toBeInTheDocument();
  });

  it("shows nothing extra when an item has no hint", async () => {
    await plan([mkItem({ kind: "task", ref_id: 7, title: "File taxes" })]);
    await screen.findByText("File taxes");
    expect(screen.queryByText(/focus hours/)).not.toBeInTheDocument();
    expect(screen.queryByText(/fine for a walk/)).not.toBeInTheDocument();
  });
});
