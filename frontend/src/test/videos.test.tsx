import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi, type Fake } from "./fakeApi";
import { installFakeVideos, mkPlaylist, mkVideo, type FakeVideos } from "./fakeVideos";
import { renderAt } from "./render";

type Setup = { fake: Fake; store: FakeVideos };

/** One ByteByteGo playlist (2 per day) with three unwatched videos. */
function bbg() {
  return {
    playlists: [mkPlaylist({ id: 1, name: "ByteByteGo", daily_target: 2, source_url: "https://www.youtube.com/@ByteByteGo" })],
    videos: [
      mkVideo({ id: 11, playlist_id: 1, position: 1, title: "How DNS works", url: "https://youtu.be/aaaaaaaaaaa", category: "Networking" }),
      mkVideo({ id: 12, playlist_id: 1, position: 2, title: "Load balancers" }),
      mkVideo({ id: 13, playlist_id: 1, position: 3, title: "Rate limiting" }),
    ],
  };
}

async function open(path: string, seed: Partial<FakeVideos> = bbg()): Promise<Setup> {
  const fake = installFakeApi();
  const store = installFakeVideos(fake, seed);
  renderAt(path);
  return { fake, store };
}

const upNext = () => screen.findByRole("list", { name: "Up next today" });
const videoList = () => screen.findByRole("list", { name: "Video list" });
const titlesIn = (list: HTMLElement) => within(list).getAllByRole("checkbox").map((c) => c.getAttribute("aria-label"));

// ================================ empty state + playlists ================================

describe("playlists", () => {
  it("shows an honest empty state and starts a pre-filled ByteByteGo playlist (no videos invented)", async () => {
    const { fake, store } = await open("/videos", { playlists: [], videos: [] });
    expect(await screen.findByText("No playlists yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start a ByteByteGo playlist" }));

    const dialog = await screen.findByRole("dialog", { name: "New playlist" });
    expect(within(dialog).getByLabelText("Name")).toHaveValue("ByteByteGo");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));

    expect(await screen.findByRole("heading", { name: "ByteByteGo", level: 2 })).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/video-playlists$/)[0].body).toMatchObject({
      name: "ByteByteGo", source_url: "https://www.youtube.com/@ByteByteGo", daily_target: 1, active: true,
    });
    expect(store.videos).toHaveLength(0);
    expect(screen.getByText("No videos added yet")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("validates the name and the daily target before sending anything", async () => {
    const { fake } = await open("/videos", { playlists: [], videos: [] });
    await userEvent.click((await screen.findAllByRole("button", { name: "New playlist" }))[0]);
    const dialog = await screen.findByRole("dialog", { name: "New playlist" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Please give the playlist a name.");

    await userEvent.type(within(dialog).getByLabelText("Name"), "Mine");
    await userEvent.clear(within(dialog).getByLabelText("Videos to watch per day"));
    await userEvent.type(within(dialog).getByLabelText("Videos to watch per day"), "0");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("whole number from 1 to 50");
    expect(fake.callsTo("POST", /video-playlists/)).toHaveLength(0);
  });

  it("shows the server's message for a duplicate name", async () => {
    await open("/videos");
    await screen.findByRole("heading", { name: "ByteByteGo", level: 2 });
    await userEvent.click(screen.getAllByRole("button", { name: "New playlist" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "New playlist" });
    await userEvent.type(within(dialog).getByLabelText("Name"), "bytebytego");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already have a playlist with that name");
  });

  it("switches between playlists with tabs", async () => {
    await open("/videos", {
      playlists: [mkPlaylist({ id: 1, name: "ByteByteGo" }), mkPlaylist({ id: 2, name: "Rust talks" })],
      videos: [mkVideo({ playlist_id: 2, title: "Ownership explained" })],
    });
    await screen.findByRole("heading", { name: "ByteByteGo", level: 2 });
    await userEvent.click(screen.getByRole("tab", { name: "Rust talks" }));
    expect(await screen.findByRole("heading", { name: "Rust talks", level: 2 })).toBeInTheDocument();
    expect(await within(await videoList()).findByText("Ownership explained")).toBeInTheDocument();
  });

  it("edits a playlist's daily target and shows it on the Today card", async () => {
    const { fake } = await open("/videos");
    expect(await screen.findByText("Watched 0 of 2 today")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit playlist" });
    const target = within(dialog).getByLabelText("Videos to watch per day");
    await userEvent.clear(target);
    await userEvent.type(target, "3");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Watched 0 of 3 today")).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /video-playlists\/1$/)[0].body).toMatchObject({ daily_target: 3 });
  });

  it("deletes a playlist only after confirmation, warning how many videos go with it", async () => {
    const { fake } = await open("/videos");
    await userEvent.click(await screen.findByRole("button", { name: "Delete playlist ByteByteGo" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete playlist?" });
    expect(dialog).toHaveTextContent("3 videos");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /video-playlists/)).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Delete playlist ByteByteGo" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No playlists yet")).toBeInTheDocument();
    expect(fake.callsTo("DELETE", /video-playlists\/1$/)).toHaveLength(1);
  });

  it("shows the server error when playlists cannot be loaded, and retries", async () => {
    const fake = installFakeApi();
    installFakeVideos(fake, bbg());
    fake.failNext(/^GET \/api\/video-playlists$/, 500, "Database is down");
    renderAt("/videos");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "ByteByteGo", level: 2 })).toBeInTheDocument();
  });
});

// ================================ today + progress ================================

describe("today and progress", () => {
  it("lists exactly as many videos as the daily target, in order, with real progress", async () => {
    await open("/videos");
    const list = await upNext();
    expect(within(list).getByText("How DNS works")).toBeInTheDocument();
    expect(within(list).getByText("Load balancers")).toBeInTheDocument();
    expect(within(list).queryByText("Rate limiting")).not.toBeInTheDocument();
    expect(screen.getByText("Watched 0 of 2 today")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "ByteByteGo progress" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("0 of 3 watched")).toBeInTheDocument();
  });

  it("marking a video watched updates progress and removes it from today's list (never recommended again)", async () => {
    const { fake } = await open("/videos");
    const list = await upNext();
    await userEvent.click(within(list).getByRole("button", { name: "Mark How DNS works as watched" }));

    await waitFor(() => expect(screen.getByText("Watched 1 of 2 today")).toBeInTheDocument());
    expect(fake.callsTo("POST", /\/api\/videos\/11\/complete$/)).toHaveLength(1);
    expect(screen.getByText("1 of 3 watched")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "ByteByteGo progress" })).toHaveAttribute("aria-valuenow", "33");

    const next = await upNext();
    expect(within(next).queryByText("How DNS works")).not.toBeInTheDocument();
    expect(within(next).getByText("Load balancers")).toBeInTheDocument();
    // the To watch list no longer contains it either
    await waitFor(() => expect(titlesIn(screen.getByRole("list", { name: "Video list" }))).not.toContain("Mark How DNS works as watched"));
  });

  it("says the target is met once enough videos are watched and points at what is next", async () => {
    const seed = bbg();
    seed.playlists[0].daily_target = 1;
    seed.videos[0] = { ...seed.videos[0], status: "completed", completed_at: new Date().toISOString() };
    await open("/videos", seed);
    const note = (await screen.findByText(/Today's target is met/)).closest("p")!;
    expect(note).toHaveTextContent("Load balancers");
    expect(screen.queryByRole("list", { name: "Up next today" })).not.toBeInTheDocument();
  });

  it("does not count a video watched on an earlier day towards today", async () => {
    const seed = bbg();
    seed.videos[0] = { ...seed.videos[0], status: "completed", completed_at: "2026-11-01T10:00:00Z" };
    await open("/videos", seed);
    expect(await screen.findByText("Watched 0 of 2 today")).toBeInTheDocument();
    expect(screen.getByText("1 of 3 watched")).toBeInTheDocument();
  });

  it("says everything is watched when nothing is left", async () => {
    const seed = bbg();
    seed.videos = seed.videos.map((v) => ({ ...v, status: "completed" as const, completed_at: "2026-11-01T10:00:00Z" }));
    await open("/videos", seed);
    expect(await screen.findByText("Every video in this playlist is watched.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "ByteByteGo progress" })).toHaveAttribute("aria-valuenow", "100");
  });

  it("shows the server's message if marking watched fails", async () => {
    const { fake } = await open("/videos");
    fake.failNext(/^POST \/api\/videos\/\d+\/complete/, 422, "Could not complete that video");
    const list = await upNext();
    await userEvent.click(within(list).getByRole("button", { name: "Mark How DNS works as watched" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not complete that video");
    expect(screen.getByText("Watched 0 of 2 today")).toBeInTheDocument();
  });
});

// ================================ video list ================================

describe("video list", () => {
  it("shows videos to watch with status, category and a safe external link", async () => {
    await open("/videos");
    const list = await videoList();
    expect(titlesIn(list)).toEqual(["Mark How DNS works as watched", "Mark Load balancers as watched", "Mark Rate limiting as watched"]);
    expect(within(list).getByText("Networking")).toBeInTheDocument();
    const link = within(list).getByRole("link", { name: "Open How DNS works" });
    expect(link).toHaveAttribute("href", "https://youtu.be/aaaaaaaaaaa");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
    expect(within(list).queryByRole("link", { name: "Open Load balancers" })).not.toBeInTheDocument(); // no link, no anchor
  });

  it("filters by view through the server and can reopen a watched video", async () => {
    const seed = bbg();
    seed.videos[1] = { ...seed.videos[1], status: "completed", completed_at: "2026-11-01T10:00:00Z" };
    const { fake } = await open("/videos", seed);
    await videoList();
    expect(screen.queryByRole("checkbox", { name: "Reopen Load balancers" })).not.toBeInTheDocument(); // hidden from To watch

    await userEvent.click(screen.getByRole("tab", { name: "Watched" }));
    const done = await screen.findByRole("checkbox", { name: "Reopen Load balancers" });
    expect(done).toBeChecked();
    expect(fake.callsTo("GET", /videos$/).some((c) => c.query.view === "completed")).toBe(true);

    await userEvent.click(done);
    expect(await screen.findByText("Nothing watched yet")).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/videos\/12\/uncomplete$/)).toHaveLength(1);
    await userEvent.click(screen.getByRole("tab", { name: "To watch" }));
    expect(titlesIn(await videoList())).toContain("Mark Load balancers as watched");
  });

  it("searches by title on the server", async () => {
    const { fake } = await open("/videos");
    await videoList();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search videos" }), "rate");
    await waitFor(() => expect(titlesIn(screen.getByRole("list", { name: "Video list" }))).toEqual(["Mark Rate limiting as watched"]));
    expect(fake.callsTo("GET", /videos$/).some((c) => c.query.q === "rate")).toBe(true);
    await userEvent.clear(screen.getByRole("searchbox", { name: "Search videos" }));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search videos" }), "zzz");
    expect(await screen.findByText("No videos match your search")).toBeInTheDocument();
  });

  it("starts a video (status becomes In progress)", async () => {
    const { fake } = await open("/videos");
    const list = await videoList();
    await userEvent.click(within(list).getByRole("button", { name: "Start Load balancers" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Video list" })).getByText("In progress")).toBeInTheDocument());
    expect(fake.callsTo("POST", /\/api\/videos\/12\/start$/)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Start Load balancers" })).not.toBeInTheDocument();
  });

  it("reorders with up/down and disables the buttons at the ends", async () => {
    const { fake } = await open("/videos");
    const list = await videoList();
    expect(within(list).getByRole("button", { name: "Move How DNS works up" })).toBeDisabled();
    expect(within(list).getByRole("button", { name: "Move Rate limiting down" })).toBeDisabled();
    await userEvent.click(within(list).getByRole("button", { name: "Move How DNS works down" }));
    await waitFor(() =>
      expect(titlesIn(screen.getByRole("list", { name: "Video list" }))).toEqual([
        "Mark Load balancers as watched", "Mark How DNS works as watched", "Mark Rate limiting as watched",
      ]),
    );
    expect(fake.callsTo("POST", /\/api\/videos\/11\/move$/)[0].body).toEqual({ direction: "down" });
  });

  it("does not offer reordering while searching or in the Watched view", async () => {
    await open("/videos");
    await videoList();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search videos" }), "o");
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Video list" })).getAllByRole("button", { name: /Move .* (up|down)/ }).every((b) => (b as HTMLButtonElement).disabled)).toBe(true));
  });
});

// ================================ add / edit / delete ================================

describe("adding, editing and deleting videos", () => {
  it("requires a title and sends the fields", async () => {
    const { fake } = await open("/videos");
    await videoList();
    await userEvent.click(screen.getByRole("button", { name: "Add video" }));
    const dialog = await screen.findByRole("dialog", { name: "Add video" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Add video" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Please give the video a title.");
    expect(fake.callsTo("POST", /\/videos$/)).toHaveLength(0);

    await userEvent.type(within(dialog).getByLabelText("Title"), "CDN basics");
    await userEvent.type(within(dialog).getByLabelText(/^Link/), "https://youtu.be/ccccccccccc");
    await userEvent.type(within(dialog).getByLabelText("Category"), "Networking");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add video" }));

    expect(await within(await videoList()).findByText("CDN basics")).toBeInTheDocument();
    expect(fake.callsTo("POST", /video-playlists\/1\/videos$/)[0].body).toEqual({
      title: "CDN basics", url: "https://youtu.be/ccccccccccc", category: "Networking", description: null, notes: null,
    });
  });

  it("shows the server's rejection inside the form and keeps it open", async () => {
    const { fake } = await open("/videos");
    await videoList();
    fake.failNext(/^POST \/api\/video-playlists\/1\/videos$/, 409, "That video is already in this playlist");
    await userEvent.click(screen.getByRole("button", { name: "Add video" }));
    const dialog = await screen.findByRole("dialog", { name: "Add video" });
    await userEvent.type(within(dialog).getByLabelText("Title"), "Again");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add video" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already in this playlist");
    expect(screen.getByRole("dialog", { name: "Add video" })).toBeInTheDocument();
  });

  it("edits a video and shows the change", async () => {
    const { fake } = await open("/videos");
    const list = await videoList();
    await userEvent.click(within(list).getByRole("button", { name: "Edit Load balancers" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit video" });
    expect(within(dialog).getByLabelText("Title")).toHaveValue("Load balancers");
    await userEvent.clear(within(dialog).getByLabelText("Title"));
    await userEvent.type(within(dialog).getByLabelText("Title"), "Load balancing 101");
    await userEvent.type(within(dialog).getByLabelText("Notes"), "L4 vs L7");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await within(await videoList()).findByText("Load balancing 101")).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /\/api\/videos\/12$/)[0].body).toMatchObject({ title: "Load balancing 101", notes: "L4 vs L7" });
    expect(within(await videoList()).getByText(/Note: L4 vs L7/)).toBeInTheDocument();
  });

  it("deletes a video only after confirmation", async () => {
    const { fake } = await open("/videos");
    const list = await videoList();
    await userEvent.click(within(list).getByRole("button", { name: "Delete Rate limiting" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete video?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /\/api\/videos/)).toHaveLength(0);
    expect(within(await videoList()).getByText("Rate limiting")).toBeInTheDocument();

    await userEvent.click(within(await videoList()).getByRole("button", { name: "Delete Rate limiting" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Video list" })).queryByText("Rate limiting")).not.toBeInTheDocument());
    expect(fake.callsTo("DELETE", /\/api\/videos\/13$/)).toHaveLength(1);
  });
});

// ================================ paste links ================================

describe("pasting links", () => {
  async function openPaste() {
    const s = await open("/videos");
    await videoList();
    await userEvent.click(screen.getByRole("button", { name: "Paste links" }));
    const dialog = await screen.findByRole("dialog", { name: "Paste video links" });
    return { ...s, dialog };
  }

  it("counts lines, sends them, and reports added / duplicate / unreadable lines", async () => {
    const { fake, dialog } = await openPaste();
    const box = within(dialog).getByLabelText(/Links, one per line/);
    fireEvent.change(box, { target: { value: "CDN basics | https://youtu.be/bbbbbbbbbbb\n\nhttps://youtu.be/aaaaaaaaaaa\nnot a link\n" } });
    expect(within(dialog).getByText("3 lines")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Category for all/), "Systems");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add videos" }));

    const result = await within(dialog).findByRole("status");
    expect(result).toHaveTextContent("Added 1 video");
    expect(result).toHaveTextContent("skipped 1 already in the playlist");
    expect(result).toHaveTextContent("couldn't read 1 line");
    expect(within(dialog).getByText("not a link")).toBeInTheDocument();
    expect(fake.callsTo("POST", /bulk-videos$/)[0].body).toEqual({
      lines: ["CDN basics | https://youtu.be/bbbbbbbbbbb", "https://youtu.be/aaaaaaaaaaa", "not a link"], category: "Systems",
    });

    await userEvent.click(within(dialog).getByRole("button", { name: "Done" }));
    expect(await within(await videoList()).findByText("CDN basics")).toBeInTheDocument();
    expect(screen.getByText("0 of 4 watched")).toBeInTheDocument();
  });

  it("keeps the submit button disabled until something is pasted, and refuses more than 200 lines", async () => {
    const { dialog } = await openPaste();
    const submit = within(dialog).getByRole("button", { name: "Add videos" });
    expect(submit).toBeDisabled();
    const box = within(dialog).getByLabelText(/Links, one per line/);
    fireEvent.change(box, { target: { value: Array.from({ length: 201 }, (_, i) => `https://example.com/${i}`).join("\n") } });
    expect(submit).toBeDisabled();
    expect(within(dialog).getByText("Paste at most 200 lines at a time.")).toBeInTheDocument();
    fireEvent.change(box, { target: { value: "https://example.com/1" } });
    expect(submit).toBeEnabled();
  });

  it("shows the server's error and keeps what was typed", async () => {
    const { fake, dialog } = await openPaste();
    fake.failNext(/^POST \/api\/video-playlists\/1\/bulk-videos$/, 422, "Too many lines");
    fireEvent.change(within(dialog).getByLabelText(/Links, one per line/), { target: { value: "https://example.com/1" } });
    await userEvent.click(within(dialog).getByRole("button", { name: "Add videos" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Too many lines");
    expect(within(dialog).getByLabelText(/Links, one per line/)).toHaveValue("https://example.com/1");
  });
});

// ================================ navigation ================================

describe("navigation", () => {
  it("the sidebar link is live (no Soon badge) and leads to the page", async () => {
    await open("/");
    await screen.findByRole("heading", { name: /Ada Lovelace/ });
    const nav = screen.getAllByRole("navigation")[0];
    const link = within(nav).getByRole("link", { name: /Videos/ });
    expect(within(link).queryByText("Soon")).not.toBeInTheDocument();
    await userEvent.click(link);
    expect(await screen.findByRole("heading", { name: "Videos", level: 1 })).toBeInTheDocument();
  });
});
